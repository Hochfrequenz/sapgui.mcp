() => {
    const buttons = [];
    const seenIds = new Set();

    /**
     * SAP Web GUI buttons are <div> elements with:
     * - role="button"
     * - class containing "lsButton"
     * - Text in "title" attribute (NOT textContent which often contains SVG)
     * - Optional accesskey attribute
     * - lsdata containing button metadata
     */

    // SAP-specific button selectors
    const buttonSelectors = [
        '.lsButton[role="button"]', // Primary SAP button style
        'div[role="button"].lsButton',
        '[role="button"][title]', // Any role=button with title
        'button', // Standard HTML buttons
    ];

    for (const sel of buttonSelectors) {
        const btns = document.querySelectorAll(sel);
        for (const btn of btns) {
            // Skip if already seen (by ID)
            if (btn.id && seenIds.has(btn.id)) continue;
            if (btn.id) seenIds.add(btn.id);

            // Skip invisible buttons
            const style = window.getComputedStyle(btn);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            if (btn.offsetWidth === 0 && btn.offsetHeight === 0) continue;

            // SAP buttons: text is in title attribute, not textContent
            // (textContent may contain SVG or icon text)
            const title = btn.getAttribute('title') || '';
            const textContent = btn.textContent?.trim() || '';

            // Try to extract label from lsdata
            let lsdataLabel = null;
            let shortcut = null;
            const lsdata = btn.getAttribute('lsdata');
            if (lsdata) {
                try {
                    const parsed = JSON.parse(lsdata);
                    // SAP stores button text in key "0" or "4"
                    lsdataLabel = parsed['0'] || parsed['4'] || null;
                } catch {}
            }

            // Use title first (most reliable for SAP), then lsdata, then textContent
            const label = title || lsdataLabel || textContent || '';
            if (!label) continue;

            // Extract shortcut from title (e.g., "Zurück (F3)" -> "F3")
            const shortcutMatch = label.match(/\(([^)]+)\)\s*$/);
            if (shortcutMatch) {
                shortcut = shortcutMatch[1];
            }

            // Generate selector (prefer ID if available)
            let selector = null;
            if (btn.id) {
                // Escape special characters in SAP IDs (colons, brackets)
                selector = '#' + CSS.escape(btn.id);
            }

            buttons.push({
                label: label,
                id: btn.id || null,
                selector: selector,
                shortcut: shortcut,
                accesskey: btn.getAttribute('accesskey') || null,
                tagName: btn.tagName,
                isLsButton: btn.classList.contains('lsButton'),
            });
        }
    }

    return buttons;
};
