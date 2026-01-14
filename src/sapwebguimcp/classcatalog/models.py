"""Class catalog models - simplified for runtime search."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClassEntry:
    """Class entry in the catalog."""

    name: str
    description: str = ""
    object_type: str = "class"  # "class" or "interface"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassEntry":
        """Create from catalog JSON dict."""
        return cls(
            name=data.get("class_name", ""),
            description=data.get("description", ""),
            object_type=data.get("object_type", "class"),
        )


@dataclass
class ClassCatalog:
    """Container for the class catalog."""

    classes: dict[str, ClassEntry] = field(default_factory=dict)
    source_system: str | None = None
    language: str | None = None
    total_count: int = 0

    def get_by_name(self, name: str) -> ClassEntry | None:
        """Look up class by name (case-insensitive)."""
        return self.classes.get(name.upper())
