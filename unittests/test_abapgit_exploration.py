"""
Exploratory tests for abapGit integration.

These tests help us understand the abapGit UI structure to build
automated pull/push tools.

Run with: pytest unittests/test_abapgit_exploration.py -v -s
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapwebguimcp.models import (
    AbapGitActionResult,
    DiscoveredButtons,
    FormFieldsResult,
    LoginResult,
    ScreenText,
    SnapshotResult,
    TableData,
    TransactionResult,
)

from .conftest import call_tool_typed, get_html_content

EXPLORATION_DIR = Path(__file__).parent / "testdata" / "abapgit_exploration"


async def capture_snapshot(
    client: ClientSession,
    name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for analysis."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.snapshot

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{name}_{language}.yaml"
    filepath = EXPLORATION_DIR / filename

    if not filepath.exists() or overwrite:
        EXPLORATION_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"\nSaved snapshot: {filepath}")

    return yaml_content


async def capture_screen_text(
    client: ClientSession,
    name: str,
    overwrite: bool = False,
) -> ScreenText:
    """Capture screen text for analysis."""
    result = await call_tool_typed(client, "sap_get_screen_text", {}, ScreenText)

    # Build text representation
    lines = [
        f"Title: {result.title}",
        f"Status: {result.status_bar}",
        f"Tabs: {result.tabs}",
        f"Labels: {result.labels}",
        f"Buttons: {result.buttons}",
        f"Table Headers: {result.table_headers}",
        f"Main Content: {result.main_content}",
    ]
    text_content = "\n".join(lines)

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{name}_{language}.txt"
    filepath = EXPLORATION_DIR / filename

    if not filepath.exists() or overwrite:
        EXPLORATION_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(text_content, encoding="utf-8")
        print(f"\nSaved screen text: {filepath}")

    return result


async def capture_html(
    client: ClientSession,
    name: str,
    selector: str | None = None,
    overwrite: bool = False,
) -> str:
    """Capture HTML content for analysis."""
    html_content = await get_html_content(client, selector=selector)

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{name}_{language}.html"
    filepath = EXPLORATION_DIR / filename

    if not filepath.exists() or overwrite:
        EXPLORATION_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(html_content, encoding="utf-8")
        print(f"\nSaved HTML: {filepath}")

    return html_content


# =============================================================================
# Exploration Tests - Run these manually to understand abapGit UI
# =============================================================================


@pytest.mark.anyio
async def test_abapgit_open_transaction(sap_mcp_client: ClientSession) -> None:
    """Open ZABAPGIT and capture initial screen."""
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"
    print(f"\nLogged in as {login_result.user}")

    # Open ZABAPGIT
    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success, f"Transaction failed: {tx_result.error}"
    print(f"\nOpened transaction: {tx_result.tcode}")

    # Capture snapshots
    await capture_snapshot(sap_mcp_client, "zabapgit_initial", overwrite=True)
    await capture_screen_text(sap_mcp_client, "zabapgit_initial", overwrite=True)

    print("\n=== Initial abapGit screen captured ===")


@pytest.mark.anyio
async def test_abapgit_explore_html(sap_mcp_client: ClientSession) -> None:
    """Explore the HTML structure of abapGit (including iframe content)."""
    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Capture full page HTML
    html = await capture_html(sap_mcp_client, "zabapgit_full_page", overwrite=True)

    # Print iframe info
    if "iframe" in html.lower():
        print("\n=== Found iframe in page ===")
        # Count iframes
        import re
        iframes = re.findall(r'<iframe[^>]*>', html, re.IGNORECASE)
        print(f"Found {len(iframes)} iframe(s)")
        for i, iframe in enumerate(iframes):
            print(f"  iframe {i}: {iframe[:200]}...")


@pytest.mark.anyio
async def test_abapgit_explore_repo_list(sap_mcp_client: ClientSession) -> None:
    """Explore the repository list structure."""
    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Try to read table data (repos might be in a table/grid)
    table_result = await call_tool_typed(
        sap_mcp_client,
        "sap_read_table",
        {"max_rows": 50},
        TableData,
    )

    if table_result.success and table_result.rows:
        print(f"\n=== Found table with {len(table_result.rows)} rows ===")
        print(f"Columns: {table_result.columns}")
        for i, row in enumerate(table_result.rows[:5]):
            print(f"Row {i}: {row}")
    else:
        print(f"\nNo table found or empty: {table_result.error}")

    # Capture for analysis
    await capture_snapshot(sap_mcp_client, "zabapgit_repo_list", overwrite=True)
    await capture_screen_text(sap_mcp_client, "zabapgit_repo_list", overwrite=True)


@pytest.mark.anyio
async def test_abapgit_explore_buttons(sap_mcp_client: ClientSession) -> None:
    """Explore available buttons/actions in abapGit."""
    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Discover buttons
    buttons_result = await call_tool_typed(
        sap_mcp_client,
        "sap_discover_buttons",
        {},
        DiscoveredButtons,
    )

    print("\n=== Available buttons ===")
    for btn in buttons_result.buttons:
        print(f"  {btn.label}: selector={btn.selector}, shortcut={btn.shortcut}")


@pytest.mark.anyio
async def test_abapgit_explore_form_fields(sap_mcp_client: ClientSession) -> None:
    """Explore form fields in abapGit."""
    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Discover form fields
    fields_result = await call_tool_typed(
        sap_mcp_client,
        "sap_get_form_fields",
        {},
        FormFieldsResult,
    )

    print("\n=== Form fields ===")
    for field in fields_result.fields:
        print(f"  {field.label}: type={field.field_type}, value={field.value}")


@pytest.mark.anyio
async def test_abapgit_explore_iframe_content(sap_mcp_client: ClientSession) -> None:
    """Try to access the iframe content where abapGit UI lives."""
    from sapwebguimcp.models import EvaluateResult

    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Try to get iframe info via JavaScript
    js_script = """
    (() => {
        const iframes = document.querySelectorAll('iframe');
        const results = [];
        iframes.forEach((iframe, i) => {
            try {
                const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
                const bodyText = iframeDoc?.body?.innerText?.substring(0, 500) || 'no access';
                results.push({
                    index: i,
                    id: iframe.id,
                    src: iframe.src,
                    bodyPreview: bodyText
                });
            } catch (e) {
                results.push({
                    index: i,
                    id: iframe.id,
                    src: iframe.src,
                    error: e.message
                });
            }
        });
        return JSON.stringify(results, null, 2);
    })()
    """

    eval_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_script},
        EvaluateResult,
    )

    print("\n=== Iframe content exploration ===")
    print(eval_result.result)


@pytest.mark.anyio
async def test_abapgit_explore_repo_actions(sap_mcp_client: ClientSession) -> None:
    """Explore how to interact with a specific repo (pull/push buttons)."""
    from sapwebguimcp.models import EvaluateResult

    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Explore the repo list structure and find clickable elements
    js_script = """
    (() => {
        const iframe = document.querySelector('iframe#C116') || document.querySelector('iframe');
        if (!iframe) return JSON.stringify({error: 'No iframe found'});

        const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
        if (!iframeDoc) return JSON.stringify({error: 'Cannot access iframe document'});

        // Find all links/buttons in the iframe
        const links = Array.from(iframeDoc.querySelectorAll('a, button, [onclick], [role="button"]'));
        const linkInfo = links.slice(0, 50).map(el => ({
            tag: el.tagName,
            text: el.innerText?.substring(0, 100),
            href: el.href || null,
            onclick: el.getAttribute('onclick')?.substring(0, 100) || null,
            className: el.className?.substring(0, 100) || null,
            id: el.id || null
        }));

        // Find tables (repo list is likely in a table)
        const tables = Array.from(iframeDoc.querySelectorAll('table'));
        const tableInfo = tables.map((t, i) => ({
            index: i,
            rows: t.rows?.length || 0,
            firstRowText: t.rows?.[0]?.innerText?.substring(0, 200) || null
        }));

        // Find the repo entries specifically
        const repoRows = Array.from(iframeDoc.querySelectorAll('tr')).filter(
            tr => tr.innerText.includes('github.com') || tr.innerText.includes('git@')
        );
        const repoInfo = repoRows.map(tr => ({
            text: tr.innerText?.substring(0, 300),
            cells: Array.from(tr.cells || []).map(c => c.innerText?.substring(0, 50))
        }));

        return JSON.stringify({
            linkCount: links.length,
            links: linkInfo,
            tables: tableInfo,
            repos: repoInfo
        }, null, 2);
    })()
    """

    eval_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_script},
        EvaluateResult,
    )

    print("\n=== Repo list structure ===")
    import json
    result = json.loads(eval_result.result)

    print(f"\nFound {result.get('linkCount', 0)} links/buttons")
    print(f"\nTables: {result.get('tables', [])}")
    print(f"\nRepos found: {len(result.get('repos', []))}")
    for repo in result.get('repos', []):
        print(f"  - {repo.get('text', '')[:100]}...")

    print("\n\nFirst 10 links:")
    for link in result.get('links', [])[:10]:
        print(f"  {link.get('tag')}: {link.get('text', '')[:50]} | onclick={link.get('onclick')}")


@pytest.mark.anyio
async def test_abapgit_click_repo_menu(sap_mcp_client: ClientSession) -> None:
    """Try clicking on a repo to see the context menu (Pull/Push options)."""
    from sapwebguimcp.models import ClickResult, EvaluateResult

    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Find the arrow/menu button for a repo
    js_find_menu = """
    (() => {
        const iframe = document.querySelector('iframe#C116') || document.querySelector('iframe');
        if (!iframe) return JSON.stringify({error: 'No iframe found'});

        const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
        if (!iframeDoc) return JSON.stringify({error: 'Cannot access iframe document'});

        // Look for menu triggers (triangles/arrows next to repos)
        // In abapGit, there's usually a ▸ or similar for the context menu
        const menuTriggers = Array.from(iframeDoc.querySelectorAll('a, span, td'))
            .filter(el => el.innerText?.includes('▸') || el.innerText?.includes('►') ||
                         el.className?.includes('menu') || el.className?.includes('action'));

        return JSON.stringify({
            found: menuTriggers.length,
            triggers: menuTriggers.slice(0, 10).map(el => ({
                tag: el.tagName,
                text: el.innerText?.substring(0, 50),
                className: el.className,
                onclick: el.getAttribute('onclick')?.substring(0, 100),
                parentText: el.parentElement?.innerText?.substring(0, 100)
            }))
        }, null, 2);
    })()
    """

    eval_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_find_menu},
        EvaluateResult,
    )

    print("\n=== Menu triggers in abapGit ===")
    import json
    result = json.loads(eval_result.result)
    print(f"Found {result.get('found', 0)} potential menu triggers")
    for trigger in result.get('triggers', []):
        print(f"  {trigger}")


@pytest.mark.anyio
async def test_abapgit_find_pull_push_actions(sap_mcp_client: ClientSession) -> None:
    """Search for Pull and Push related elements in the abapGit UI."""
    from sapwebguimcp.models import EvaluateResult

    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Search for any element containing "pull" or "push"
    js_script = """
    (() => {
        const iframe = document.querySelector('iframe#C116') || document.querySelector('iframe');
        if (!iframe) return JSON.stringify({error: 'No iframe found'});

        const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
        if (!iframeDoc) return JSON.stringify({error: 'Cannot access iframe document'});

        // Get all text content
        const bodyText = iframeDoc.body?.innerText || '';

        // Find elements with pull/push in text or attributes
        const allElements = Array.from(iframeDoc.querySelectorAll('*'));
        const pullPushElements = allElements.filter(el => {
            const text = (el.innerText || '').toLowerCase();
            const attrs = el.outerHTML?.substring(0, 500).toLowerCase() || '';
            return text.includes('pull') || text.includes('push') ||
                   text.includes('stage') || text.includes('commit') ||
                   attrs.includes('pull') || attrs.includes('push');
        });

        // Get unique elements (avoid duplicates from nested elements)
        const seen = new Set();
        const unique = pullPushElements.filter(el => {
            const key = el.tagName + el.innerText?.substring(0, 50);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });

        return JSON.stringify({
            bodyTextPreview: bodyText.substring(0, 1000),
            pullPushElements: unique.slice(0, 20).map(el => ({
                tag: el.tagName,
                text: el.innerText?.substring(0, 100),
                className: el.className,
                onclick: el.getAttribute('onclick')?.substring(0, 150),
                href: el.href || null
            }))
        }, null, 2);
    })()
    """

    eval_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_script},
        EvaluateResult,
    )

    print("\n=== Pull/Push related elements ===")
    import json
    # Result might be double-encoded as string
    raw_result = eval_result.result

    # Parse until we get a dict
    while isinstance(raw_result, str):
        raw_result = json.loads(raw_result)
    result = raw_result

    # Save to file for analysis (avoids encoding issues)
    output_file = EXPLORATION_DIR / "zabapgit_pull_push_elements.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to: {output_file}")

    print("\n--- Pull/Push elements count ---")
    print(f"Found {len(result.get('pullPushElements', []))} pull/push related elements")

    for el in result.get('pullPushElements', []):
        text = el.get('text', '').replace('\n', ' ').replace('\r', '')[:60]
        onclick = el.get('onclick', '')
        # Encode for console safety
        try:
            print(f"  {el.get('tag')}: '{text}' | onclick={onclick}")
        except UnicodeEncodeError:
            print(f"  {el.get('tag')}: [unicode text] | onclick={onclick}")


@pytest.mark.anyio
async def test_abapgit_click_pull(sap_mcp_client: ClientSession) -> None:
    """Click the Pull link and observe what happens (PAT dialog?)."""
    import asyncio

    from sapwebguimcp.models import EvaluateResult

    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Wait for abapGit UI to fully load inside iframe
    await asyncio.sleep(3)

    # Find the Pull link - try multiple iframe IDs
    js_click_pull = """
    (() => {
        // Try multiple ways to find the iframe (ID can be dynamic)
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),  // ID starts with C
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframe = null;
        let iframeDoc = null;

        for (const candidate of iframeCandidates) {
            try {
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc && doc.body?.innerText?.includes('Repository')) {
                    iframe = candidate;
                    iframeDoc = doc;
                    break;
                }
            } catch (e) { /* ignore cross-origin errors */ }
        }

        if (!iframe) return JSON.stringify({error: 'No iframe with abapGit content found'});
        if (!iframeDoc) return JSON.stringify({error: 'Cannot access iframe document'});

        // Find the Pull link - look for various patterns
        const allLinks = Array.from(iframeDoc.querySelectorAll('a'));
        const pullLink = allLinks.find(a =>
            (a.innerText?.trim() === 'Pull' && a.href?.includes('git_pull')) ||
            (a.innerText?.toLowerCase().includes('pull') && a.className?.includes('action_link'))
        );

        if (!pullLink) {
            // Debug: list all links with "pull" or action classes
            const debugLinks = allLinks.filter(a =>
                a.innerText?.toLowerCase().includes('pull') ||
                a.className?.includes('action')
            ).map(a => ({text: a.innerText?.substring(0, 50), href: a.href?.substring(0, 100), className: a.className}));

            return JSON.stringify({
                error: 'Pull link not found',
                iframeId: iframe.id,
                debug: debugLinks.slice(0, 10)
            });
        }

        return JSON.stringify({
            found: true,
            iframeId: iframe.id,
            href: pullLink.href,
            text: pullLink.innerText?.trim()
        });
    })()
    """

    eval_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_click_pull},
        EvaluateResult,
    )

    import json
    raw = eval_result.result
    while isinstance(raw, str):
        raw = json.loads(raw)
    result = raw
    print(f"\nPull link info: {result}")

    if result.get('error'):
        print(f"Error: {result['error']}")
        return

    # Actually click the Pull link
    js_do_click = """
    (() => {
        // Find iframe with abapGit content
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframeDoc = null;
        for (const candidate of iframeCandidates) {
            try {
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc && doc.body?.innerText?.includes('Repository')) {
                    iframeDoc = doc;
                    break;
                }
            } catch (e) { /* ignore */ }
        }

        if (!iframeDoc) return JSON.stringify({clicked: false, error: 'No iframe found'});

        // Use same matching logic as the find script
        const allLinks = Array.from(iframeDoc.querySelectorAll('a'));
        const pullLink = allLinks.find(a =>
            (a.innerText?.trim() === 'Pull' && a.href?.includes('git_pull')) ||
            (a.innerText?.toLowerCase().includes('pull') && a.className?.includes('action_link'))
        );

        if (pullLink) {
            pullLink.click();
            return JSON.stringify({clicked: true, href: pullLink.href});
        }
        return JSON.stringify({clicked: false, error: 'Pull link not found'});
    })()
    """

    click_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_do_click},
        EvaluateResult,
    )
    print(f"\nClick result: {click_result.result}")

    # Wait a moment for dialog to appear
    import asyncio
    await asyncio.sleep(2)

    # Capture what's on screen now
    await capture_snapshot(sap_mcp_client, "zabapgit_after_pull_click", overwrite=True)

    # Check for popup/dialog
    js_check_dialog = """
    (() => {
        // Find iframe with abapGit content
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframeDoc = null;
        for (const candidate of iframeCandidates) {
            try {
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc) {
                    iframeDoc = doc;
                    break;
                }
            } catch (e) { /* ignore */ }
        }

        if (!iframeDoc) return JSON.stringify({error: 'No iframe found'});

        // Look for dialog/popup elements
        const dialogs = Array.from(iframeDoc.querySelectorAll(
            '.dialog, .popup, .modal, [role="dialog"], [role="alertdialog"], form, .repo-popup'
        ));

        // Also check for input fields (PAT might be in a form)
        const inputs = Array.from(iframeDoc.querySelectorAll('input[type="text"], input[type="password"]'));

        // Get body text
        const bodyText = iframeDoc.body?.innerText?.substring(0, 2000) || '';

        return JSON.stringify({
            dialogCount: dialogs.length,
            dialogs: dialogs.slice(0, 5).map(d => ({
                tag: d.tagName,
                className: d.className,
                text: d.innerText?.substring(0, 200)
            })),
            inputCount: inputs.length,
            inputs: inputs.map(i => ({
                type: i.type,
                name: i.name,
                id: i.id,
                placeholder: i.placeholder
            })),
            bodyPreview: bodyText
        }, null, 2);
    })()
    """

    dialog_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_check_dialog},
        EvaluateResult,
    )

    raw_dialog = dialog_result.result
    while isinstance(raw_dialog, str):
        raw_dialog = json.loads(raw_dialog)
    dialog_info = raw_dialog
    # Save to file
    output_file = EXPLORATION_DIR / "zabapgit_after_pull_dialog.json"
    output_file.write_text(json.dumps(dialog_info, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved dialog info to: {output_file}")
    print(f"Dialogs found: {dialog_info.get('dialogCount', 0)}")
    print(f"Inputs found: {dialog_info.get('inputCount', 0)}")
    for inp in dialog_info.get('inputs', []):
        print(f"  Input: {inp}")


@pytest.mark.anyio
async def test_abapgit_explore_repo_menu(sap_mcp_client: ClientSession) -> None:
    """Explore the repo-specific action menu (the ▸ arrow next to repo)."""
    import asyncio
    import json

    from sapwebguimcp.models import EvaluateResult

    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Wait for abapGit UI to load
    await asyncio.sleep(3)

    # Find and explore the repo menu arrow (▸)
    js_find_repo_menu = """
    (() => {
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframeDoc = null;
        for (const candidate of iframeCandidates) {
            try {
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc && doc.body?.innerText?.includes('Repository')) {
                    iframeDoc = doc;
                    break;
                }
            } catch (e) { /* ignore */ }
        }

        if (!iframeDoc) return JSON.stringify({error: 'No iframe found'});

        // Find the repo row containing a github.com reference
        const allRows = Array.from(iframeDoc.querySelectorAll('tr'));
        const repoRow = allRows.find(tr =>
            tr.innerText?.includes('github.com') || tr.innerText?.includes('/HFQ/')
        );

        if (!repoRow) return JSON.stringify({error: 'No repo row found'});

        // Find all links/actions in this repo row
        const rowLinks = Array.from(repoRow.querySelectorAll('a, span, [onclick]'));

        // Find the ▸ arrow (menu trigger)
        const menuArrow = rowLinks.find(el =>
            el.innerText?.includes('▸') || el.innerText?.includes('►')
        );

        // Also look for Pull/Stage specific links in the row
        const pullLink = rowLinks.find(a => a.innerText?.includes('Pull') || a.href?.includes('git_pull'));
        const stageLink = rowLinks.find(a => a.innerText?.includes('Stage') || a.href?.includes('go_stage'));

        // Get all actions in the row
        const actions = rowLinks.map(el => ({
            tag: el.tagName,
            text: el.innerText?.substring(0, 50),
            href: el.href || null,
            className: el.className?.substring(0, 100),
            onclick: el.getAttribute?.('onclick')?.substring(0, 100)
        }));

        return JSON.stringify({
            repoRowText: repoRow.innerText?.substring(0, 300),
            actionCount: rowLinks.length,
            actions: actions,
            menuArrow: menuArrow ? {text: menuArrow.innerText, className: menuArrow.className} : null,
            pullLink: pullLink ? {text: pullLink.innerText, href: pullLink.href} : null,
            stageLink: stageLink ? {text: stageLink.innerText, href: stageLink.href} : null
        }, null, 2);
    })()
    """

    eval_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_find_repo_menu},
        EvaluateResult,
    )

    raw = eval_result.result
    while isinstance(raw, str):
        raw = json.loads(raw)
    result = raw

    # Save to file
    output_file = EXPLORATION_DIR / "zabapgit_repo_menu.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to: {output_file}")

    # Print with Unicode handling
    repo_text = result.get('repoRowText', '')[:150].encode('ascii', 'replace').decode()
    print(f"\nRepo row text: {repo_text}...")
    print(f"Action count: {result.get('actionCount', 0)}")
    print(f"Menu arrow found: {result.get('menuArrow') is not None}")
    print(f"Pull link found: {result.get('pullLink') is not None}")
    print(f"Stage link found: {result.get('stageLink') is not None}")
    if result.get('pullLink'):
        print(f"  Pull href: {result['pullLink'].get('href', '')[:100]}")
    if result.get('stageLink'):
        print(f"  Stage href: {result['stageLink'].get('href', '')[:100]}")
    print(f"\nAll actions in row: {result.get('actionCount', 0)} items (saved to file)")

    # If there's a menu arrow, click it to expand
    if result.get('menuArrow'):
        print("\n--- Clicking menu arrow to expand ---")
        js_click_menu = """
        (() => {
            const iframeCandidates = [
                document.querySelector('iframe#C116'),
                document.querySelector('iframe[id^="C"]'),
                document.querySelector('iframe')
            ].filter(Boolean);

            let iframeDoc = null;
            for (const candidate of iframeCandidates) {
                try {
                    const doc = candidate.contentDocument || candidate.contentWindow?.document;
                    if (doc && doc.body?.innerText?.includes('Repository')) {
                        iframeDoc = doc;
                        break;
                    }
                } catch (e) { /* ignore */ }
            }

            if (!iframeDoc) return JSON.stringify({error: 'No iframe found'});

            const allRows = Array.from(iframeDoc.querySelectorAll('tr'));
            const repoRow = allRows.find(tr =>
                tr.innerText?.includes('github.com') || tr.innerText?.includes('/HFQ/')
            );

            if (!repoRow) return JSON.stringify({error: 'No repo row found'});

            const rowLinks = Array.from(repoRow.querySelectorAll('a, span, [onclick]'));
            const menuArrow = rowLinks.find(el =>
                el.innerText?.includes('▸') || el.innerText?.includes('►')
            );

            if (!menuArrow) return JSON.stringify({error: 'No menu arrow found'});

            menuArrow.click();
            return JSON.stringify({clicked: true, text: menuArrow.innerText});
        })()
        """

        click_result = await call_tool_typed(
            sap_mcp_client,
            "browser_evaluate",
            {"script": js_click_menu},
            EvaluateResult,
        )

        raw_click = click_result.result
        while isinstance(raw_click, str):
            raw_click = json.loads(raw_click)
        print(f"Click result: clicked={raw_click.get('clicked')}, error={raw_click.get('error')}")

        # Wait for menu to expand
        await asyncio.sleep(1)

        # Check what's now visible (expanded menu)
        js_check_expanded = """
        (() => {
            const iframeCandidates = [
                document.querySelector('iframe#C116'),
                document.querySelector('iframe[id^="C"]'),
                document.querySelector('iframe')
            ].filter(Boolean);

            let iframeDoc = null;
            for (const candidate of iframeCandidates) {
                try {
                    const doc = candidate.contentDocument || candidate.contentWindow?.document;
                    if (doc) {
                        iframeDoc = doc;
                        break;
                    }
                } catch (e) { /* ignore */ }
            }

            if (!iframeDoc) return JSON.stringify({error: 'No iframe found'});

            // Look for visible menus/dropdowns
            const menus = Array.from(iframeDoc.querySelectorAll('.dropdown, .menu, [role="menu"], ul.repo-actions, .submenu, ul'));
            const visibleMenus = menus.filter(m => {
                const style = window.getComputedStyle(m);
                return style.display !== 'none' && style.visibility !== 'hidden';
            });

            // Find all action links
            const allLinks = Array.from(iframeDoc.querySelectorAll('a'));
            const actionLinks = allLinks.filter(a =>
                a.className?.includes('action') ||
                a.innerText?.toLowerCase().match(/pull|push|stage|diff|check/)
            ).map(a => ({
                text: a.innerText?.trim()?.substring(0, 50),
                href: a.href?.substring(0, 150),
                className: a.className
            }));

            const bodyText = iframeDoc.body?.innerText?.substring(0, 2000) || '';

            return JSON.stringify({
                visibleMenuCount: visibleMenus.length,
                actionLinks: actionLinks,
                bodyPreview: bodyText
            }, null, 2);
        })()
        """

        expanded_result = await call_tool_typed(
            sap_mcp_client,
            "browser_evaluate",
            {"script": js_check_expanded},
            EvaluateResult,
        )

        raw_expanded = expanded_result.result
        while isinstance(raw_expanded, str):
            raw_expanded = json.loads(raw_expanded)

        # Save expanded menu info
        output_file2 = EXPLORATION_DIR / "zabapgit_repo_menu_expanded.json"
        output_file2.write_text(json.dumps(raw_expanded, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved expanded menu to: {output_file2}")
        print(f"Action links found: {len(raw_expanded.get('actionLinks', []))}")
        for link in raw_expanded.get('actionLinks', [])[:15]:
            text = link.get('text', '').encode('ascii', 'replace').decode()
            href = link.get('href', '')[:80] if link.get('href') else ''
            print(f"  {text}: {href}")


@pytest.mark.anyio
async def test_abapgit_click_repo_pull(sap_mcp_client: ClientSession) -> None:
    """Click Pull from the repo-specific menu and observe what dialog appears."""
    import asyncio
    import json

    from sapwebguimcp.models import EvaluateResult

    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Wait for abapGit UI to load
    await asyncio.sleep(3)

    # Step 1: Click the repo menu arrow to expand
    js_click_menu = """
    (() => {
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframeDoc = null;
        for (const candidate of iframeCandidates) {
            try {
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc && doc.body?.innerText?.includes('Repository')) {
                    iframeDoc = doc;
                    break;
                }
            } catch (e) { /* ignore */ }
        }

        if (!iframeDoc) return JSON.stringify({error: 'No iframe found'});

        const allRows = Array.from(iframeDoc.querySelectorAll('tr'));
        const repoRow = allRows.find(tr =>
            tr.innerText?.includes('github.com') || tr.innerText?.includes('/HFQ/')
        );

        if (!repoRow) return JSON.stringify({error: 'No repo row found'});

        const rowLinks = Array.from(repoRow.querySelectorAll('a'));
        const menuArrow = rowLinks.find(el =>
            el.innerText?.includes('▸') || el.innerText?.includes('►')
        );

        if (!menuArrow) return JSON.stringify({error: 'No menu arrow found'});

        menuArrow.click();
        return JSON.stringify({clicked: true, step: 'menu_arrow'});
    })()
    """

    result1 = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_click_menu},
        EvaluateResult,
    )
    raw1 = result1.result
    while isinstance(raw1, str):
        raw1 = json.loads(raw1)
    print(f"\nStep 1 - Click menu arrow: {raw1}")

    if raw1.get('error'):
        print(f"Error: {raw1['error']}")
        return

    # Wait for menu to expand
    await asyncio.sleep(1)

    # Step 2: Click the Pull action link
    js_click_pull = """
    (() => {
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframeDoc = null;
        for (const candidate of iframeCandidates) {
            try {
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc) {
                    iframeDoc = doc;
                    break;
                }
            } catch (e) { /* ignore */ }
        }

        if (!iframeDoc) return JSON.stringify({error: 'No iframe found'});

        // Find the Pull link in the expanded menu
        const allLinks = Array.from(iframeDoc.querySelectorAll('a'));
        const pullLink = allLinks.find(a =>
            a.innerText?.trim() === 'Pull' && a.className?.includes('action_link')
        );

        if (!pullLink) {
            // Debug: list action links
            const actionLinks = allLinks.filter(a => a.className?.includes('action_link'));
            return JSON.stringify({
                error: 'Pull link not found',
                actionLinkCount: actionLinks.length,
                actionLinkTexts: actionLinks.slice(0, 10).map(a => a.innerText?.trim())
            });
        }

        pullLink.click();
        return JSON.stringify({clicked: true, step: 'pull_link', href: pullLink.href});
    })()
    """

    result2 = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_click_pull},
        EvaluateResult,
    )
    raw2 = result2.result
    while isinstance(raw2, str):
        raw2 = json.loads(raw2)
    print(f"\nStep 2 - Click Pull: {raw2.get('clicked')}, error={raw2.get('error')}")

    if raw2.get('error'):
        print(f"Debug: {raw2}")
        return

    # Wait for dialog/screen to appear
    await asyncio.sleep(3)

    # Step 3: Check what dialog appeared (PAT input? confirmation?)
    js_check_screen = """
    (() => {
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframeDoc = null;
        for (const candidate of iframeCandidates) {
            try {
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc) {
                    iframeDoc = doc;
                    break;
                }
            } catch (e) { /* ignore */ }
        }

        if (!iframeDoc) return JSON.stringify({error: 'No iframe found'});

        // Look for forms, input fields, dialogs
        const forms = Array.from(iframeDoc.querySelectorAll('form'));
        const inputs = Array.from(iframeDoc.querySelectorAll('input'));
        const textareas = Array.from(iframeDoc.querySelectorAll('textarea'));
        const labels = Array.from(iframeDoc.querySelectorAll('label, .label, th'));
        const buttons = Array.from(iframeDoc.querySelectorAll('button, a[role="button"], .button'));

        // Check for PAT/token related text
        const bodyText = iframeDoc.body?.innerText || '';
        const hasTokenText = /token|pat|password|authentication|credential/i.test(bodyText);

        return JSON.stringify({
            formCount: forms.length,
            inputCount: inputs.length,
            inputs: inputs.slice(0, 10).map(i => ({
                type: i.type,
                name: i.name,
                id: i.id,
                placeholder: i.placeholder,
                value: i.value?.substring(0, 50)
            })),
            textareaCount: textareas.length,
            labelTexts: labels.slice(0, 20).map(l => l.innerText?.substring(0, 50)),
            buttonTexts: buttons.slice(0, 10).map(b => b.innerText?.substring(0, 30)),
            hasTokenText: hasTokenText,
            bodyPreview: bodyText.substring(0, 2000)
        }, null, 2);
    })()
    """

    result3 = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_check_screen},
        EvaluateResult,
    )
    raw3 = result3.result
    while isinstance(raw3, str):
        raw3 = json.loads(raw3)

    # Save to file
    output_file = EXPLORATION_DIR / "zabapgit_pull_dialog.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(raw3, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved dialog info to: {output_file}")

    print(f"\nForm count: {raw3.get('formCount', 0)}")
    print(f"Input count: {raw3.get('inputCount', 0)}")
    print(f"Has token/PAT text: {raw3.get('hasTokenText', False)}")
    print(f"\nInputs: {len(raw3.get('inputs', []))} input fields")
    for inp in raw3.get('inputs', []):
        print(f"  - {inp.get('name') or inp.get('id')}: type={inp.get('type')}")
    print(f"\nLabels: {len(raw3.get('labelTexts', []))} labels (see saved file)")
    print(f"\nButtons: {len(raw3.get('buttonTexts', []))} buttons")
    for btn in raw3.get('buttonTexts', []):
        text = btn.encode('ascii', 'replace').decode() if btn else ''
        print(f"  - {text}")

    # Capture snapshot
    await capture_snapshot(sap_mcp_client, "zabapgit_pull_dialog", overwrite=True)


# =============================================================================
# Integration Tests for abapGit MCP Tools
# =============================================================================


@pytest.mark.anyio
async def test_sap_abapgit_pull_tool(sap_mcp_client: ClientSession) -> None:
    """Test the sap_abapgit_pull MCP tool."""
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Try to pull the BO4E repo (matches by name pattern)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "BO4E"},
        AbapGitActionResult,
    )

    print(f"\nPull result: success={result.success}")
    print(f"Repo name: {result.repo_name}")
    print(f"Message: {result.message}")
    print(f"Error: {result.error}")

    # The test should succeed in finding and clicking Pull
    # It may fail on PAT if no token is provided, which is expected
    if not result.success and "PAT" in (result.error or ""):
        print("Note: Pull requires PAT - expected if ABAPGIT_PAT not set")
    elif not result.success:
        print(f"Pull failed with error: {result.error}")


@pytest.mark.anyio
async def test_sap_abapgit_stage_tool(sap_mcp_client: ClientSession) -> None:
    """Test the sap_abapgit_stage MCP tool."""
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Try to stage the BO4E repo
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_stage",
        {"repo": "BO4E"},
        AbapGitActionResult,
    )

    print(f"\nStage result: success={result.success}")
    print(f"Repo name: {result.repo_name}")
    print(f"Message: {result.message}")
    print(f"Error: {result.error}")
