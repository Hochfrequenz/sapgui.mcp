# Split into two repositories: SAP GUI (COM) and WebGUI

Status: plan, not started. Tracking issue: to be created from this plan.

## Goal

Two independent, clean projects, each with its own README, docs and CI/CD:

|              | **COM project** (this repo, `Hochfrequenz/sapgui.mcp`)                                                | **WebGUI project** (new repo)                                                       |
| ------------ | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Backend      | SAP GUI for Windows via COM scripting (sapsucker)                                                     | SAP WebGUI via Playwright and Chrome                                                |
| Platforms    | Windows only                                                                                          | Windows, macOS, Linux                                                               |
| Distribution | Windows binary only (public and remote-logging variant). No Docker, no macOS build, no Python package | Binaries and Docker image, as today                                                 |
| Keeps        | Name, issues, releases, history                                                                       | Full history up to the fork tag                                                     |
| Maintenance  | Actively developed                                                                                    | Maintained if a maintainer picks it up, otherwise it goes stale. The README says so |

### Why

- **Different capabilities.** COM has stable element IDs, tree controls, breakpoints, `sap_run_script` and direct grid access. WebGUI runs on any OS without an SAP GUI install, but reads HTML and ARIA snapshots. Most tools already need a different strategy per backend.
- **Parity tax.** Every new backend method is implemented twice, every tool carries two paths, and every PR needs live tests on both backends. The WebGUI backend is behind (20 open `webgui-only` issues), and keeping it in step slows the COM backend down.
- **Setup complexity.** One README serves Windows SAP GUI users and macOS, Docker and CDP-proxy users. The COM project shrinks to "download the exe, write `systems.json`, register it in the MCP client".

### Accepted costs

- **Copy, then diverge.** Shared code (language packs, `systems.json` handling, result models, offline catalogs) is copied at the fork and evolves separately. A fix to SAP behaviour found on one side, such as a dialog text, has to be ported by hand. No shared library is extracted.
- The WebGUI project may go stale. That is acceptable.

## Approach: snapshot fork, then prune both sides

1. **Prepare** this repo so that each backend's code can be deleted by file or by function.
2. **Fork** the WebGUI repo from a tagged release in which both backends were live-tested.
3. **Prune** this repo of WebGUI and the new repo of desktop, each in staged PRs that are live-tested against their own backend only.

Rejected alternatives:

- **Move each backend's code into separate modules before the fork.** Same end state, but every move needs live tests on both backends, and both repos then delete those modules anyway. The preparation below only untangles the few spots where both paths are interleaved.
- **One repo with two distributions.** Simplifies setup, but not development, since every tool keeps both paths and both test sets.
- **Extract a shared library** (language packs, models). Every change would need a library release first. Only worth it if the WebGUI project stays actively developed.

### Earlier groundwork

#681–#686 (PRs #687–#693) already removed dead code, untangled `backend/types.py`, moved backend-specific models into their backends, added split markers to the config models and documented the 22 result types that both backends use. Below the tool layer, the code is ready for the split.

## Current state (measured on `main` at ff7a8f1, 2026-11-17)

- **There is no backend protocol class.** Tools are typed `WebGuiBackend | DesktopBackend`. `ARCHITECTURE.md` still describes a `SapUiBackend` protocol in `backend/protocol.py` and a `tools/_backend_utils.py`, but neither file exists.
- **The tools are mostly split already.** 22 tool modules mention the backend type 1–6 times each. Most transaction tools dispatch once, for example `se09_tools.py:521`, `se16_tools.py:1159` and `sm37_tools.py:472`. The other hits are `isinstance` narrowing inside `_…_desktop` functions, or three-line `if not desktop: check_popup` guards, for example `sap_tools.py:1540`. Both kinds disappear naturally when one side is deleted.
- **What is really interleaved** is a short list:

    - `sap_tools.py`: `sap_transaction` (447–471), `sap_get_shortcuts` (1156) and `sap_lookup_fields` (965–972)
    - `abapgit_tools.py`: 181, 238 and 923
    - `se37_tools.py:64`
    - `field_helpers.py:78`

    Of the other helpers, `desktop_wait_predicates` and `table_helpers` are desktop-only, `screen_state_helpers` is WebGUI-only, and `edit_helpers` is neutral.

- **Registration per backend.** `server.py:357-366` registers some tools for one backend only:
    - **desktop only:** `com_tools`, `tree_tools`, `script_tools`, sandbox resources. `breakpoint_tools` is registered for both but works only on desktop.
    - **WebGUI only:** `browser_tools`, `se37_edit_tools`, `quick_report_tools`.
- **`sap_se37_edit` and `sap_quick_report` have no desktop implementation.** Unless they are ported (decision D3), the COM project loses them.
- **`BACKEND_TYPE` defaults to `webgui`** (`models/config.py:202`). A user who never set it runs WebGUI today, and the COM project would switch them to desktop silently.
- **Tests.** About 87 test modules sit in the `unittests/` root, a mix of desktop-specific, WebGUI-specific and shared ones. The test directories depend on each other:
    - `unittests/desktop/test_spro_integration.py:11` imports `unittests.webgui.testdata.lang_test`.
    - Three tests in `unittests/lang/` read `unittests/webgui/testdata/html_snapshots`.
    - `unittests/test_abapgit_repo_skip.py:8-9` imports `unittests.desktop.conftest`.
    - `unittests/conftest.py:130-131` and `test_live_marker.py:18` hard-code both directories.
    - `.gitmodules` puts both abapGit test repositories under `unittests/webgui/abapgit_repos/`.
    - The release smoke test of the binary is `unittests/webgui/smoke_test_exe.py` (run by `build_executable.yml`).
- **CI runs on Ubuntu**, where the desktop unit tests skip (`unittests.yml`, `coverage.yml`, `pythonlint.yml`).
- **Language packs carry no backend tag.** Nothing marks which texts only one backend reads, and no test finds unused texts. WebGUI-only language machinery:
    - `for_js()` in `lang/text.py`
    - `unittests/lang/node_runner.py`, `test_text_js.py` and `test_js_pack_guard.py`
    - `JS_DIR` in `test_no_ui_literals.py`
    - the `prettier src/**/*.js` script in `package.json`
- **`breakpoint_tools.py` is frozen.** `unittests/test_no_ui_literals.py:711-713` pins it to `lang_baseline.json` (#1025), so it is not touched before the fork.
- **Publishing.** The PyPI upload in `python-publish.yml` is commented out. That workflow only builds the package and pushes the Docker image, whose name comes from `github.repository`.
- **Places that name this repository** and must change in the WebGUI repo:
    - the feedback-issue target, `models/config.py:306`
    - `pyproject.toml` URLs
    - the binary names `sapgui_mcp_*`
    - the MCP server name (`server.py:308`)
    - issue links in code comments

## Decisions to settle in the tracking issue (before issue 5)

| #   | Decision                                                                                       | Recommendation                                                                                                                                                                                                |
| --- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Name of the WebGUI repo, Python package, entry point and binaries                              | Repo `Hochfrequenz/sapwebgui.mcp`, package `sapwebguimcp`, binaries `sapwebgui_mcp_*`. Different names prevent confusion in MCP client configs and release downloads                                          |
| D2  | Version numbers                                                                                | Fork tag = the next minor release of this repo (e.g. `v0.20.0`). This repo continues from there. The WebGUI repo starts at the same version under its new name                                                |
| D3  | `sap_se37_edit` and `sap_quick_report` on desktop                                              | Do not block the split. Open desktop feature issues and port them after the split, desktop first                                                                                                              |
| D4  | Users who run WebGUI today: with `BACKEND_TYPE=webgui`, or with it unset (the current default) | The COM binary starts on desktop. If `BACKEND_TYPE=webgui`, `SAP_URL` or `CDP_URL` is set, it logs a warning and adds a notice to the server instructions that points to the WebGUI project. It does not fail |
| D5  | Maintenance status of the WebGUI repo                                                          | README notice: "maintainer wanted, may not receive updates" until someone takes it over                                                                                                                       |

## Issues, in order

The numbers give the order. Issues with the same number and different letters can run in parallel. Live tests share one SAP connection and need the VPN, so live-tested PRs run one after another.

Model columns: who implements and who reviews. Sonnet is the default. Opus reviews behaviour-preserving changes to central paths. Haiku does purely mechanical work that produces no public text.

### Phase 1: Preparation in this repo

| #   | Issue                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Depends on    | Live tests                               | Implement / review         |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------- | ---------------------------------------- | -------------------------- |
| 0   | **Tracking issue**, labelled with the existing `desktop-webgui-split` label. It links this plan and #681–#686, lists the decisions D1–D5 and all issues below                                                                                                                                                                                                                                                                                                                                          | –             | –                                        | me / –                     |
| 1   | **Triage open issues by backend.** Add a `desktop-only` and a `both-backends` label next to the existing `webgui-only`, so that every open issue carries exactly one. This makes the issue transfer in issue 6 mechanical                                                                                                                                                                                                                                                                              | 0             | –                                        | haiku / sonnet             |
| 2a  | **Sort tests and test assets by backend** (offline only; details below). No test logic changes. Acceptance: the offline unit suite collects the same number of tests before and after, and no import or path leads from `unittests/desktop` into `unittests/webgui` or back                                                                                                                                                                                                                            | 0             | none                                     | sonnet / sonnet            |
| 2b  | **Untangle the interleaved spots** listed under "Current state": `sap_transaction`, `sap_get_shortcuts`, `sap_lookup_fields`, `abapgit_tools.py` 181/238/923, `se37_tools.py:64`, `field_helpers.py:78`. Each gets one dispatch to a `_desktop` and a `_webgui` function. Behaviour unchanged. Not touched: the popup guards and the `isinstance` narrowing (both go when a side is deleted) and `breakpoint_tools.py` (#1025). Fix the stale protocol description in `ARCHITECTURE.md` in the same PR | 0             | both backends, both systems              | sonnet / opus              |
| 2c  | **Tag language-pack texts by consumer** (offline). Mark each leaf in `lang/schema.py` as desktop, WebGUI or both, or add a test that lists the keys each backend reads, so that issues 10 and 18 can delete texts mechanically                                                                                                                                                                                                                                                                         | 0             | none                                     | sonnet / opus              |
| 3   | **Desktop feature issues for the WebGUI-only tools** (decision D3): one issue each for `sap_se37_edit` and `sap_quick_report` on desktop. Only the issues; implementing them is post-split work                                                                                                                                                                                                                                                                                                        | 0             | –                                        | me / –                     |
| 4   | **Fork-point release.** Run the full live suite on both backends and both systems. Fix every failure or link it to an issue. Tag the release that becomes the fork point, with release notes that announce the split                                                                                                                                                                                                                                                                                   | 1, 2a, 2b, 2c | full suites, both backends, both systems | sonnet runs and checks / – |

What issue 2a moves:

- Desktop-specific tests from the `unittests/` root into `unittests/desktop/`, and WebGUI-specific ones into `unittests/webgui/`. Shared tests stay in the root.
- Shared test assets to a neutral place, for example `unittests/testdata/`: the `lang_test` data, the HTML snapshots the `unittests/lang/` tests read, and the abapGit submodules (`.gitmodules`).
- Shared fixtures out of `unittests/desktop/conftest.py`, so that no test imports another directory's conftest.
- `smoke_test_exe.py` to a neutral path, so that deleting `unittests/webgui/` does not break the release build.
- `unittests/conftest.py` and `test_live_marker.py`, adjusted to the new paths.

Acceptance for the end of phase 1:

- Every remaining backend branch in `tools/` is a single dispatch, an `isinstance` narrowing or a popup guard.
- Every backend-specific test sits in `unittests/desktop/` or `unittests/webgui/`.
- Every language-pack text says which backend uses it.
- Every open issue carries one backend label.

### Phase 2: Fork

| #   | Issue                                                                                                                                                                                                                                                                                                                                                                                                                 | Depends on | Implement / review |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ------------------ |
| 5   | **Create the WebGUI repo** from the fork tag with full history (`git clone`, then push the tag's commit as `main` and all tags; not a GitHub fork, so that it is a standalone repo). Configure branch protection, required checks, Copilot review, Dependabot, labels and secrets (GHCR for the Docker image, remote logging if kept). This needs org admin rights: the user does it, an agent prepares the checklist | 4, D1      | user + sonnet / –  |
| 6   | **Move issues.** Transfer every `webgui-only` issue to the new repo (`gh issue transfer`). For every `both-backends` issue, open a copy in the new repo with a link back. Comment in both places. These are public posts, so the leak rules apply                                                                                                                                                                     | 1, 5       | sonnet / sonnet    |

### Phase 3a: Prune this repo to the COM project (desktop first)

PRs that change runtime code are live-tested on the desktop backend only, on both systems. The offline suite and `mypy --strict` must pass on every PR.

| #   | Issue                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Depends on              | Live tests            | Implement / review |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- | --------------------- | ------------------ |
| 7   | **Fix the backend to desktop.** Remove `BACKEND_TYPE` and its default, the backend selection in `backend/manager.py`, the CDP check (`server.py:105`) and the WebGUI parts of the server instructions (`server.py:278`) and of `sap_login_impl.py:63`. Register only the desktop tool list. Implement D4                                                                                                                                                                             | 6                       | desktop, both systems | sonnet / opus      |
| 8   | **Delete the WebGUI paths in the tools**: the `_webgui` functions from 2b, the popup guards, the `isinstance` narrowing, the WebGUI-only helpers (`screen_state_helpers`), `browser_tools`, `se37_edit_tools`, `quick_report_tools`, the `getattr` duck typing in `session_tools.py:46-138`, and the WebGUI parts of `sap_list_connections_impl.py`. Collapse the `WebGuiBackend \| DesktopBackend` annotations to `DesktopBackend`                                                  | 7                       | desktop, both systems | sonnet / sonnet    |
| 9   | **Delete the WebGUI backend**: `backend/webgui/`, its imports in `backend/__init__.py` and `backend/manager.py`, the WebGUI models (`models/__init__.py:27-28`, `alv_models.py:17`), the WebGUI settings in `models/config.py`, `logging_config.py:156`, `unittests/webgui/`, Playwright, `nginx-cdp-proxy.conf` and the WebGUI entries in `.env.example`. The release smoke test runs against the desktop binary only                                                               | 8                       | desktop, both systems | sonnet / opus      |
| 10  | **Language-pack cleanup**: delete the texts tagged WebGUI-only (2c), `for_js()`, the Node runner and the JS pack tests, `JS_DIR` and the JS prettier script                                                                                                                                                                                                                                                                                                                          | 9, 2c                   | desktop, both systems | sonnet / sonnet    |
| 11  | **CI/CD for the COM project.** Run unit tests, coverage and mypy on `windows-latest`, so that the desktop tests stop skipping. `build_executable.yml`: Windows only (public and remote-logging exe), no macOS, no Chrome matrix. Delete `python-publish.yml` (Docker image and package build), `Dockerfile`, `docker-compose.yml`, the `playwright install` steps, and the Docker ecosystem in Dependabot. Clean up `pyproject.toml` (description, keywords, stale per-file ignores) | 9                       | exe smoke test only   | sonnet / sonnet    |
| 12  | **Docs for the COM project.** `README.md` (one setup path: exe, `systems.json`, MCP client; a pointer to the WebGUI project), `ARCHITECTURE.md`, `CONTRIBUTING.md`, `docs/SAP_TEST_PREREQUISITES.md`, `scripts/README.md`, `tools/README.md`, `models/README.md`, `data/sap_knowledge.md`, `skills/examples/general_navigation.md`, `CLAUDE.md` and the `readme-demo` skill. Remove the Docker, CDP-proxy, Chrome and macOS sections. `docs/plans` and `docs/design` stay as history | 9 (11 for the CI parts) | none                  | sonnet / sonnet    |
| 13  | **First COM-only release**, with release notes that explain the split and tell WebGUI users where to go                                                                                                                                                                                                                                                                                                                                                                              | 10, 11, 12              | exe smoke test        | me / –             |

### Phase 3b: Prune the new repo to the WebGUI project

Runs in parallel with phase 3a, but desktop first if capacity is short. PRs that change runtime code are live-tested on the WebGUI backend only, on both systems. These issues are created in the new repo once it exists; until then the tracking issue lists them.

| #   | Issue                                                                                                                                                                                                                                                                                                                    | Depends on               | Live tests                     | Implement / review |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------ | ------------------------------ | ------------------ |
| 14  | **New identity** (D1), without the package rename: feedback-issue target (`models/config.py:306`), `pyproject.toml` URLs, binary names, MCP server name, the issue links in comments that matter                                                                                                                         | 5                        | none                           | sonnet / sonnet    |
| 15  | **Fix the backend to WebGUI.** Remove `BACKEND_TYPE` and the backend selection. Register only the WebGUI tool list: unregister `com_tools`, `tree_tools`, `script_tools`, `breakpoint_tools` and the sandbox resources. Delete the breakpoint baseline test in `test_no_ui_literals.py` together with its baseline entry | 14                       | WebGUI, both systems           | sonnet / opus      |
| 16  | **Delete the desktop paths in the tools**: the `_desktop` functions, the desktop-only helpers (`desktop_wait_predicates`, `table_helpers`), the popup guards and the narrowing. Collapse the annotations to `WebGuiBackend`                                                                                              | 15                       | WebGUI, both systems           | sonnet / sonnet    |
| 17  | **Delete the desktop backend**: `backend/desktop/`, the desktop settings and models, `unittests/desktop/`, `sapsucker` and `pywin32`, and the desktop-only scripts (`scripts/validate_pr_629.py`, `explore_issue_717.py`, `probe_*.py`)                                                                                  | 16                       | WebGUI, both systems           | sonnet / opus      |
| 18  | **Language-pack cleanup**: delete the texts tagged desktop-only (2c)                                                                                                                                                                                                                                                     | 17                       | WebGUI, both systems           | sonnet / sonnet    |
| 19  | **Package rename** `sapguimcp` → the D1 name, after the deletions, so that it touches only surviving files                                                                                                                                                                                                               | 18                       | offline suite + exe smoke test | haiku / sonnet     |
| 20  | **CI/CD for the WebGUI project**: builds under the new names, Docker image, release workflow, secrets                                                                                                                                                                                                                    | 19                       | exe smoke test                 | sonnet / sonnet    |
| 21  | **Docs for the WebGUI project**: README with the maintenance notice (D5), `ARCHITECTURE.md`, `CONTRIBUTING.md`, test prerequisites, `CLAUDE.md`, MCP server instructions                                                                                                                                                 | 19 (20 for the CI parts) | none                           | sonnet / sonnet    |
| 22  | **First release of the WebGUI project**                                                                                                                                                                                                                                                                                  | 20, 21                   | exe smoke test                 | user or maintainer |

### Out of scope

- Introducing or removing a backend abstraction in either project. Each project uses its one backend class directly.
- Porting `sap_se37_edit` and `sap_quick_report` to desktop: only the issues are created (issue 3).
- Fixing open `webgui-only` bugs before the fork. They move with issue 6.
- Changing popup handling on either side. Issues 8 and 16 only delete the other backend's guards.

## Order at a glance

```
0 ─┬─ 1 ──┐
   ├─ 2a ─┤
   ├─ 2b ─┼─ 4 ─ 5 ─ 6 ─┬─ 7 ─ 8 ─ 9 ─┬─ 10 ─┬─ 13          (this repo)
   ├─ 2c ─┘             │             ├─ 11 ─┤
   └─ 3                 │             └─ 12 ─┘
                        └─ 14 ─ 15 ─ 16 ─ 17 ─ 18 ─ 19 ─┬─ 20 ─┬─ 22   (WebGUI repo)
                                                        └─ 21 ─┘
```

Issue 14 only needs the new repo (issue 5); it is drawn after 6 for readability.

## Risks

- **Prep PRs collide with feature work.** 2a moves many test files and 2b touches central tools. Keep each PR small and merge it quickly.
- **Live-test load.** 2b and 4 need live tests on both backends and both systems through one SAP connection, with the VPN up. After the fork, each side tests only its own backend.
- **Hidden cross-dependencies** surface during issues 9 and 17. `mypy --strict` and the offline unit suite catch them, so both must pass on every prune PR.
- **Users switched silently.** Everyone who runs the Windows binary without setting `BACKEND_TYPE` uses WebGUI today. D4, the warning in issue 7 and the release notes of issue 13 make the switch visible.
- **Issue references in code comments** (`#123`) point to this repo's issues. In the WebGUI repo they become ambiguous; issue 14 turns the ones that matter into full links.
