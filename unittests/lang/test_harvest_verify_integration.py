"""Live: the DE and EN packs match SAP's texts for every sourced field (#1044, spec section 9).

Reads development-metadata text tables through ADT data preview (no SAP GUI session). Marked
``integration`` explicitly: it uses no live SAP GUI fixture, so the automatic marker misses it.
``SAP_HARVEST_SYSTEM`` selects a ``systems.json`` key; the default system otherwise.
"""

import os

import pytest
from sap_mcp_config import load_default

from sapguimcp.lang import supported_languages
from unittests.lang.harvest_script import harvest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("language", ["DE", "EN"])
def test_pack_matches_sap(language: str) -> None:
    try:
        config = load_default(supported_languages=supported_languages())
    except Exception as exc:  # no systems.json on this machine
        pytest.skip(f"no SAP configuration: {exc}")
    system = config.systems[os.environ.get("SAP_HARVEST_SYSTEM") or config.default_system]
    if system.is_oauth2:
        pytest.skip("OAuth2 system: run the --print-sql / --sap-texts recipe instead")
    preview = harvest.AdtPreview.for_system(system)
    findings = harvest.verify(language, lambda _path, source: preview.query(harvest.sql_for(source, language)))
    assert findings == {}
