"""Compare a language pack with SAP's own texts (#1044, spec section 9). DEVELOPMENT USE ONLY.

Usage::

    uv run python scripts/harvest_lang_texts.py DE --verify [--system <key>]
    uv run python scripts/harvest_lang_texts.py DE --verify --sap-texts texts.json
    uv run python scripts/harvest_lang_texts.py DE --print-sql
    uv run python scripts/harvest_lang_texts.py IT --draft [--system <key>] [--sap-texts texts.json] [--out it.py]

``--verify`` reads every non-``Manual`` source of ``sapguimcp.lang.sources.SOURCES`` for the
language and reports each pack field whose text no longer matches SAP ("drift"). It reads only
development-metadata text tables (DD04T, D021T, RSMPTEXTS, T100, DD07T, TSTCT, T002) through the
ADT data-preview endpoint ``/sap/bc/adt/datapreview/freestyle``, as the SAP API policy allows for
development tooling. Credentials come from ``systems.json`` (sap-mcp-config); OAuth2 systems are
not supported here. For them, ``--print-sql`` lists one query per field: run each through the
sap-adt MCP ``run_query`` tool (purpose ``development_metadata``), save ``{path: [text, ...]}`` as
JSON and pass it with ``--sap-texts``.

``--draft`` writes the source of a draft ``<lang>.py`` for a language that is not registered yet
(any 2-character SAP language key of T002; ``--print-sql`` accepts such a key too). The draft has the
structure of the EN pack. Fields with a SAP source hold SAP's text; ``Manual`` fields, ``fragment``
fields and ``Template`` / ``RegexText`` fields keep the EN value with a ``# TODO`` comment, as do
``html_lang``, ``logon_dropdown`` and ``date_format``. Flags and kinds stay those of EN. It never
registers the pack. Output goes to stdout or ``--out`` (an existing file is not overwritten).

Exit code: 0 without drift, 1 with drift, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from sap_mcp_config import load_default

from sapguimcp.lang import pack_for, supported_languages
from sapguimcp.lang.schema import Leaf, iter_leaves, sections
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
from sapguimcp.lang.text import RegexText, Template, Text

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

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


def _q(value: str) -> str:
    """A Python string literal in double quotes (the formatter would normalise it anyway)."""
    return json.dumps(value, ensure_ascii=False)


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _flags(leaf: Leaf) -> str:
    out = "" if leaf.fold else ", fold=False"
    if isinstance(leaf, Text) and leaf.word:
        out += ", word=True"
    return out


def _tuple(values: Sequence[str], quote: Callable[[str], str]) -> str:
    return "(" + ", ".join(quote(value) for value in values) + ("," if len(values) == 1 else "") + ")"


def _leaf_code(leaf: Leaf, variants: Sequence[str] | None = None) -> str:
    """Constructor call with ``leaf``'s kind and flags; ``variants`` replace its own (``None``: keep)."""
    if isinstance(leaf, RegexText):
        return f"RegexText({_tuple(leaf.patterns, repr)}{_flags(leaf)})"
    return f"{type(leaf).__name__}({_tuple(leaf.variants if variants is None else variants, _q)}{_flags(leaf)})"


def _draft_leaf(leaf: Leaf, source: Source, sap_texts: Sequence[str]) -> tuple[str, str | None]:
    """``(code, comment)`` of one field: SAP's text where it can be taken over safely."""
    if isinstance(source, Manual):
        return _leaf_code(leaf), f"TODO translate (Manual: {_one_line(source.reason)})"
    texts = list(dict.fromkeys(text.strip() for text in sap_texts if text.strip()))
    if not texts:
        return _leaf_code(leaf), "TODO translate (SAP has no text in this language)"
    shown = _one_line(" | ".join(texts))
    if source.relation == "fragment":
        return _leaf_code(leaf), f"TODO fragment of: {shown}"
    if isinstance(leaf, Text):
        return _leaf_code(leaf, texts), None
    return _leaf_code(leaf), f"TODO derive from SAP text: {shown}"  # Template / RegexText: placeholders, regex


def _entry_name(key: object) -> str:
    return f"{type(key).__name__}.{key.name}" if isinstance(key, Enum) else repr(key)


def draft(language: str, fetch: Callable[[str, Source], Sequence[str]]) -> str:
    """Source of a draft ``<language>.py`` shaped like the EN pack (see the module docstring)."""
    if not _LANGUAGE_KEY.match(language):
        raise ValueError(f"not an SAP language key: {language!r}")
    en = pack_for("EN")
    imports: dict[str, set[str]] = {"sapguimcp.lang.schema": {"LanguagePack"}, "sapguimcp.lang.text": set()}
    body: list[str] = []

    def emit(indent: int, text: str, comment: str | None = None) -> None:
        body.append(" " * indent + text + (f"  # {comment}" if comment else ""))

    def leaf_line(indent: int, prefix: str, path: str, leaf: Leaf) -> None:
        source = SOURCES[path]
        code, comment = _draft_leaf(leaf, source, () if isinstance(source, Manual) else fetch(path, source))
        imports["sapguimcp.lang.text"].add(type(leaf).__name__)
        emit(indent, f"{prefix}{code},", comment)

    emit(0, f"{language} = LanguagePack(")
    emit(4, f"code={_q(language)},")
    emit(4, f"html_lang={_q(en.html_lang)},", f"TODO ISO code of <html lang> in the WebGUI for {language}")
    emit(4, f"logon_dropdown={_q(en.logon_dropdown)},", "TODO language name in the WebGUI logon dropdown")
    emit(4, f"date_format={_q(en.date_format)},", "TODO strftime pattern of the default date input format")
    emit(4, "same_as_en=frozenset(),", "TODO field paths that deliberately equal EN")
    for section_name, section in sections(en):
        section_class = type(section).__name__
        imports["sapguimcp.lang.schema"].add(section_class)
        emit(4, f"{section_name}={section_class}(")
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            path = f"{section_name}.{field.name}"
            if not isinstance(value, Mapping):
                leaf_line(8, f"{field.name}=", path, value)
                continue
            imports["sapguimcp.lang.schema"].add("canonical")
            emit(8, f"{field.name}=canonical(")
            emit(12, "{")
            for key, leaf in value.items():
                imports["sapguimcp.lang.schema"].add(type(key).__name__)
                leaf_line(16, f"{_entry_name(key)}: ", f"{path}[{key}]", leaf)
            emit(12, "}")
            emit(8, "),")
        emit(4, "),")
    emit(0, ")")
    lines = [
        f'"""{language} language pack: DRAFT from scripts/harvest_lang_texts.py --draft (#1044).',
        "",
        "Every ``TODO`` comment marks a field a person has to settle; remove it afterwards. Not registered:",
        "follow ``ADDING_A_LANGUAGE.md`` (format with ruff, then register in ``__init__.py``).",
        '"""',
        "",
    ]
    lines.extend(f"from {module} import {', '.join(sorted(names))}" for module, names in sorted(imports.items()))
    return "\n".join([*lines, "", *body, ""])


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
    parser.add_argument("--out", type=Path, help="--draft: write the draft module here instead of stdout")
    args = parser.parse_args(argv)
    if not _LANGUAGE_KEY.match(args.language):
        parser.error(f"not a 2-character SAP language key: {args.language!r}")
    if args.out is not None and not args.draft:
        parser.error("--out belongs to --draft")
    if not (args.draft or args.print_sql) and args.language not in supported_languages():
        parser.error(f"unsupported language {args.language!r}; supported: {', '.join(sorted(supported_languages()))}")
    if args.print_sql:
        for path, source in SOURCES.items():
            if not isinstance(source, Manual):
                print(f"{path}\t{sql_for(source, args.language)}")
        return 0
    preview: AdtPreview | None = None
    if args.sap_texts is not None:
        fetch = _fetch_from_file(json.loads(args.sap_texts.read_text(encoding="utf-8")))
    else:  # only the direct ADT mode needs systems.json and credentials
        config = load_default(supported_languages=supported_languages())
        if args.system is not None and args.system not in config.systems:
            parser.error(f"unknown --system {args.system!r}; known: {', '.join(sorted(config.systems))}")
        preview = AdtPreview.for_system(config.systems[args.system or config.default_system])
        client = preview
        fetch = lambda _path, source: client.query(sql_for(source, args.language))  # noqa: E731
    try:
        if args.draft:
            if preview is not None and not preview.query(f"SELECT LAISO FROM T002 WHERE LAISO = '{args.language}'"):
                print(f"error: {args.language} is not a language of T002 on this system", file=sys.stderr)
                return 2
            source_text = draft(args.language, fetch)
            if args.out is None:
                sys.stdout.write(source_text)
            else:
                try:
                    with args.out.open("x", encoding="utf-8", newline="\n") as handle:
                        handle.write(source_text)
                except OSError as exc:  # includes FileExistsError: the draft never overwrites a file
                    parser.error(f"cannot write {args.out}: {type(exc).__name__}")
                print(f"{args.language}: draft written to {args.out}", file=sys.stderr)
            return 0
        findings = verify(args.language, fetch)
    except httpx.HTTPStatusError as exc:
        print(f"error: SAP request failed with HTTP status {exc.response.status_code}", file=sys.stderr)
        return 2
    except httpx.HTTPError as exc:
        print(f"error: SAP request failed ({type(exc).__name__})", file=sys.stderr)
        return 2
    for path, finding in findings.items():
        print(f"DRIFT {path}: {finding}")
    checked = sum(not isinstance(source, Manual) for source in SOURCES.values())
    print(f"{args.language}: {checked} sourced fields checked, {len(findings)} drifted")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
