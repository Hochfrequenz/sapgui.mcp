# Design: Fix README Environment Variable Documentation

**Date:** 2026-02-20
**Goal:** Fix inaccuracies in README.md — make MCP registration and environment variables clear and complete across all three deployment sections.

## Problem

1. No upfront explanation of where to register the MCP server (`.mcp.json` vs `claude_desktop_config.json`)
2. EXE section only shows 5 env vars — missing most optional ones
3. Dev/Python section only shows 3 env vars in config JSON
4. Docker section is the most complete but still incomplete
5. No required vs optional distinction anywhere
6. `GITHUB_PAT` shown without explanation of when it's needed
7. `AUDIT_LOG_DIR` shown in non-Docker paths where it's less relevant

## Design

### 1. MCP Registration Intro

Add a block **before** the three `<details>` sections, after "Choose one of these three approaches:":

> **Where to register the MCP server:**
>
> - **Claude Code** — add to `.mcp.json` in your project root (per-project config)
> - **Claude Desktop** — add to `claude_desktop_config.json` (global config, path varies by OS — shown in each section below)
>
> All three setup approaches below show you how to configure both.

### 2. EXE Section

- Add both Claude Desktop and Claude Code JSON configs
- Expand env vars to common set: `SAP_URL`, `SAP_USER`, `SAP_PASSWORD`, `SAP_MANDANT`, `SAP_LANGUAGE`, `GITHUB_PAT`
- Prose before JSON: "Required: SAP_URL, SAP_USER, SAP_PASSWORD, SAP_MANDANT. All other variables are optional — remove any you don't need."
- Note that `GITHUB_PAT` is only needed for `log_feedback` or abapGit
- Use `DE` as language in examples
- No `AUDIT_LOG_DIR` (non-Docker)
- Reference Configuration Reference for full list

### 3. Docker Section

- Keep the two sub-options (Claude Desktop + Claude Code)
- Expand `-e` args to common set: SAP credentials, `SAP_LANGUAGE`, `BROWSER_MODE`, `CDP_URL`, `AUDIT_LOG_DIR`, `GITHUB_PAT`
- Same prose pattern for required vs optional
- Keep `AUDIT_LOG_DIR` (Docker maps a volume)
- Use `DE` as language in examples
- Add note about `GITHUB_PAT` being optional
- Reference Configuration Reference for full list

### 4. Dev/Python Section

- Add both Claude Desktop and Claude Code JSON configs
- Expand env vars to common set (no `AUDIT_LOG_DIR`)
- Note: no CDP proxy needed when running Python locally
- Same prose pattern
- Reference Configuration Reference for full list

### 5. Configuration Reference Table

- Add missing env vars: `BROWSER_TYPE`, `BROWSER_HEADLESS`, `GITHUB_USER`, `ABAPGIT_PAT`, `PAPERTRAIL_HOST`, `PAPERTRAIL_PORT`, `LOG_FORMAT`, `LOG_LEVEL`
- Add a "Required" column to distinguish required from optional
- Keep as single source of truth for all variables

## Env Vars Shown in Setup Sections (common set)

| Variable        | Required    | In EXE          | In Docker       | In Dev          |
| --------------- | ----------- | --------------- | --------------- | --------------- |
| `SAP_URL`       | Yes         | Yes             | Yes             | Yes             |
| `SAP_USER`      | Yes         | Yes             | Yes             | Yes             |
| `SAP_PASSWORD`  | Yes         | Yes             | Yes             | Yes             |
| `SAP_MANDANT`   | Yes         | Yes             | Yes             | Yes             |
| `SAP_LANGUAGE`  | No          | Yes             | Yes             | Yes             |
| `BROWSER_MODE`  | No          | No (default ok) | Yes             | Yes             |
| `CDP_URL`       | Conditional | No (default ok) | Yes             | Yes             |
| `AUDIT_LOG_DIR` | No          | No              | Yes             | No              |
| `GITHUB_PAT`    | No          | Yes (with note) | Yes (with note) | Yes (with note) |

All other vars (`BROWSER_TYPE`, `BROWSER_HEADLESS`, `GITHUB_USER`, `GITHUB_REPO`, `ABAPGIT_PAT`, `PAPERTRAIL_*`, `LOG_*`) are in the Configuration Reference table only.

## Principles

- Each section is self-contained and copy-pasteable
- Required vs optional is always clear via prose
- `DE` used as language in all examples
- Always reference Configuration Reference for the full list
- No `AUDIT_LOG_DIR` outside Docker (less relevant without volume mounts)
