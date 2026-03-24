"""Unit tests for sap_list_connections tool."""

import xml.etree.ElementTree as ET
from textwrap import dedent
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PATCH_GET_BACKEND = "sapwebguimcp.tools.sap_list_connections_impl.get_backend"

_SAMPLE_LANDSCAPE_XML = dedent("""\
    <?xml version="1.0"?>
    <Landscape>
      <Services>
        <Service type="SAPGUI" uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890" name="HFQ" systemid="HFQ" server="172.22.100.151:3200"/>
        <Service type="Reference" uuid="b2c3d4e5-f6a7-8901-bcde-f12345678901" name="HF ECC Lieferant" systemid="HFQ" client="100"
                 user="dachnerm" language="DE" link="a1b2c3d4-e5f6-7890-abcd-ef1234567890"/>
        <Service type="Reference" uuid="c3d4e5f6-a7b8-9012-cdef-123456789012" name="HF ECC Netz" systemid="HFQ" client="200"
                 user="dachnerm" language="DE" link="a1b2c3d4-e5f6-7890-abcd-ef1234567890"/>
        <Service type="SAPGUI" uuid="d4e5f6a7-b8c9-0123-defa-234567890123" name="S4U" systemid="S4U" server="srvhfuhana:3200"/>
      </Services>
    </Landscape>
""")


def _parse_connections(xml_text: str) -> list:
    from sapwebguimcp.tools.sap_list_connections_impl import _parse_landscape_xml

    return _parse_landscape_xml(xml_text)


class TestParseLandscapeXml:
    """_parse_landscape_xml extracts connection info from the XML."""

    def test_returns_sapgui_entries(self) -> None:
        """SAPGUI type entries are returned with name and systemid."""
        entries = _parse_connections(_SAMPLE_LANDSCAPE_XML)
        names = [e["name"] for e in entries]
        assert "HFQ" in names
        assert "S4U" in names

    def test_returns_reference_entries(self) -> None:
        """Reference type entries are included with their client pre-filled."""
        entries = _parse_connections(_SAMPLE_LANDSCAPE_XML)
        hf_lieferant = next(e for e in entries if e["name"] == "HF ECC Lieferant")
        assert hf_lieferant["client"] == "100"
        assert hf_lieferant["type"] == "Reference"

    def test_sapgui_entry_has_server(self) -> None:
        """SAPGUI entries include the server address."""
        entries = _parse_connections(_SAMPLE_LANDSCAPE_XML)
        hfq = next(e for e in entries if e["name"] == "HFQ")
        assert hfq["server"] == "172.22.100.151:3200"
        assert hfq["type"] == "SAPGUI"

    def test_empty_landscape(self) -> None:
        """Empty Services section returns empty list."""
        xml = '<?xml version="1.0"?><Landscape><Services/></Landscape>'
        assert _parse_connections(xml) == []


class TestSapListConnectionsTool:
    """sap_list_connections returns available SAP Logon entries."""

    @pytest.mark.anyio
    async def test_returns_connection_list(self) -> None:
        """Tool calls backend.list_connections and returns results."""
        from sapwebguimcp.tools.sap_list_connections_impl import sap_list_connections_impl

        backend = AsyncMock()
        backend.list_connections.return_value = [
            {"name": "HFQ", "type": "SAPGUI", "systemid": "HFQ", "server": "172.22.100.151:3200", "client": ""},
            {"name": "S4U", "type": "SAPGUI", "systemid": "S4U", "server": "srvhfuhana:3200", "client": ""},
        ]

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_list_connections_impl()

        assert result.success is True
        assert len(result.connections) == 2
        assert result.connections[0]["name"] == "HFQ"
