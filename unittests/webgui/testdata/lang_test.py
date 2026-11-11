"""Test-only SAP texts of the WebGUI tests, as one test pack per logon language (#1044).

The same mechanism as the language packs in ``sapguimcp.lang``: frozen dataclass sections with
required fields only, every value a ``Text``, and a completeness test
(``unittests/webgui/test_lang_test_pack.py``) that checks every registered language has a test
pack with the same fields, kinds and flags. A field whose value deliberately equals EN is listed
in ``same_as_en``. The ``ui_texts`` fixture in ``unittests/webgui/conftest.py`` selects the pack
for ``SAP_LANGUAGE``.

These texts belong to the tests, not to the server, so they live here and not in a language pack.
"""

import os
from dataclasses import dataclass

from sapguimcp.lang import Text, supported_languages

DEFAULT_LANGUAGE = "DE"


@dataclass(frozen=True, slots=True)
class BpTexts:
    """BP transaction (business partner)."""

    postal_code: Text
    city: Text
    street: Text
    gp_role_label: Text
    grouping_label: Text
    gp_role_default: Text
    """Partial match: the full EN value is "Business Partner (Gen.)"."""
    yes_button: Text
    no_button: Text


@dataclass(frozen=True, slots=True)
class Sm30Texts:
    """SM30 (table maintenance)."""

    maintain_button: Text
    table_view_label: Text


@dataclass(frozen=True, slots=True)
class Se38Texts:
    """SE38 (ABAP editor)."""

    create_button: Text
    continue_button: Text
    long_doc_button: Text


@dataclass(frozen=True, slots=True)
class Se16Texts:
    """SE16 (data browser) toolbar actions, as their button titles show them."""

    online_manual_action: Text
    table_contents_action: Text


@dataclass(frozen=True, slots=True)
class SproTexts:
    """SPRO (IMG): a search term that finds IMG activities in the logon language."""

    img_area_search: Text


@dataclass(frozen=True, slots=True)
class ButtonTexts:
    """Common popup and dialog buttons."""

    cancel: Text
    ok: Text
    save: Text
    back: Text


@dataclass(frozen=True, slots=True)
class UiTestPack:
    """Test-only texts of one SAP logon language."""

    code: str
    same_as_en: frozenset[str]
    bp: BpTexts
    sm30: Sm30Texts
    se38: Se38Texts
    se16: Se16Texts
    spro: SproTexts
    buttons: ButtonTexts


TEST_DE = UiTestPack(
    code="DE",
    same_as_en=frozenset({"buttons.ok"}),
    bp=BpTexts(
        postal_code=Text(("Postleitzahl",)),
        city=Text(("Ort",)),
        street=Text(("Straße",)),
        gp_role_label=Text(("GP-Rolle",)),
        grouping_label=Text(("Gruppierung",)),
        gp_role_default=Text(("GPartner allgemein",)),
        yes_button=Text(("Ja",), word=True),
        no_button=Text(("Nein",), word=True),
    ),
    sm30=Sm30Texts(
        maintain_button=Text(("Pflegen",)),
        table_view_label=Text(("Tabelle/Sicht",)),
    ),
    se38=Se38Texts(
        create_button=Text(("Anlegen",)),
        continue_button=Text(("Weiter",)),
        long_doc_button=Text(("Langdokumentation",)),
    ),
    se16=Se16Texts(
        online_manual_action=Text(("Online Handbuch",)),
        table_contents_action=Text(("Tabelleninhalt",)),
    ),
    spro=SproTexts(img_area_search=Text(("Finanzwesen",))),
    buttons=ButtonTexts(
        cancel=Text(("Abbrechen",)),
        ok=Text(("OK",)),
        save=Text(("Sichern",)),
        back=Text(("Zurück",)),
    ),
)

TEST_EN = UiTestPack(
    code="EN",
    same_as_en=frozenset(),
    bp=BpTexts(
        postal_code=Text(("Postal Code",)),
        city=Text(("City",)),
        street=Text(("Street",)),
        gp_role_label=Text(("Role",)),
        grouping_label=Text(("Grouping",)),
        gp_role_default=Text(("Business Partner",)),
        yes_button=Text(("Yes",), word=True),
        no_button=Text(("No",), word=True),
    ),
    sm30=Sm30Texts(
        maintain_button=Text(("Maintain",)),
        table_view_label=Text(("Table/View",)),
    ),
    se38=Se38Texts(
        create_button=Text(("Create",)),
        continue_button=Text(("Continue",)),
        long_doc_button=Text(("Long text",)),
    ),
    se16=Se16Texts(
        online_manual_action=Text(("Online Manual",)),
        table_contents_action=Text(("Table Contents",)),
    ),
    spro=SproTexts(img_area_search=Text(("Financial Accounting",))),
    buttons=ButtonTexts(
        cancel=Text(("Cancel",)),
        ok=Text(("OK",)),
        save=Text(("Save",)),
        back=Text(("Back",)),
    ),
)

UI_TEST_PACKS: dict[str, UiTestPack] = {pack.code: pack for pack in (TEST_DE, TEST_EN)}
"""Test packs by SAP language key; the completeness test requires one per registered language."""


def resolve_sap_language() -> str:
    """The WebGUI tests' logon language from ``SAP_LANGUAGE``; DE when unset or without a pack.

    Unchanged behaviour from the former ``("DE", "EN")`` check, with the list now coming from the
    registered language packs.
    """
    code = os.environ.get("SAP_LANGUAGE", DEFAULT_LANGUAGE).upper()
    return code if code in supported_languages() else DEFAULT_LANGUAGE
