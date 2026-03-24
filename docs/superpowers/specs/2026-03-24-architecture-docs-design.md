# Architecture Documentation

**Date:** 2026-03-24
**Status:** Approved

## Goal

Add `ARCHITECTURE.md` to the repo root so new developers (both internal Hochfrequenz devs and external contributors) can understand the codebase structure without reading 10+ source files. Uses mermaid diagrams for visual clarity (renders natively on GitHub).

## Contents

1. **SAP context** — one paragraph for non-SAP devs (transactions, tcodes, OK-code, status bar)
2. **Layers diagram** (mermaid) — MCP client → server → tools → backend manager → protocol → backends
3. **Request flow diagram** (mermaid) — sequence diagram showing a tool call end-to-end
4. **Layer descriptions** — 2-3 sentences per layer with key files
5. **How to add a new transaction tool** — step-by-step with file locations, referencing SE16 as canonical example
6. **Test organization** — which tests need SAP, which don't, how skip markers work
7. **Configuration groups** — env vars grouped by purpose with one-line descriptions

## What's NOT included

- Detailed API docs (already in docstrings)
- README duplication (link to it)
- Tool-by-tool documentation (just the pattern)
- Refactoring proposals

## File

`ARCHITECTURE.md` in repo root, next to README.md and CONTRIBUTING.md.
