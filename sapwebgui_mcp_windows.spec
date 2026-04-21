# -*- mode: python ; coding: utf-8 -*-
"""Canonical PyInstaller spec for the Windows .exe build.

Invoked by ``tox -e build_executable``. Two variants are produced by the CI
jobs in ``.github/workflows/build_executable.yml`` — they differ only in
whether ``.env.production`` is present on disk at build time:

* **Public** (``sapwebgui_mcp_windows.exe``) — ``.env.production`` absent.
  No remote-logging defaults are baked into the binary. Papertrail stays
  off unless the user sets ``PAPERTRAIL_HOST`` + ``PAPERTRAIL_PORT`` in
  their own ``.env`` / environment.
* **With remote logging** (``sapwebgui_mcp_windows_with_remote_logging.exe``)
  — the CI job writes ``.env.production`` from repository secrets before
  running ``pyinstaller``, so the resulting binary ships with Hochfrequenz's
  Papertrail endpoint as the default destination. End users can still
  override by putting an empty ``PAPERTRAIL_HOST=`` in their own ``.env``.

Set ``SAPWEBGUI_BUILD_NAME`` to control the output filename (defaults to
``sapwebgui_mcp_windows`` — public variant).
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# --- CLI flags from the former tox command line, preserved here ---
# - fastmcp uses importlib.metadata.version("fastmcp") at import time
# - fastmcp -> docket -> fakeredis needs commands.json data files
# - fastmcp -> docket -> fakeredis -> lupa needs Lua runtime submodules
# - sapwebguimcp ships js/, prompts/, data/, workflows/ non-Python files
# If fastmcp drops the docket dependency, the lupa/fakeredis lines can go.
datas = []
hiddenimports = []
datas += collect_data_files("fakeredis")
datas += collect_data_files("sapwebguimcp")
datas += copy_metadata("fastmcp")
hiddenimports += collect_submodules("lupa")

# Optional bundled defaults. Only included when ``.env.production`` exists on
# disk at build time — the public CI job deliberately does not create it, so
# the public .exe ships with no network-destination defaults.
if os.path.exists(".env.production"):
    datas += [(".env.production", ".")]

name = os.environ.get("SAPWEBGUI_BUILD_NAME", "sapwebgui_mcp_windows")

a = Analysis(
    ["src\\sapwebguimcp\\server.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
