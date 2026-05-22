"""
Pydantic models for SE24 (Class Builder) lookup results.

These models represent class/interface metadata from SE24 including:
- Class/Interface basic info (name, description, package, superclass)
- Methods with parameters and exceptions
- Attributes (constants, instance/static variables)
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "SE24Result",
    "SE24Entry",
    "SE24Error",
    "SE24Method",
    "SE24MethodParameter",
    "SE24MethodException",
    "SE24Attribute",
    "SE24FileSummary",
    "SE24ObjectType",
    "SE24Visibility",
    "SE24ParameterCategory",
]

# =============================================================================
# Type Aliases
# =============================================================================

SE24ObjectType = Literal["class", "interface"]
SE24Visibility = Literal["public", "protected", "private"]
SE24ParameterCategory = Literal["importing", "exporting", "changing", "returning"]


# =============================================================================
# Sub-Models
# =============================================================================


class SE24MethodParameter(BaseModel):
    """A method parameter (importing/exporting/changing/returning)."""

    name: str
    """Parameter name."""

    category: SE24ParameterCategory
    """Parameter category: importing, exporting, changing, or returning."""

    type_ref: str
    """Type reference (e.g., 'STRING', 'I', 'REF TO CL_SALV_TABLE')."""

    optional: bool = False
    """Whether the parameter is optional."""

    default_value: str | None = None
    """Default value if parameter is optional."""

    description: str = ""
    """Parameter description."""


class SE24MethodException(BaseModel):
    """An exception that a method can raise."""

    name: str
    """Exception name."""

    description: str = ""
    """Exception description."""


class SE24Method(BaseModel):
    """A class/interface method."""

    name: str
    """Method name."""

    visibility: SE24Visibility
    """Visibility: public, protected, or private."""

    is_static: bool = False
    """Whether the method is static (class method)."""

    is_abstract: bool = False
    """Whether the method is abstract."""

    is_final: bool = False
    """Whether the method is final (cannot be redefined)."""

    is_constructor: bool = False
    """Whether this is the constructor method."""

    importing_parameters: list[SE24MethodParameter] = Field(default_factory=list)
    """Import parameters."""

    exporting_parameters: list[SE24MethodParameter] = Field(default_factory=list)
    """Export parameters."""

    changing_parameters: list[SE24MethodParameter] = Field(default_factory=list)
    """Changing parameters."""

    returning_parameter: SE24MethodParameter | None = None
    """Returning parameter (if any - functional method)."""

    exceptions: list[SE24MethodException] = Field(default_factory=list)
    """Exceptions that can be raised."""

    description: str = ""
    """Method description."""


class SE24Attribute(BaseModel):
    """A class attribute (constant, instance variable, or static variable)."""

    name: str
    """Attribute name."""

    visibility: SE24Visibility
    """Visibility: public, protected, or private."""

    is_static: bool = False
    """Whether the attribute is static (class attribute)."""

    is_constant: bool = False
    """Whether the attribute is a constant."""

    is_read_only: bool = False
    """Whether the attribute is read-only."""

    type_ref: str
    """Type reference."""

    default_value: str | None = None
    """Initial/default value."""

    description: str = ""
    """Attribute description."""


# =============================================================================
# Main Models
# =============================================================================


class SE24Entry(BaseModel):
    """Successful SE24 class/interface lookup result."""

    class_name: str
    """Class or interface name."""

    object_type: SE24ObjectType
    """Whether this is a class or interface."""

    description: str = ""
    """Class/interface description."""

    package: str = ""
    """Development package."""

    superclass: str | None = None
    """Superclass name (for classes only)."""

    is_abstract: bool = False
    """Whether the class is abstract."""

    is_final: bool = False
    """Whether the class is final."""

    interfaces: list[str] = Field(default_factory=list)
    """List of implemented interfaces."""

    methods: list[SE24Method] = Field(default_factory=list)
    """List of methods."""

    attributes: list[SE24Attribute] = Field(default_factory=list)
    """List of attributes."""

    retrieved_at: AwareDatetime
    """When this information was retrieved."""


class SE24Error(BaseModel):
    """Failed SE24 lookup result."""

    class_name: str
    """The class/interface name that failed lookup."""

    error: str
    """Error message."""

    retrieved_at: AwareDatetime
    """When the error occurred."""


class SE24Result(ToolResult):
    """Result of SE24 class/interface lookup."""

    entries: list[SE24Entry] = Field(default_factory=list)
    """Successfully looked up classes/interfaces."""

    errors: list[SE24Error] = Field(default_factory=list)
    """Failed lookups."""


class SE24FileSummary(ToolResult):
    """Summary returned when results are written to file."""

    output_file: str
    """Path to the output file."""

    total_requested: int
    """Total number of classes/interfaces requested."""

    successful: int
    """Number of successful lookups."""

    failed: int
    """Number of failed lookups."""

    sample_entries: list[str] = Field(default_factory=list)
    """Sample of successfully looked up class names (first 5)."""

    sample_errors: list[str] = Field(default_factory=list)
    """Sample of failed class names (first 5)."""
