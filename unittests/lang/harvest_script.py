"""Imports ``scripts/harvest_lang_texts.py`` (not a package) for its tests (#1044, phase 2c)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "harvest_lang_texts.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("harvest_lang_texts", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


harvest = _load()
