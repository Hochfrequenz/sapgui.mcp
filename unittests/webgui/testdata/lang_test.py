"""
Test-specific DE/EN language constants with explicit _DE/_EN suffixes.

These constants are for test assertions that depend on SAP GUI language.
Follows the same pattern as src/sapguimcp/lang.py but for test-only strings.
"""

# =============================================================================
# BP Transaction - Business Partner
# =============================================================================

# Form field labels
BP_POSTAL_CODE_DE = "Postleitzahl"
BP_POSTAL_CODE_EN = "Postal Code"

BP_CITY_DE = "Ort"
BP_CITY_EN = "City"

BP_STREET_DE = "Straße"
BP_STREET_EN = "Street"

# Dropdown labels
BP_GP_ROLE_LABEL_DE = "GP-Rolle"
BP_GP_ROLE_LABEL_EN = "Role"

BP_GROUPING_LABEL_DE = "Gruppierung"
BP_GROUPING_LABEL_EN = "Grouping"

# Dropdown default values
# Note: Full EN value from SAP is "Business Partner (Gen.)" but we match partial
BP_GP_ROLE_DEFAULT_DE = "GPartner allgemein"
BP_GP_ROLE_DEFAULT_EN = "Business Partner"

# Popup buttons
BP_YES_BUTTON_DE = "Ja"
BP_YES_BUTTON_EN = "Yes"

BP_NO_BUTTON_DE = "Nein"
BP_NO_BUTTON_EN = "No"

# =============================================================================
# SM30 Transaction - Table Maintenance
# =============================================================================

SM30_MAINTAIN_BUTTON_DE = "Pflegen"
SM30_MAINTAIN_BUTTON_EN = "Maintain"

SM30_TABLE_VIEW_LABEL_DE = "Tabelle/Sicht"
SM30_TABLE_VIEW_LABEL_EN = "Table/View"

# =============================================================================
# SE38 Transaction - ABAP Editor
# =============================================================================

SE38_CREATE_BUTTON_DE = "Anlegen"
SE38_CREATE_BUTTON_EN = "Create"

SE38_CONTINUE_BUTTON_DE = "Weiter"
SE38_CONTINUE_BUTTON_EN = "Continue"

SE38_LONG_DOC_BUTTON_DE = "Langdokumentation"
SE38_LONG_DOC_BUTTON_EN = "Long text"

# =============================================================================
# Common popup/dialog buttons
# =============================================================================

BUTTON_CANCEL_DE = "Abbrechen"
BUTTON_CANCEL_EN = "Cancel"

BUTTON_OK_DE = "OK"
BUTTON_OK_EN = "OK"

BUTTON_SAVE_DE = "Sichern"
BUTTON_SAVE_EN = "Save"

BUTTON_BACK_DE = "Zurück"
BUTTON_BACK_EN = "Back"
