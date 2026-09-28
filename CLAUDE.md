# CLAUDE.md

Guidance for AI coding agents working in this repository.

## Project Documentation

This file only holds agent-specific rules. For everything else, read the existing documentation:

- [`README.md`](README.md) — what the server does, installation, `systems.json` setup, and the
  configuration reference
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — development setup, running unit and integration tests,
  HTML snapshot testing, and code style
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — layers, request flow, file organization, and how to add
  a new transaction tool
- [`docs/SAP_TEST_PREREQUISITES.md`](docs/SAP_TEST_PREREQUISITES.md) — everything a fresh SAP
  system needs before the integration tests can run (permissions, configuration, test objects)
- [`scripts/README.md`](scripts/README.md) — development and maintenance scripts that are not
  part of the runtime server

## Public Repository — No Internal Data

This repository and its issue tracker are **public**. Nothing that identifies our internal
environment may land there — that covers commits, source, docs, test fixtures, issue titles and
bodies, issue comments, PR descriptions, and anything a workflow writes on our behalf.

Never publish:

- Hostnames, FQDNs, IP addresses, or ports of internal systems — SAP or otherwise, including
  auth and identity infrastructure
- The internal system aliases defined in `systems.json`, including per-client and proxy
  variants, when used to name a system in prose
- Anything that embeds a system ID: transport and task numbers (`<SID>K9…`), lock keys, SAP GUI
  window titles, or log lines carrying a host. Write `<request>` / `<task>` instead — an outside
  reader cannot run a reproducer against our request numbers anyway
- Object names in our own or a partner's registered SAP namespace (`/XXX/…`). The namespace
  identifies its owner, the object name usually identifies the business domain, and a partner
  namespace additionally discloses which add-ons we run. Use a neutral placeholder such as
  `/ABC/CL_EXAMPLE`
- An inventory of our landscape: client numbers, which industry or partner add-ons are
  installed, or references to internal wikis and ticket systems. Saying that a finding was
  reproduced "on both systems" is fine; enumerating the landscape is not
- Credentials or tokens of any kind, and client numbers tied to a named system
- Local filesystem paths containing a user name, and SAP logon IDs
- Customer, project, or other company-internal identifiers

Name an SAP system by **type and release level** instead, which is also more useful to an outside
reader than an alias:

- `SAP S/4HANA 2025, on-premise (SAP_BASIS 816, S4CORE 109)`
- `SAP ERP 6.0 EHP8 (SAP_BASIS 750, SAP_APPL 618)`

Read the levels from the system rather than guessing: component levels from `CVERS`
(`SELECT COMPONENT, RELEASE, EXTRELEASE FROM CVERS WHERE COMPONENT IN ('SAP_BASIS', 'SAP_APPL',
'S4CORE')` — note that `LIKE 'SAP%'` silently misses `S4CORE`), and the marketing release from
`PRDVERS` (`SELECT NAME, VERSION, INSTSTATUS, DESCRIPT FROM PRDVERS`, where `INSTSTATUS = '+'`
marks the active version). Both are basis metadata, not business data. Publish the release level
only — never the support-package level (the `EXTRELEASE` column, e.g. `SP 0034`), which maps
directly onto published SAP Security Notes and so states which fixes are not yet applied. Where
several systems appear in one document, introduce the type/release form once and refer back to
it ("the ECC system", "on both systems").

The one allowed exception is a literal value the code has to hold because an integration test
keys off one system's real behaviour (for example an expected `system_name` in a live-test
fixture). The prose, comments and commit messages _around_ that value are not covered — write
"the S/4HANA system", not the alias. Unit-test fixture strings are not covered either; use
`sysA` / `sysB`. This section is bound by the same rule: where an example is needed, write
`<alias>`.

`.mcp.json` is **not** an exception. Credentials belong in `systems.json` or environment
variables (see [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config)), but a local
`.mcp.json` may still hold them. It is git-ignored and must never be committed at all.

Before pushing, grep the diff for the shapes that matter — an internal domain suffix, a
`<SID>K9…` transport number, a `/XXX/` namespace prefix — rather than for the alias names, so the
guard itself does not leak them.

When you find internal data already published, redact it in place (edit the issue body, or open a
PR) rather than only noting it. For a hostname, credential or logon ID, assume the value is
already disclosed regardless: editing a body does not remove it from the edit history or from the
notification e-mails that already went out, so rotate or renumber it instead of trusting the edit.
