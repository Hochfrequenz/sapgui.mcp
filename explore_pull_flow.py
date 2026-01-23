"""
Exploratory script to understand the full abapGit pull flow:
1. Click Pull
2. Handle any confirmation dialogs
3. Wait for pull to complete
4. Navigate to SE38 and verify the report content
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sapwebguimcp.models import get_browser_manager
from sapwebguimcp.tools.sap_tool_impl import sap_transaction_impl


async def capture_screen_state(page, label: str):
    """Capture current screen state for analysis."""
    print(f"\n{'='*60}")
    print(f"SCREEN STATE: {label}")
    print('='*60)

    # Get page title
    title = await page.title()
    print(f"Page title: {title}")

    # Check for popups/dialogs in main page
    dialogs = await page.query_selector_all("[class*='popup'], [class*='dialog'], [class*='modal'], [role='dialog']")
    print(f"Found {len(dialogs)} potential dialogs in main page")

    # Check iframe content
    iframes = await page.query_selector_all("iframe")
    print(f"Found {len(iframes)} iframes")

    for i, iframe in enumerate(iframes):
        try:
            frame = await iframe.content_frame()
            if frame:
                # Get iframe HTML snippet
                body = await frame.query_selector("body")
                if body:
                    text = await body.inner_text()
                    # Truncate for readability
                    text_preview = text[:2000] if len(text) > 2000 else text
                    print(f"\nIframe {i} content preview:")
                    print(text_preview)
                    print("...")

                    # Look for buttons
                    buttons = await frame.query_selector_all("button, input[type='button'], input[type='submit'], a.btn, .button")
                    button_texts = []
                    for btn in buttons:
                        btn_text = await btn.inner_text() if await btn.is_visible() else ""
                        if not btn_text:
                            btn_text = await btn.get_attribute("value") or await btn.get_attribute("title") or ""
                        if btn_text.strip():
                            button_texts.append(btn_text.strip())
                    if button_texts:
                        print(f"\nButtons found in iframe {i}: {button_texts}")

                    # Look for checkboxes
                    checkboxes = await frame.query_selector_all("input[type='checkbox']")
                    print(f"Checkboxes in iframe {i}: {len(checkboxes)}")

                    # Look for links
                    links = await frame.query_selector_all("a")
                    link_texts = []
                    for link in links[:20]:  # First 20 links
                        link_text = await link.inner_text() if await link.is_visible() else ""
                        if link_text.strip():
                            link_texts.append(link_text.strip())
                    if link_texts:
                        print(f"\nLinks in iframe {i}: {link_texts}")
        except Exception as e:
            print(f"Error reading iframe {i}: {e}")

    # Check status bar
    status_selectors = [
        "#MSGAREA_STATUSBAR",
        "[id*='STATUSBAR']",
        "[class*='statusbar']",
        "#sapwd_main_window_root_statusbar"
    ]
    for sel in status_selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = await el.inner_text()
                if text.strip():
                    print(f"\nStatus bar ({sel}): {text.strip()}")
        except:
            pass


async def explore_pull_and_verify():
    """Explore the full pull flow and verify in SE38."""

    browser_manager = await get_browser_manager()
    page = await browser_manager.get_current_page()

    if not page:
        print("ERROR: No browser page. Run sap_login first.")
        return

    repo_name = "Z_PRIVATE_ABAPGIT_TEST_REPOSITORY"
    report_name = "Z_REPORT_IN_PRIVATE_GIT_REPO"
    expected_text = "HELLO PRIVATE REPO - UPDATED BY MCP TEST 2026-01-23"

    print(f"Testing pull for repo: {repo_name}")
    print(f"Will verify report: {report_name}")
    print(f"Expected content: {expected_text}")

    # Step 1: Navigate to ZABAPGIT
    print("\n" + "="*60)
    print("STEP 1: Navigate to ZABAPGIT")
    print("="*60)

    result = await sap_transaction_impl("ZABAPGIT", new_window=False)
    print(f"Transaction result: {result}")

    await page.wait_for_timeout(5000)
    await capture_screen_state(page, "After navigating to ZABAPGIT")

    # Step 2: Find and click menu arrow for the repo
    print("\n" + "="*60)
    print("STEP 2: Find repo and expand menu")
    print("="*60)

    # Use the JavaScript to find and click menu
    js_path = Path(__file__).parent / "src" / "sapwebguimcp" / "js" / "abapgit_iframe.js"
    js_code = js_path.read_text(encoding="utf-8")

    find_result = await page.evaluate(f"""
        (() => {{
            {js_code}
            return findRepoRow("{repo_name}");
        }})()
    """)
    print(f"Find repo result: {find_result}")

    if find_result.get("error"):
        print(f"ERROR: Could not find repo: {find_result['error']}")
        return

    # Click menu arrow
    click_menu = await page.evaluate(f"""
        (() => {{
            {js_code}
            return clickMenuArrow("{repo_name}");
        }})()
    """)
    print(f"Click menu result: {click_menu}")

    await page.wait_for_timeout(2000)

    # Check if login dialog appeared
    login_check = await page.evaluate(f"""
        (() => {{
            {js_code}
            return checkLoginDialog();
        }})()
    """)
    print(f"Login dialog check: {login_check}")

    if login_check.get("hasLoginDialog"):
        print("\n" + "="*60)
        print("LOGIN DIALOG DETECTED - Handling authentication")
        print("="*60)

        # Get PAT from environment
        import os
        pat = os.environ.get("ABAPGIT_PAT") or os.environ.get("GITHUB_PAT")
        if not pat:
            print("ERROR: No PAT available for private repo")
            return

        # Fill token
        fill_result = await page.evaluate(f"""
            (token) => {{
                {js_code}
                return fillToken(token);
            }}
        """, pat)
        print(f"Token fill result: {fill_result}")

        # Click Weiter button
        button_selectors = [
            "[title*='Weiter']",
            "[title*='Continue']",
            "button:has-text('Weiter')",
            "button:has-text('Continue')",
        ]
        weiter_clicked = False
        for selector in button_selectors:
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=500):
                    await locator.click()
                    print(f"Clicked Weiter using: {selector}")
                    weiter_clicked = True
                    break
            except:
                pass

        if not weiter_clicked:
            print("WARNING: Could not click Weiter")

        await page.wait_for_timeout(3000)

        # Re-expand menu after login
        click_menu = await page.evaluate(f"""
            (() => {{
                {js_code}
                return clickMenuArrow("{repo_name}");
            }})()
        """)
        print(f"Re-click menu result: {click_menu}")
        await page.wait_for_timeout(2000)

    await capture_screen_state(page, "After expanding menu (or after login)")

    # Step 3: Click Pull
    print("\n" + "="*60)
    print("STEP 3: Click Pull")
    print("="*60)

    # Try Playwright locators first
    pull_clicked = False
    for variant in ["Pull", "Ziehen"]:
        try:
            iframe_locator = page.frame_locator("iframe").first.locator(f"a:has-text('{variant}')").first
            if await iframe_locator.is_visible(timeout=500):
                await iframe_locator.click()
                print(f"Clicked Pull link: {variant}")
                pull_clicked = True
                break
        except Exception as e:
            print(f"Could not click '{variant}': {e}")

    if not pull_clicked:
        print("ERROR: Could not click Pull")
        return

    await page.wait_for_timeout(3000)
    await capture_screen_state(page, "After clicking Pull - checking for confirmation dialog")

    # Step 4: Handle confirmation dialog if present
    print("\n" + "="*60)
    print("STEP 4: Handle confirmation dialog")
    print("="*60)

    # Look for checkboxes or "Select All" type options in iframe
    try:
        iframe = page.frame_locator("iframe").first

        # Check for various confirmation patterns
        # Pattern 1: Checkboxes for objects
        checkboxes = iframe.locator("input[type='checkbox']")
        checkbox_count = await checkboxes.count()
        print(f"Found {checkbox_count} checkboxes in iframe")

        # Pattern 2: "Select All" or similar button/link
        for select_text in ["Select All", "Alle auswählen", "Alles", "All"]:
            try:
                select_locator = iframe.locator(f"a:has-text('{select_text}'), button:has-text('{select_text}')").first
                if await select_locator.is_visible(timeout=500):
                    await select_locator.click()
                    print(f"Clicked: {select_text}")
                    await page.wait_for_timeout(1000)
                    break
            except:
                pass

        # Pattern 3: Look for "Pull" or "Continue" or "OK" button to confirm
        for confirm_text in ["Pull", "Ziehen", "Continue", "Weiter", "OK", "Übernehmen"]:
            try:
                confirm_locator = iframe.locator(f"button:has-text('{confirm_text}'), a:has-text('{confirm_text}'), input[value*='{confirm_text}']").first
                if await confirm_locator.is_visible(timeout=500):
                    await confirm_locator.click()
                    print(f"Clicked confirmation: {confirm_text}")
                    await page.wait_for_timeout(2000)
                    break
            except:
                pass

    except Exception as e:
        print(f"Error handling confirmation: {e}")

    await capture_screen_state(page, "After handling confirmation")

    # Step 5: Wait for pull to complete
    print("\n" + "="*60)
    print("STEP 5: Wait for pull completion")
    print("="*60)

    # Poll for completion
    for i in range(10):
        await page.wait_for_timeout(2000)

        # Check status bar
        from sapwebguimcp.tools.sap_tool_impl import sap_read_status_bar_impl
        status = await sap_read_status_bar_impl()
        print(f"Poll {i+1}: Status type={status.type}, message={status.message}")

        if status.message and ("object" in status.message.lower() or "serialize" in status.message.lower()):
            print("Pull appears complete based on status bar")
            break

    await capture_screen_state(page, "After waiting for pull completion")

    # Step 6: Navigate to SE38 and verify
    print("\n" + "="*60)
    print("STEP 6: Verify in SE38")
    print("="*60)

    result = await sap_transaction_impl("SE38", new_window=False)
    print(f"SE38 navigation result: {result}")

    await page.wait_for_timeout(3000)
    await capture_screen_state(page, "SE38 initial screen")

    # Fill report name - look for the program input field
    # SE38 has a program name field, usually with ID containing "PROGRAM" or similar
    try:
        # Use sap_fill_form or similar approach
        # Look for input field by various methods
        input_selectors = [
            "input[name*='PROGRAM']",
            "input[id*='PROGRAM']",
            "#M0\\:46\\:1\\:1\\:\\:0\\:12",  # Common SE38 field ID pattern
            "input[maxlength='40']",  # Program names are max 40 chars
        ]

        program_input = None
        for sel in input_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=500):
                    program_input = loc
                    print(f"Found program input with: {sel}")
                    break
            except:
                pass

        if program_input:
            await program_input.fill(report_name)
            print(f"Filled report name: {report_name}")

            # Press F7 or click "Display" to view source
            await page.keyboard.press("F7")
            await page.wait_for_timeout(3000)

            await capture_screen_state(page, "After pressing F7 to display source")

            # Look for the expected text in the source code display
            page_text = await page.inner_text("body")
            if expected_text in page_text:
                print(f"\n{'*'*60}")
                print("SUCCESS! Found expected text in SE38 source view:")
                print(expected_text)
                print('*'*60)
            else:
                print(f"\nWARNING: Expected text not found")
                print(f"Looking for: {expected_text}")

                # Check iframe too
                try:
                    iframe = page.frame_locator("iframe").first
                    iframe_text = await iframe.locator("body").inner_text()
                    if expected_text in iframe_text:
                        print(f"\nSUCCESS! Found expected text in iframe:")
                        print(expected_text)
                except:
                    pass
        else:
            print("ERROR: Could not find program input field")

    except Exception as e:
        print(f"Error in SE38 verification: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(explore_pull_and_verify())
