"""Unit tests for sap_run_script — no live SAP required."""

from __future__ import annotations

import pytest

from sapwebguimcp.backend.desktop.models.script_results import SapRunScriptResult


class TestSapRunScriptResult:
    def test_success_defaults(self):
        r = SapRunScriptResult(output=["hello"])
        assert r.success is True
        assert r.error is None
        assert r.output == ["hello"]
        assert r.error_traceback is None

    def test_failure_factory(self):
        r = SapRunScriptResult.failure("NameError: x")
        assert r.success is False
        assert r.error == "NameError: x"
        assert r.output == []
        assert r.error_traceback is None

    def test_failure_with_partial_output(self):
        r = SapRunScriptResult.failure("KeyError: 'col'", output=["row0", "row1"])
        assert r.success is False
        assert r.output == ["row0", "row1"]

    def test_success_true_with_error_raises(self):
        with pytest.raises(Exception):
            SapRunScriptResult(success=True, error="oops")

    def test_success_false_without_error_raises(self):
        with pytest.raises(Exception):
            SapRunScriptResult(success=False)
