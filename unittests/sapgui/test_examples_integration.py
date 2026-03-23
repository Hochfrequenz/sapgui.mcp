"""Integration tests that run the sapsucker example scripts.

Ensures examples stay working as the API evolves.
Each test passes a live session to the example's main() function.
"""

import sys

import pytest

from unittests.conftest import is_sap_integration_test_machine

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only"),
    pytest.mark.skipif(
        not is_sap_integration_test_machine(),
        reason="SAP integration tests only run on authorized machines",
    ),
]


class TestExamples:
    def test_basic_navigation(self, sap_desktop_session):
        from examples.sapsucker.basic_navigation import main

        main(session=sap_desktop_session)

    def test_form_filling(self, sap_desktop_session):
        from examples.sapsucker.form_filling import main

        main(session=sap_desktop_session)

    def test_tree_navigation(self, sap_desktop_session):
        from examples.sapsucker.tree_navigation import main

        main(session=sap_desktop_session)

    def test_alv_grid_export(self, sap_desktop_session):
        from examples.sapsucker.alv_grid_export import main

        main(session=sap_desktop_session)
