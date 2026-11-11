"""Compare a language pack with SAP's own texts (#1044, spec section 9). DEVELOPMENT USE ONLY.

Usage::

    uv run python scripts/harvest_lang_texts.py DE --verify [--system <key>]
    uv run python scripts/harvest_lang_texts.py DE --verify --sap-texts texts.json
    uv run python scripts/harvest_lang_texts.py DE --print-sql

``--verify`` reads every non-``Manual`` source of ``sapguimcp.lang.sources.SOURCES`` for the
language and reports each pack field whose text no longer matches SAP ("drift"). It reads only
development-metadata text tables (DD04T, D021T, RSMPTEXTS, T100, DD07T, TSTCT, T002) through the
ADT data-preview endpoint ``/sap/bc/adt/datapreview/freestyle``, as the SAP API policy allows for
development tooling. Credentials come from ``systems.json`` (sap-mcp-config); OAuth2 systems are
not supported here. For them, ``--print-sql`` lists one query per field: run each through the
sap-adt MCP ``run_query`` tool (purpose ``development_metadata``), save ``{path: [text, ...]}`` as
JSON and pass it with ``--sap-texts``.

Draft mode (``--draft``, writing a new ``<lang>.py``) is specified in spec section 9 and not
implemented yet. Exit code: 0 without drift, 1 with drift, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from sap_mcp_config import load_default

from sapguimcp.lang import pack_for, supported_languages
from sapguimcp.lang.schema import Leaf, iter_leaves
from sapguimcp.lang.sources import (
    SOURCES,
    DataElement,
    DomainValue,
    GuiFunction,
    Manual,
    Message,
    ScreenText,
    Source,
    Transaction,
)
from sapguimcp.lang.text import RegexText, Template

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sap_mcp_config.models import SAPSystem

_TECHNICAL_ID = re.compile(r"^[A-Z0-9_/]{1,40}$")
_SCREEN_FIELD = re.compile(r"^[A-Z0-9_/*-]{1,132}$")  # D021T FLDN, e.g. RSRD1-TBMA
_LANGUAGE_KEY = re.compile(r"^[A-Z0-9]{2}$")
_T100_PLACEHOLDER = re.compile(r"&\d?")
_PLACEHOLDER_FILL = "ZZPLACEHOLDER"
_DD04T_COLUMN = {"short": "SCRTEXT_S", "medium": "SCRTEXT_M", "long": "SCRTEXT_L", "heading": "REPTEXT"}
_PREVIEW_PATH = "/sap/bc/adt/datapreview/freestyle"
_PREVIEW_NS = "{http://www.sap.com/adt/dataPreview}"


def _field(value: str) -> str:
    """A screen field name (may hold ``-``), checked before it goes into a SQL literal."""
    if not _SCREEN_FIELD.match(value):
        raise ValueError(f"not a screen field name: {value!r}")
    return value


def _id(value: str) -> str:
    """A technical ID, checked before it goes into a SQL literal."""
    if not _TECHNICAL_ID.match(value):
        raise ValueError(f"not a technical ID: {value!r}")
    return value


def sql_for(source: Source, language: str) -> str:
    """ABAP SQL that returns the source's text(s) in ``language`` (a 2-character SAP key)."""
    if not _LANGUAGE_KEY.match(language):
        raise ValueError(f"not an SAP language key: {language!r}")
    lang = f"IN ( SELECT SPRAS FROM T002 WHERE LAISO = '{language}' )"
    match source:
        case DataElement(name=name, length=length):
            return (
                f"SELECT {_DD04T_COLUMN[length]} FROM DD04T WHERE ROLLNAME = '{_id(name)}'"
                f" AND AS4LOCAL = 'A' AND DDLANGUAGE {lang}"
            )
        case ScreenText(program=program, screen=screen, field=field):
            return (
                f"SELECT DTXT FROM D021T WHERE PROG = '{_id(program)}' AND DYNR = '{_id(screen)}'"
                f" AND FLDN = '{_field(field)}' AND LANG {lang}"
            )
        case GuiFunction(program=program, fcode=fcode):
            return (
                f"SELECT TEXT FROM RSMPTEXTS WHERE PROGNAME = '{_id(program)}' AND OBJ_TYPE = 'F'"
                f" AND OBJ_CODE = '{_id(fcode)}' AND SPRSL {lang}"
            )
        case Message(message_class=message_class, number=number):
            return (
                f"SELECT TEXT FROM T100 WHERE ARBGB = '{_id(message_class)}' AND MSGNR = '{_id(number)}'"
                f" AND SPRSL {lang}"
            )
        case DomainValue(domain=domain, value=value):
            return (
                f"SELECT DDTEXT FROM DD07T WHERE DOMNAME = '{_id(domain)}' AND DOMVALUE_L = '{_id(value)}'"
                f" AND AS4LOCAL = 'A' AND DDLANGUAGE {lang}"
            )
        case Transaction(tcode=tcode):
            return f"SELECT TTEXT FROM TSTCT WHERE TCODE = '{_id(tcode)}' AND SPRSL {lang}"
        case Manual():
            raise ValueError("a Manual source has no SQL")


def drift(leaf: Leaf, source: Source, sap_texts: Sequence[str]) -> str | None:
    """``None`` if one of SAP's texts matches the pack text, else a one-line finding."""
    if isinstance(source, Manual):
        return None
    texts = [text.strip() for text in sap_texts if text.strip()]
    if not texts:
        return "SAP has no text for this source"
    for text in texts:
        if isinstance(leaf, Template):
            matched = leaf.search(_T100_PLACEHOLDER.sub(_PLACEHOLDER_FILL, text)) is not None
        elif isinstance(leaf, RegexText):
            matched = leaf.pattern.search(text) is not None
        elif source.relation == "fragment":
            matched = leaf.contains(_T100_PLACEHOLDER.sub(" ", text))
        else:
            matched = leaf.equals(text)
        if matched:
            return None
    return f"SAP says {texts!r}"


def parse_preview(xml_text: str) -> list[str]:
    """First-column values of an ADT data-preview response, one per row."""
    root = ET.fromstring(xml_text)  # noqa: S314  # response of the configured SAP system
    columns = root.findall(f"{_PREVIEW_NS}columns")
    if not columns:
        return []
    return [data.text or "" for data in columns[0].iter(f"{_PREVIEW_NS}data")]


@dataclass
class AdtPreview:
    """Minimal client for the ADT freestyle data preview (development-metadata tables only)."""

    client: httpx.Client
    csrf_token: str = ""

    @classmethod
    def for_system(cls, system: SAPSystem) -> AdtPreview:
        if system.is_oauth2:
            raise SystemExit("OAuth2 systems are not supported; use --print-sql and --sap-texts")
        client = httpx.Client(
            base_url=system.host,
            auth=(system.user, system.password.get_secret_value()),
            params={"sap-client": system.client},
            verify=not system.tls_skip_verify,
            timeout=60,
        )
        return cls(client)

    def query(self, sql: str) -> list[str]:
        if not self.csrf_token:
            response = self.client.get("/sap/bc/adt/discovery", headers={"x-csrf-token": "fetch"})
            response.raise_for_status()
            self.csrf_token = response.headers.get("x-csrf-token", "")
        response = self.client.post(
            _PREVIEW_PATH,
            params={"rowNumber": "100"},
            content=sql.encode("utf-8"),
            headers={
                "x-csrf-token": self.csrf_token,
                "Content-Type": "text/plain",
                "Accept": "application/xml, application/vnd.sap.adt.datapreview.table.v1+xml",
            },
        )
        response.raise_for_status()
        return parse_preview(response.text)


def verify(language: str, fetch: Callable[[str, Source], Sequence[str]]) -> dict[str, str]:
    """Drift findings by field path for ``language``; ``fetch(path, source)`` returns SAP's texts."""
    pack = pack_for(language)
    findings: dict[str, str] = {}
    for path, leaf in iter_leaves(pack):
        source = SOURCES[path]
        if isinstance(source, Manual):
            continue
        finding = drift(leaf, source, fetch(path, source))
        if finding is not None:
            findings[path] = finding
    return findings


def _fetch_from_file(texts: Mapping[str, Sequence[str]]) -> Callable[[str, Source], Sequence[str]]:
    return lambda path, _source: texts.get(path, ())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("language", type=str.upper)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--print-sql", action="store_true")
    mode.add_argument("--draft", action="store_true")
    parser.add_argument("--system", help="systems.json key (default: default_system)")
    parser.add_argument("--sap-texts", type=Path, help="JSON {path: [text, ...]} collected via run_query")
    args = parser.parse_args(argv)
    if args.draft:
        parser.error("--draft is not implemented yet (spec section 9)")
    if args.print_sql:
        for path, source in SOURCES.items():
            if not isinstance(source, Manual):
                print(f"{path}\t{sql_for(source, args.language)}")
        return 0
    if args.sap_texts is not None:
        fetch = _fetch_from_file(json.loads(args.sap_texts.read_text(encoding="utf-8")))
    else:
        config = load_default(supported_languages=supported_languages())
        preview = AdtPreview.for_system(config.systems[args.system or config.default_system])
        fetch = lambda _path, source: preview.query(sql_for(source, args.language))  # noqa: E731
    findings = verify(args.language, fetch)
    for path, finding in findings.items():
        print(f"DRIFT {path}: {finding}")
    checked = sum(not isinstance(source, Manual) for source in SOURCES.values())
    print(f"{args.language}: {checked} sourced fields checked, {len(findings)} drifted")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
