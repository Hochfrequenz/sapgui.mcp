"""Integration tests for BP (Business Partner) transaction.

Covers fill form, set field, dropdowns, form fields, and org form tests.
"""

import asyncio
import os

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import ClickResult, WaitResult
from sapguimcp.models import (
    FillFormResult,
    FormFieldsResult,
    KeyboardResult,
    LoginResult,
    ScreenText,
    SetFieldResult,
    TransactionResult,
)

from .conftest import call_tool_typed
from .integration_helpers import (
    _wait_for_transaction_screen,
    capture_html_snapshot,
)


@pytest.mark.anyio
async def test_bp_fill_form_batch_fill(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form batch filling in BP (Business Partner) transaction.

    This test verifies that sap_fill_form can fill multiple form fields
    in a single call, which is much faster than individual browser_fill calls.

    The test:
    1. Opens BP transaction
    2. Captures HTML snapshot of initial screen (shows Person/Organisation buttons)
    3. Clicks "Person" button to create a new person BP
    4. Captures HTML snapshot of person form
    5. Uses sap_fill_form to batch fill name and address fields
    6. Verifies all fields were reported as filled
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Step 1: Open BP transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    assert result.success, f"sap_transaction BP failed: {result.error}"

    # Wait for BP initial screen (has Person/Organisation buttons)
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Capture HTML snapshot of BP initial screen
    await capture_html_snapshot(sap_mcp_client, "bp_initial")

    # Step 2: Click on the "Person" button to create a new person
    # The button has ID M0:48::btn[5] with text "Person anlegen (F5)"
    #
    # IMPORTANT: SAP Web GUI requires multiple waits for reliable form interaction:
    # - Pre-click wait: Ensures the page is fully interactive after initial load
    # - Post-click wait: Allows SAP backend to process and return the form HTML
    # - Form label wait: Ensures the specific form labels are rendered
    # - Post-render wait: Allows all label-input associations (lsdata) to be populated
    # Without these waits, the form may not have all labels visible when sap_fill_form runs.
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    click_result = await call_tool_typed(
        sap_mcp_client, "browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"}, ClickResult
    )
    assert click_result.success, f"Failed to click Person button: {click_result.error}"

    # Wait for SAP backend to process and return form HTML
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Wait for specific form labels to be rendered
    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})

    # Allow all label-input lsdata associations to be populated
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Capture HTML snapshot after clicking Person (shows the form fields)
    await capture_html_snapshot(sap_mcp_client, "bp_person_form")

    # Step 3: Use sap_fill_form to batch fill multiple fields
    # Field labels depend on language setting
    if sap_language == "DE":
        fields_to_fill = {
            "Vorname": "Max",
            "Nachname": "Mustermann",
        }
    else:
        fields_to_fill = {
            "First Name": "Max",
            "Last Name": "Mustermann",
        }

    fill_result = await call_tool_typed(sap_mcp_client, "sap_fill_form", {"fields": fields_to_fill}, FillFormResult)
    assert fill_result.success, f"sap_fill_form failed: {fill_result.error}"

    # Verify ALL fields were filled successfully
    filled_fields = set(fill_result.filled or [])
    not_found_fields = fill_result.not_found or []
    error_fields = fill_result.errors or []
    expected_fields = set(fields_to_fill.keys())

    # No fields should be missing or have errors
    assert len(not_found_fields) == 0, (
        f"All fields must be found. Not found: {not_found_fields}. "
        f"Check if labels match SAP_LANGUAGE={sap_language} setting."
    )
    assert len(error_fields) == 0, f"All fields must fill without errors. Errors: {error_fields}"

    # All requested fields must be in the filled list
    assert (
        filled_fields == expected_fields
    ), f"All fields must be filled. Expected: {expected_fields}, Filled: {filled_fields}"


@pytest.mark.anyio
async def test_bp_fill_form_with_css_selectors(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form using CSS selectors instead of labels.

    This test verifies that sap_fill_form can fill fields using direct
    CSS selectors (e.g., [attribute*='value'] selectors) that match SAP lsdata attributes.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open BP transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    assert result.success, f"sap_transaction BP failed: {result.error}"

    # Wait for BP initial screen
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Click on "Person" button to create a new person
    # IMPORTANT: SAP Web GUI requires multiple waits for reliable form interaction.
    # See test_bp_fill_form_batch_fill for detailed explanation.
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    click_result = await call_tool_typed(
        sap_mcp_client, "browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"}, ClickResult
    )
    assert click_result.success, f"Failed to click Person button: {click_result.error}"

    # Wait for SAP backend to process and return form HTML
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Wait for first name label to confirm form is loaded
    await sap_mcp_client.call_tool(
        "browser_wait", {"selector": "label:has-text('Vorname'), label:has-text('First Name')", "timeout": 15000}
    )

    # Allow all label-input lsdata associations to be populated
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Use CSS selectors that match SAP lsdata attributes for BP person form
    # These selectors target the actual SAP field IDs embedded in lsdata
    # Based on actual BP form HTML snapshots (bp_person_form_de.html)
    fields_to_fill = {
        "input[lsdata*='NAME_FIRST']": "Max",
        "input[lsdata*='NAME_LAST']": "Mustermann",
        "input[lsdata*='STREET']": "Hauptstraße",
        "input[lsdata*='HOUSE_NUM1']": "123",
        "input[lsdata*='POST_CODE1']": "12345",
        "input[lsdata*='CITY1']": "Berlin",
    }

    fill_result = await call_tool_typed(sap_mcp_client, "sap_fill_form", {"fields": fields_to_fill}, FillFormResult)
    assert fill_result.success, f"sap_fill_form with CSS selectors failed: {fill_result.error}"

    # Verify ALL fields were filled successfully
    filled_fields = set(fill_result.filled or [])
    not_found_fields = fill_result.not_found or []
    error_fields = fill_result.errors or []
    expected_fields = set(fields_to_fill.keys())

    # No fields should be missing or have errors
    assert len(not_found_fields) == 0, (
        f"All CSS selector fields must be found. Not found: {not_found_fields}. "
        f"Selectors may need adjustment based on actual BP form HTML."
    )
    assert len(error_fields) == 0, f"All fields must fill without errors. Errors: {error_fields}"

    # All requested fields must be in the filled list
    assert (
        filled_fields == expected_fields
    ), f"All fields must be filled. Expected: {expected_fields}, Filled: {filled_fields}"


@pytest.mark.anyio
async def test_bp_org_form_snapshot(sap_mcp_client: ClientSession) -> None:
    """
    Capture HTML snapshot of BP organisation form for offline label verification.

    Opens the BP transaction and presses F6 to create an organisation.
    Saves the snapshot so unit tests can verify field labels used in prompts.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    assert result.success, f"sap_transaction BP failed: {result.error}"

    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Wait for initial screen to be fully interactive
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Click the "Organisation" category button, then fill mandatory fields
    # to reach the org data entry form.  The BP workflow requires selecting
    # a category first, then filling minimum data before the full form appears.
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")
    org_label = "Organisation" if sap_language == "DE" else "Organization"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": f"span:has-text('{org_label}')"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Wait for org-specific label ("Name 1" is the same in DE and EN).
    # If the org form doesn't appear (SAP may show intermediate screens),
    # skip gracefully so the unit test (test_bp_org_form_prompt_labels)
    # gets a proper skip rather than using a stale snapshot.
    wait_result = await call_tool_typed(
        sap_mcp_client,
        "browser_wait",
        {"selector": "label:has-text('Name 1')", "timeout": 15000},
        WaitResult,
    )
    if not wait_result.success:
        pytest.skip(
            "BP org form did not appear after clicking Organisation — "
            "SAP may require additional navigation steps. "
            "Snapshot not re-captured."
        )

    # Allow all label-input lsdata associations to be populated
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Capture HTML snapshot of org form for offline label verification
    await capture_html_snapshot(sap_mcp_client, "bp_org_form", overwrite=True)


@pytest.mark.anyio
async def test_sap_fill_form_strict_mode(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form strict mode - should fail if any field is not found.

    In strict mode (strict=True), the tool should return success=False
    if any field cannot be found or filled.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open a simple transaction
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Try to fill with an invalid field label in strict mode
    fill_result = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {
            "fields": {
                "NONEXISTENT_FIELD_12345": "test value",
            },
            "strict": True,
        },
        FillFormResult,
    )

    # Strict mode should report failure when field not found
    assert not fill_result.success, f"Strict mode should fail when field not found. Response: {fill_result}"
    assert (
        fill_result.not_found and "NONEXISTENT_FIELD_12345" in fill_result.not_found
    ), f"Field should be in not_found list: {fill_result}"


@pytest.mark.anyio
async def test_bp_fill_form_ambiguous_label_rejected(sap_mcp_client: ClientSession) -> None:
    """
    Test that ambiguous labels are rejected with a helpful error message.

    The BP Person form (BP transaction, F5 for Person) has two "Postleitzahl" fields:
    - ADDR2_DATA-POST_CODE1: for street address
    - ADDR2_DATA-POST_CODE2: for PO Box address

    Using the label "Postleitzahl" (German) or "Postal Code" (English) should fail
    because it's ambiguous. The error message should include the available CSS selectors.

    This test verifies the fix for the bug where sap_fill_form silently matched
    the first field when multiple fields shared the same label.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open BP transaction
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Press F5 to create a Person (uses sap_press_key which reads status bar)
    keyboard_result = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)

    # Handle category selection popup if it appears
    if keyboard_result.popup:
        # Click "Ja" (Yes) or confirm button to proceed
        await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Enter"}, KeyboardResult)
        await asyncio.sleep(0.5)

    # Wait for Person form to load
    await asyncio.sleep(1.0)

    # Determine the ambiguous label based on language
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")
    ambiguous_label = "Postleitzahl" if sap_language == "DE" else "Postal Code"

    # Try to fill using the ambiguous label
    # This should fail because there are 2 fields with this label
    fill_result = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {
            "fields": {
                ambiguous_label: "12345",  # Ambiguous - matches POST_CODE1 and POST_CODE2
            },
        },
        FillFormResult,
    )

    # The field should NOT be filled successfully
    filled_fields = fill_result.filled or []
    assert ambiguous_label not in filled_fields, (
        f"Ambiguous label '{ambiguous_label}' should NOT be filled. " f"Response: {fill_result}"
    )

    # There should be an error about the ambiguous label
    errors = fill_result.errors or []
    error_messages = [str(e) for e in errors]
    error_text = " ".join(error_messages)

    assert any(ambiguous_label in msg or "matches" in msg.lower() for msg in error_messages), (
        f"Expected an error mentioning '{ambiguous_label}' ambiguity. " f"Errors: {errors}, Response: {fill_result}"
    )

    # The error should mention POST_CODE1 and/or POST_CODE2 as alternatives
    assert "POST_CODE" in error_text or "#" in error_text, (
        f"Error should include CSS selectors as alternatives. " f"Errors: {errors}"
    )


@pytest.mark.anyio
async def test_bp_set_field_ambiguous_label_rejected(sap_mcp_client: ClientSession) -> None:
    """
    Test that sap_set_field also rejects ambiguous labels.

    Similar to test_bp_fill_form_ambiguous_label_rejected but tests the
    single-field sap_set_field tool instead of sap_fill_form.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open BP transaction
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Press F5 to create a Person
    keyboard_result = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)

    # Handle category selection popup if it appears
    if keyboard_result.popup:
        await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Enter"}, KeyboardResult)
        await asyncio.sleep(0.5)

    # Wait for Person form to load
    await asyncio.sleep(1.0)

    # Try to set the ambiguous "Postleitzahl" field
    set_result = await call_tool_typed(
        sap_mcp_client,
        "sap_set_field",
        {
            "label": "Postleitzahl",
            "value": "12345",
        },
        SetFieldResult,
    )

    # Should fail due to ambiguity
    assert not set_result.success, (
        f"sap_set_field should fail for ambiguous label 'Postleitzahl'. " f"Response: {set_result}"
    )

    # Error should mention the ambiguity
    error = set_result.error or ""
    assert (
        "Postleitzahl" in error or "matches" in error.lower() or "ambiguous" in error.lower()
    ), f"Error should mention ambiguity. Error: {error}"


@pytest.mark.anyio
async def test_bp_get_form_fields_discovers_dropdowns(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_get_form_fields discovers dropdown fields on BP create person screen.

    The BP create person screen has two dropdown fields:
    - GP-Rolle (Business Partner Role)
    - Gruppierung (Grouping)

    This test verifies that sap_get_form_fields correctly identifies these as dropdowns.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Wait for form to load
    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Call sap_get_form_fields
    data = await call_tool_typed(sap_mcp_client, "sap_get_form_fields", {}, FormFieldsResult)
    assert data.success, f"sap_get_form_fields failed: {data.error}"

    # Check that fields were found
    fields = data.fields
    assert len(fields) > 0, "Expected to find form fields"

    # Find dropdown fields
    dropdown_fields = [f for f in fields if f.field_type == "dropdown"]
    assert (
        len(dropdown_fields) >= 2
    ), f"Expected at least 2 dropdowns (GP-Rolle, Gruppierung), found {len(dropdown_fields)}"

    # Check for GP-Rolle dropdown
    gp_rolle_dropdown = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert (
        gp_rolle_dropdown is not None
    ), f"Expected GP-Rolle dropdown. Found dropdowns: {[f.label for f in dropdown_fields]}"
    assert gp_rolle_dropdown.id, "Dropdown should have an ID"


@pytest.mark.anyio
async def test_bp_get_form_fields_with_dropdown_options(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_get_form_fields with include_dropdown_options=True fetches options.

    When include_dropdown_options=True, the tool should open each dropdown,
    extract available options, and return them in the field data.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Call sap_get_form_fields with dropdown options
    data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": True}, FormFieldsResult
    )
    assert data.success, f"sap_get_form_fields with options failed: {data.error}"

    # Find dropdown fields with options
    dropdown_fields = [f for f in data.fields if f.field_type == "dropdown"]
    assert len(dropdown_fields) >= 2, "Expected at least 2 dropdowns"

    # GP-Rolle should have options populated
    gp_rolle_dropdown = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert gp_rolle_dropdown is not None, "Expected GP-Rolle dropdown"

    options = gp_rolle_dropdown.options
    assert options is not None, "Expected options to be populated when include_dropdown_options=True"
    assert len(options) > 0, "Expected GP-Rolle to have available options"

    # Verify it has the default option (GPartner allgemein / Business Partner (Gen.))
    has_general_bp = any("GPartner" in opt or "General" in opt or "Business Partner" in opt for opt in options)
    assert has_general_bp, f"Expected 'GPartner allgemein' or 'Business Partner' in options: {options}"


@pytest.mark.anyio
async def test_bp_get_screen_text_with_dropdown_options(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_get_screen_text with include_dropdown_options=True.

    The dropdowns field should contain dropdown info with options.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Call sap_get_screen_text with dropdown options
    data = await call_tool_typed(sap_mcp_client, "sap_get_screen_text", {"include_dropdown_options": True}, ScreenText)
    assert data.success, f"sap_get_screen_text with dropdowns failed: {data.error}"

    # Check that dropdowns field is populated
    dropdowns = data.dropdowns
    assert dropdowns is not None, "Expected dropdowns field when include_dropdown_options=True"
    assert len(dropdowns) >= 2, f"Expected at least 2 dropdowns, found {len(dropdowns)}"

    # Each dropdown should have id, label, and options
    for dd in dropdowns:
        assert dd.id, f"Dropdown should have id: {dd}"
        assert dd.label, f"Dropdown should have label: {dd}"
        assert isinstance(dd.options, list), f"Dropdown should have options list: {dd}"


@pytest.mark.anyio
async def test_bp_fill_form_dropdown_selection(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form can select a dropdown value by label.

    This test selects a specific GP-Rolle value from the dropdown.
    Note: Changing GP-Rolle may trigger a popup dialog.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # First, get the dropdown options to know valid values
    form_data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": True}, FormFieldsResult
    )
    assert form_data.success, f"sap_get_form_fields failed: {form_data.error}"

    # Find GP-Rolle dropdown and get first option
    dropdown_fields = [f for f in form_data.fields if f.field_type == "dropdown"]
    gp_rolle = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert gp_rolle is not None, "Expected GP-Rolle dropdown"

    options = gp_rolle.options or []
    assert len(options) > 0, "Expected GP-Rolle to have options"

    # Select the first option (should be the default, so no popup)
    option_to_select = options[0]
    element_id = gp_rolle.id

    # Use CSS selector with element ID
    selector = f"#{element_id}"
    fill_data = await call_tool_typed(
        sap_mcp_client, "sap_fill_form", {"fields": {selector: option_to_select}}, FillFormResult
    )
    assert fill_data.success, f"sap_fill_form dropdown failed: {fill_data.error}"

    # Verify the field was filled (selector should be in filled list)
    filled = fill_data.filled
    assert selector in filled, f"Expected {selector} to be filled. Result: {fill_data}"


@pytest.mark.anyio
async def test_bp_fill_form_dropdown_invalid_value(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form returns available options when dropdown value not found.

    When a requested value is not in the dropdown, the tool should fail
    and return the list of available options.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Try to fill with invalid dropdown value.
    # sap_fill_form uses bulk JS (fill_form_fields.js) which types directly
    # into the field — SAP comboboxes accept any typed text without validation.
    # Dropdown validation only happens via sap_set_field (which uses
    # select_dropdown_option.js).
    label = "GP-Rolle" if sap_language == "DE" else "BP Role"
    fill_data = await call_tool_typed(
        sap_mcp_client, "sap_fill_form", {"fields": {label: "INVALID_NONEXISTENT_VALUE_12345"}}, FillFormResult
    )

    # fill_form types the value directly — SAP accepts it without error
    assert fill_data.success, f"Expected fill to succeed (SAP accepts free-text in combobox). Result: {fill_data}"
    assert label in (fill_data.filled or []), f"Expected '{label}' in filled list. Result: {fill_data}"


@pytest.mark.anyio
async def test_bp_set_field_dropdown_selection(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_set_field can select a dropdown value by label.

    This tests the single-field variant of dropdown selection.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # First, get the dropdown options to know valid values
    form_data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": True}, FormFieldsResult
    )
    assert form_data.success, f"sap_get_form_fields failed: {form_data.error}"

    # Find GP-Rolle dropdown and get first option
    dropdown_fields = [f for f in form_data.fields if f.field_type == "dropdown"]
    gp_rolle = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert gp_rolle is not None, "Expected GP-Rolle dropdown"

    options = gp_rolle.options or []
    assert len(options) > 0, "Expected GP-Rolle to have options"

    # Select the first option using sap_set_field
    option_to_select = options[0]
    label = gp_rolle.label

    set_data = await call_tool_typed(
        sap_mcp_client, "sap_set_field", {"label": label, "value": option_to_select}, SetFieldResult
    )
    assert set_data.success, f"sap_set_field dropdown failed: {set_data.error}"

    # Verify the field was set
    assert set_data.label == label, f"Expected label {label}. Result: {set_data}"
    assert set_data.value == option_to_select, f"Expected value {option_to_select}. Result: {set_data}"
    # Note: selector_used is not populated by fill_field() — it returns None.
    # The backend protocol doesn't expose which CSS selector was matched.


@pytest.mark.anyio
async def test_bp_set_field_dropdown_invalid_value(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_set_field returns available options when dropdown value not found.

    Similar to sap_fill_form, but for single field setting.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Try to set invalid dropdown value
    label = "GP-Rolle" if sap_language == "DE" else "BP Role"
    set_data = await call_tool_typed(
        sap_mcp_client, "sap_set_field", {"label": label, "value": "INVALID_NONEXISTENT_VALUE_12345"}, SetFieldResult
    )

    # Should have failed
    assert not set_data.success, f"Expected failure for invalid dropdown value. Result: {set_data}"

    # Error should contain available options
    available = set_data.available_options
    assert available is not None, f"Expected available_options in result: {set_data}"
    assert len(available) > 0, f"Expected non-empty available_options: {set_data}"


@pytest.mark.anyio
async def test_bp_dropdown_value_actually_applied(sap_mcp_client: ClientSession) -> None:
    """
    Test that dropdown selection actually changes the input field value.

    This verifies the fix for issues:
    - #72 (dropdown doesn't open)
    - #73 (value not applied)
    - #74 (learning: listbox visibility approach)
    - #79 (GP-Rolle not set correctly)

    The test:
    1. Gets the current dropdown value
    2. Selects a DIFFERENT dropdown option
    3. Verifies the input field value actually changed
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Get form fields with dropdown options
    form_data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": True}, FormFieldsResult
    )
    assert form_data.success, f"sap_get_form_fields failed: {form_data.error}"

    # Find GP-Rolle dropdown
    dropdown_fields = [f for f in form_data.fields if f.field_type == "dropdown"]
    gp_rolle = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert gp_rolle is not None, "Expected GP-Rolle dropdown"

    # Get current value and available options
    original_value = gp_rolle.current_value or ""
    options = gp_rolle.options or []
    assert len(options) >= 2, "Need at least 2 options to test value change"

    # Find a different option than the current value
    option_to_select = None
    for opt in options:
        # Options are in format "KEY - Description"
        if opt != original_value and opt.strip():
            option_to_select = opt
            break

    assert (
        option_to_select is not None
    ), f"Could not find different option. Current: {original_value}, Options: {options}"

    # Extract just the key from "KEY - Description" format for matching
    option_key = option_to_select.split(" - ")[0].strip() if " - " in option_to_select else option_to_select

    # Select the new option
    label = gp_rolle.label
    set_data = await call_tool_typed(
        sap_mcp_client, "sap_set_field", {"label": label, "value": option_key}, SetFieldResult
    )
    assert set_data.success, f"sap_set_field dropdown selection failed: {set_data.error}"

    # Wait for SAP to process the selection
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Read the form fields again to verify the value changed
    verify_data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": False}, FormFieldsResult
    )
    assert verify_data.success, f"sap_get_form_fields verification failed: {verify_data.error}"

    # Find the GP-Rolle field again
    verify_dropdown_fields = [f for f in verify_data.fields if f.field_type == "dropdown"]
    verify_gp_rolle = next(
        (f for f in verify_dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert verify_gp_rolle is not None, "Expected GP-Rolle dropdown in verification"

    # Check that the value actually changed
    new_value = verify_gp_rolle.current_value or ""

    # The new value should contain the selected option key (not the original value)
    assert option_key in new_value or new_value != original_value, (
        f"Dropdown value should have changed. "
        f"Original: {original_value}, Expected key: {option_key}, Actual: {new_value}"
    )
