"""Function module catalog models - simplified for runtime search."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FMParameter:
    """Simplified parameter info for search."""

    name: str
    typing: str = ""
    reference_type: str = ""
    optional: bool = True
    description: str = ""


@dataclass
class FunctionModuleEntry:  # pylint: disable=too-many-instance-attributes
    """Function module entry in the catalog."""

    name: str
    description: str = ""
    area: str | None = None
    function_group: str | None = None
    import_params: list[FMParameter] = field(default_factory=list)
    export_params: list[FMParameter] = field(default_factory=list)
    changing_params: list[FMParameter] = field(default_factory=list)
    tables_params: list[FMParameter] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    is_rfc_enabled: bool = False
    enriched: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FunctionModuleEntry":
        """Create from catalog JSON dict."""

        def parse_params(params_list: list[dict[str, Any]]) -> list[FMParameter]:
            return [
                FMParameter(
                    name=p.get("name", ""),
                    typing=p.get("typing", ""),
                    reference_type=p.get("reference_type", ""),
                    optional=p.get("optional", True),
                    description=p.get("description", ""),
                )
                for p in params_list
            ]

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            area=data.get("area"),
            function_group=data.get("function_group"),
            import_params=parse_params(data.get("import_params", [])),
            export_params=parse_params(data.get("export_params", [])),
            changing_params=parse_params(data.get("changing_params", [])),
            tables_params=parse_params(data.get("tables_params", [])),
            exceptions=data.get("exceptions", []),
            is_rfc_enabled=data.get("is_rfc_enabled", False),
            enriched=data.get("enriched", False),
        )

    def all_params(self) -> list[FMParameter]:
        """Get all parameters."""
        return self.import_params + self.export_params + self.changing_params + self.tables_params


@dataclass
class FMCatalog:
    """Container for the function module catalog."""

    function_modules: dict[str, FunctionModuleEntry] = field(default_factory=dict)
    source_system: str | None = None
    language: str | None = None
    total_count: int = 0

    def get_by_name(self, name: str) -> FunctionModuleEntry | None:
        """Look up FM by name (case-insensitive)."""
        return self.function_modules.get(name.upper())
