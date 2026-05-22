/**
 * Shared utilities for finding form fields by label.
 * Used by set_field.js and fill_form_fields.js.
 */

/**
 * Find input element(s) by label text.
 * Returns { element, selector } on unique match,
 * { ambiguous: true, count, matches } on multiple matches,
 * or null if not found.
 *
 * IMPORTANT: This function searches ALL label-matching strategies before
 * checking for uniqueness. This prevents bugs where a label matches one
 * field via title and another field via lsdata (e.g., "Postleitzahl" in BP).
 *
 * @param {string} labelText - The label text to search for
 * @returns {Object|null} Match result or null
 */
function findInputByLabel(labelText) {
    const normalizedLabel = labelText.trim();
    const allMatches = [];

    // Helper to add a match if not already present (by element)
    function addMatch(element, selector, source, lsdataField) {
        // Avoid duplicates by checking element reference
        if (!allMatches.some((m) => m.element === element)) {
            allMatches.push({ element, selector, source, lsdataField });
        }
    }

    // Helper to extract lsdataField from input element
    function extractLsdataField(input) {
        const inputLsdata = input.getAttribute('lsdata');
        if (inputLsdata) {
            try {
                const inputParsed = JSON.parse(inputLsdata);
                // Field name is often in key "0"
                if (inputParsed['0']) {
                    return inputParsed['0'];
                }
                // Or in nested SID object
                const sid = inputParsed['21']?.SID;
                if (sid) {
                    // Extract field name from SID like ".../txtADDR2_DATA-POST_CODE1"
                    const match = sid.match(/txt([A-Z0-9_-]+)$/);
                    if (match) {
                        return match[1];
                    }
                }
            } catch {}
        }
        // Also try to get from input name attribute
        if (input.name) {
            return input.name;
        }
        return null;
    }

    // 1. Try title attribute match (most common for SAP fields)
    const inputsWithTitle = document.querySelectorAll(
        'input[title], select[title], textarea[title]'
    );
    for (const input of inputsWithTitle) {
        const title = input.getAttribute('title');
        if (title) {
            const normalizedTitle = title.substring(0, 100).trim();
            if (normalizedTitle === normalizedLabel) {
                const selector = input.id ? `#${CSS.escape(input.id)}` : `[title="${title}"]`;
                const lsdataField = extractLsdataField(input);
                addMatch(input, selector, 'title', lsdataField);
            }
        }
    }

    // 2. Try startsWith match for title (for truncation edge cases)
    // Only if no exact title matches found
    if (allMatches.length === 0) {
        for (const input of inputsWithTitle) {
            const title = input.getAttribute('title');
            if (title && title.startsWith(normalizedLabel)) {
                const selector = input.id ? `#${CSS.escape(input.id)}` : `[title="${title}"]`;
                const lsdataField = extractLsdataField(input);
                addMatch(input, selector, 'title-startsWith', lsdataField);
            }
        }
    }

    // 3. SAP-specific: labels use lsdata["1"] for associated input ID
    // and lsdata["3"] for the label text
    const labels = document.querySelectorAll('label');
    for (const label of labels) {
        const lsdata = label.getAttribute('lsdata');
        if (!lsdata) continue;
        try {
            const parsed = JSON.parse(lsdata);
            if (parsed['3'] && parsed['1']) {
                const normalizedParsed = parsed['3'].substring(0, 100).trim();
                if (normalizedParsed === normalizedLabel) {
                    const input = document.getElementById(parsed['1']);
                    if (input) {
                        const lsdataField = extractLsdataField(input);
                        const selector = `#${CSS.escape(input.id)}`;
                        addMatch(input, selector, 'lsdata', lsdataField);
                    }
                }
            }
        } catch {
            // Not valid JSON, skip
        }
    }

    // 4. Try standard label with 'for' attribute
    for (const label of labels) {
        if (label.textContent.trim() === normalizedLabel && label.htmlFor) {
            const input = document.getElementById(label.htmlFor);
            if (input) {
                const lsdataField = extractLsdataField(input);
                const selector = `#${CSS.escape(input.id)}`;
                addMatch(input, selector, 'for-attribute', lsdataField);
            }
        }
    }

    // 5. Try aria-label match
    const ariaInputs = document.querySelectorAll(
        `input[aria-label="${labelText}"], textarea[aria-label="${labelText}"]`
    );
    for (const input of ariaInputs) {
        const lsdataField = extractLsdataField(input);
        const selector = input.id ? `#${CSS.escape(input.id)}` : `[aria-label="${labelText}"]`;
        addMatch(input, selector, 'aria-label', lsdataField);
    }

    // 6. Find text node matching label, then look for nearby input
    // Only if no other matches found (this is a fallback heuristic)
    if (allMatches.length === 0) {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);

        while (walker.nextNode()) {
            const text = walker.currentNode.textContent.trim();
            if (text === labelText) {
                const parent = walker.currentNode.parentElement;
                if (!parent) continue;

                // Look in same table row (common SAP pattern)
                const row = parent.closest('tr');
                if (row) {
                    const input = row.querySelector('input, textarea, select');
                    if (input) {
                        const lsdataField = extractLsdataField(input);
                        const selector = input.id
                            ? `#${CSS.escape(input.id)}`
                            : input.name
                              ? `[name="${input.name}"]`
                              : null;
                        if (selector) {
                            addMatch(input, selector, 'text-node-row', lsdataField);
                        }
                    }
                }

                // Look in same container div
                const container = parent.closest('div, td');
                if (container) {
                    let sibling = container.nextElementSibling;
                    while (sibling) {
                        const input =
                            sibling.querySelector('input, textarea, select') ||
                            (sibling.matches && sibling.matches('input, textarea, select')
                                ? sibling
                                : null);
                        if (input) {
                            const lsdataField = extractLsdataField(input);
                            const selector = input.id
                                ? `#${CSS.escape(input.id)}`
                                : input.name
                                  ? `[name="${input.name}"]`
                                  : null;
                            if (selector) {
                                addMatch(input, selector, 'text-node-sibling', lsdataField);
                            }
                            break;
                        }
                        sibling = sibling.nextElementSibling;
                    }

                    // Check parent's next sibling
                    const parentSibling = container.parentElement?.nextElementSibling;
                    if (parentSibling) {
                        const input = parentSibling.querySelector('input, textarea, select');
                        if (input) {
                            const lsdataField = extractLsdataField(input);
                            const selector = input.id
                                ? `#${CSS.escape(input.id)}`
                                : input.name
                                  ? `[name="${input.name}"]`
                                  : null;
                            if (selector) {
                                addMatch(input, selector, 'text-node-parent-sibling', lsdataField);
                            }
                        }
                    }
                }
            }
        }
    }

    // Now check uniqueness after searching ALL strategies
    if (allMatches.length === 0) {
        return null;
    }

    if (allMatches.length === 1) {
        return { element: allMatches[0].element, selector: allMatches[0].selector };
    }

    // Multiple matches found - return ambiguity info
    return {
        ambiguous: true,
        count: allMatches.length,
        matches: allMatches.map((m) => ({
            selector: m.selector,
            lsdataField: m.lsdataField,
        })),
    };
}
