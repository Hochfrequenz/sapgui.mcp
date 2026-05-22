"""Tests for middleware models (SapIdentity, SessionStats)."""

from sapguimcp.models.middleware import SapIdentity, SessionStats


def test_sap_identity_model():
    identity = SapIdentity(sap_user="KLEINK", sap_host="sap-prod.acme.com", sap_mandant="100")
    d = identity.model_dump(mode="json", exclude_none=True)
    assert d == {"sap_user": "KLEINK", "sap_host": "sap-prod.acme.com", "sap_mandant": "100"}


def test_session_stats_identity_default_none():
    stats = SessionStats()
    assert stats.sap_identity is None


def test_session_stats_with_identity():
    identity = SapIdentity(sap_user="KLEINK", sap_host="sap-prod.acme.com", sap_mandant="100")
    stats = SessionStats(sap_identity=identity)
    assert stats.sap_identity.sap_user == "KLEINK"
