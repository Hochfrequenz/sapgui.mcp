# sapsucker

Typed Python wrapper for the SAP GUI Scripting API.

**sapsucker** gives you typed, IDE-friendly access to SAP GUI for Windows.
Instead of working with raw COM objects and guessing method names, you get
Python classes with autocomplete, type hints, and docstrings for every
SAP GUI element.

## Quickstart

```python
from sapsucker import SapGui

# Connect to running SAP GUI
app = SapGui.connect()
session = app.connections[0].sessions[0]

# Read session info
print(session.info.system_name)   # → "S4H"
print(session.info.user)          # → "DEVELOPER"

# Navigate to a transaction
session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/nSE16"
session.find_by_id("wnd[0]").send_v_key(0)  # Enter

# Read the status bar
print(session.find_by_id("wnd[0]/sbar").text)
```

## Why sapsucker?

| Feature                       | sapsucker | pysapscript | sapguipy | raw COM |
| ----------------------------- | --------- | ----------- | -------- | ------- |
| Typed wrappers (40+ classes)  | Yes       | No          | No       | No      |
| IDE autocomplete              | Yes       | No          | No       | No      |
| Type hints on every method    | Yes       | No          | No       | No      |
| Docstrings with SAP context   | Yes       | Partial     | No       | No      |
| Unit tests                    | 430+      | No          | No       | —       |
| Integration tests (real SAP)  | 50+       | No          | No       | —       |
| Linting (pylint, mypy, black) | Yes       | No          | No       | —       |
| API verified against PDF      | Yes       | No          | No       | —       |
| License                       | MIT       | GPL-3       | MIT      | —       |

Other Python libraries for SAP GUI (`pysapscript`, `PySapGUI`, `sapguipy`,
`robotframework-sapguilibrary`) use generic `read()`/`write()` methods or
Robot Framework keywords. sapsucker wraps each SAP GUI element type with its
own Python class, so `GuiGridView` has `get_cell_value()` and `GuiTree` has
`expand_node()` — not `element.read("cell", row, col)`.

## Installation

> **Note:** sapsucker is not yet published on PyPI. Install from the repository:

```bash
pip install git+https://github.com/Hochfrequenz/sapwebgui.mcp.git
```

### Prerequisites

- **SAP GUI for Windows** (7.x or 8.x)
- **SAP GUI Scripting enabled** — ask your SAP Basis team to set `sapgui/user_scripting = TRUE` in transaction RZ11, and enable scripting in your SAP GUI options (Customize Local Layout → Accessibility & Scripting)
- **Python 3.10+** on Windows

## Usage Examples

### Read an ALV grid

```python
from sapsucker import SapGui
from sapsucker.components.grid import GuiGridView

app = SapGui.connect()
session = app.connections[0].sessions[0]

# Find the grid on the current screen
grid = session.find_by_id("wnd[0]/shellcont/shell")

# Read all rows
for row in range(grid.row_count):
    for col in grid.column_order:
        print(grid.get_cell_value(row, col), end="\t")
    print()
```

### Navigate a tree

```python
from sapsucker.components.tree import GuiTree

tree = session.find_by_id("wnd[0]/shellcont/shell/shellcont[1]/shell/shellcont[2]/shell")

key = tree.top_node
print(tree.get_node_text_by_key(key))

if tree.is_folder(key):
    tree.expand_node(key)
```

### Fill a form

```python
# Set a text field value
session.find_by_id("wnd[0]/usr/ctxtRS38M-PROGRAMM").text = "RSPARAM"

# Press F8 (Execute)
session.find_by_id("wnd[0]").send_v_key(8)
```

### Context manager

```python
with SapGui.connect() as app:
    session = app.connections[0].sessions[0]
    print(session.info.user)
# All connections closed automatically
```

See the `examples/sapsucker/` directory for complete runnable scripts.

## Architecture

sapsucker wraps the SAP GUI Scripting COM API as a hierarchy of typed Python classes:

```
GuiApplication
  └── GuiConnection
       └── GuiSession
            └── GuiMainWindow
                 ├── GuiToolbar
                 ├── GuiMenubar
                 ├── GuiStatusbar
                 └── GuiUserArea
                      ├── GuiTextField, GuiLabel, GuiButton, ...
                      ├── GuiTableControl (classic dynpro tables)
                      ├── GuiGridView (ALV grids)
                      ├── GuiTree (tree controls)
                      ├── GuiTabStrip → GuiTab
                      └── GuiAbapEditor / GuiTextedit
```

Elements are discovered via `session.find_by_id(sap_id)`, which returns the
correct typed wrapper automatically (e.g., `GuiGridView` for an ALV grid,
`GuiTree` for a tree control). The factory dispatches on `TypeAsNumber` and
`SubType` COM properties.

## Thread Safety

COM objects use the Single-Threaded Apartment (STA) model. All calls to a
given SAP GUI session must happen from the same thread that called
`pythoncom.CoInitialize()`. See the `_com.py` module docstring for details
and an `asyncio.to_thread()` example.

## API Overview

| Class             | Description                                               |
| ----------------- | --------------------------------------------------------- |
| `SapGui`          | Entry point — `SapGui.connect()` returns `GuiApplication` |
| `GuiApplication`  | Root object, manages connections                          |
| `GuiConnection`   | A TCP connection to an SAP server                         |
| `GuiSession`      | A session (mode) within a connection                      |
| `GuiMainWindow`   | The main SAP window                                       |
| `GuiTextField`    | Single-line input field                                   |
| `GuiButton`       | Push button                                               |
| `GuiCheckBox`     | Checkbox                                                  |
| `GuiComboBox`     | Dropdown list                                             |
| `GuiGridView`     | ALV grid (most common data display)                       |
| `GuiTableControl` | Classic dynpro table                                      |
| `GuiTree`         | Tree control (simple, list, or column)                    |
| `GuiAbapEditor`   | ABAP source code editor                                   |
| `GuiStatusbar`    | Status bar at bottom of window                            |

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

```bash
# Clone and install dev dependencies
git clone https://github.com/Hochfrequenz/sapwebgui.mcp.git
cd sapwebgui.mcp
pip install -e ".[dev]"

# Run unit tests (no SAP required)
pytest unittests/sapgui/ -v

# Run integration tests (requires SAP GUI + credentials in .env)
pytest unittests/sapgui/ -k integration -v

# Format
black src/ unittests/ examples/
isort src/ unittests/ examples/
```

## License

MIT
