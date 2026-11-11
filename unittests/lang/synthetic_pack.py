"""A synthetic third language pack for the guard tests (#1044, spec section 10).

``synthetic_pack()`` derives a complete pack from EN: every text gets the marker prefix
``⟦XX⟧ ``, except the fields listed in ``same_as_en``, which stay identical to EN. Derived, not
hand-written, so the fields the phase-3 migrations add to the schema appear here without an edit.

Register it only through ``lang._register_for_tests``; never patch ``lang._PACKS``.
"""

import dataclasses
import re
from collections.abc import Mapping

from sapguimcp import lang
from sapguimcp.lang.schema import LanguagePack, Leaf, canonical, sections
from sapguimcp.lang.text import RegexText, Template, Text

CODE = "XX"
MARK = "⟦XX⟧ "
SAME_AS_EN = frozenset({"keys.names[Alt]"})
"""One deliberately untranslated field, so the ``same_as_en`` guards run on a real entry."""


def mark(leaf: Leaf) -> Leaf:
    """The marked copy of one text, with the same kind, flags and placeholders."""
    if isinstance(leaf, Text):
        return Text(tuple(MARK + variant for variant in leaf.variants), fold=leaf.fold, word=leaf.word)
    if isinstance(leaf, RegexText):
        # Grouped, so a top-level alternation in the pattern keeps the marker on every branch.
        return RegexText(tuple(f"{re.escape(MARK)}(?:{pattern})" for pattern in leaf.patterns), fold=leaf.fold)
    return Template(tuple(MARK + variant for variant in leaf.variants), fold=leaf.fold)


def synthetic_pack(code: str = CODE, same_as_en: frozenset[str] = SAME_AS_EN) -> LanguagePack:
    """A complete pack derived from EN; fields in ``same_as_en`` keep the EN value."""
    reference = lang.pack_for("EN")
    replaced: dict[str, object] = {}
    for section_name, section in sections(reference):
        values: dict[str, object] = {}
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            path = f"{section_name}.{field.name}"
            if isinstance(value, Mapping):
                values[field.name] = canonical(
                    {key: leaf if f"{path}[{key}]" in same_as_en else mark(leaf) for key, leaf in value.items()}
                )
            else:
                values[field.name] = value if path in same_as_en else mark(value)
        replaced[section_name] = type(section)(**values)
    return dataclasses.replace(
        reference,
        code=code,
        html_lang=code.lower(),
        logon_dropdown="Synthetisch",
        date_format="%Y-%m-%d",
        same_as_en=same_as_en,
        **replaced,
    )
