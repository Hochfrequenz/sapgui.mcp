(args) => {
    const fields = args.fields;
    const results = { filled: [], notFound: [], errors: [], debug: [] };

    /**
     * Find an input element by its associated label text.
     * SAP Web GUI uses various patterns for labels - not always standard <label> elements.
     */
    function findInputByLabel(labelText) {
        // 1. Try standard label with 'for' attribute
        const labels = document.querySelectorAll('label');
        for (const label of labels) {
            if (label.textContent.trim() === labelText && label.htmlFor) {
                const input = document.getElementById(label.htmlFor);
                if (input) return input;
            }
        }

        // 2. SAP-specific: labels use lsdata["1"] for associated input ID
        // and lsdata["3"] for the label text
        let debugInfo = { labelCount: labels.length, matchingLabels: [], foundInput: null };
        for (const label of labels) {
            const lsdata = label.getAttribute('lsdata');
            if (!lsdata) continue;
            try {
                const parsed = JSON.parse(lsdata);
                // Check if this label's text (key "3") matches
                if (parsed['3'] === labelText) {
                    debugInfo.matchingLabels.push({ labelText: parsed['3'], inputId: parsed['1'] });
                    if (parsed['1']) {
                        const input = document.getElementById(parsed['1']);
                        if (input) {
                            debugInfo.foundInput = parsed['1'];
                            return input;
                        }
                    }
                }
            } catch {
                // Not valid JSON, skip
            }
        }
        console.log('DEBUG findInputByLabel:', labelText, debugInfo);

        // 3. Find text node matching label, then look for nearby input
        // SAP often uses spans, divs, or table cells as labels
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
                    if (input) return input;
                }

                // Look in same container div
                const container = parent.closest('div, td');
                if (container) {
                    // Check next sibling elements
                    let sibling = container.nextElementSibling;
                    while (sibling) {
                        const input =
                            sibling.querySelector('input, textarea, select') ||
                            (sibling.matches('input, textarea, select') ? sibling : null);
                        if (input) return input;
                        sibling = sibling.nextElementSibling;
                    }

                    // Check parent's next sibling
                    const parentSibling = container.parentElement?.nextElementSibling;
                    if (parentSibling) {
                        const input = parentSibling.querySelector('input, textarea, select');
                        if (input) return input;
                    }
                }
            }
        }

        return null;
    }

    /**
     * Fill a single input element with a value, dispatching appropriate events.
     */
    function fillInput(el, value) {
        el.focus();
        el.value = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.blur();
    }

    // Process each field
    for (const [key, value] of Object.entries(fields)) {
        try {
            let el;

            if (key.startsWith('#')) {
                // CSS selector (ID)
                el = document.querySelector(key);
            } else if (key.startsWith('.') || key.includes('[')) {
                // Other CSS selectors
                el = document.querySelector(key);
            } else {
                // Treat as label text
                el = findInputByLabel(key);
            }

            if (!el) {
                // Add debug info about labels searched (helps diagnose form loading issues)
                const labels = document.querySelectorAll('label');
                let labelsWithLsdata = 0;
                let matchingLabels = [];
                let sampleLabelTexts = [];
                for (const label of labels) {
                    const lsdata = label.getAttribute('lsdata');
                    if (lsdata) {
                        labelsWithLsdata++;
                        try {
                            const parsed = JSON.parse(lsdata);
                            if (parsed['3']) {
                                // Keep first 10 labels for debugging
                                if (sampleLabelTexts.length < 10) {
                                    sampleLabelTexts.push(parsed['3']);
                                }
                            }
                            if (parsed['3'] === key) {
                                matchingLabels.push({ label: parsed['3'], inputId: parsed['1'] });
                            }
                        } catch {}
                    }
                }
                results.debug.push({
                    field: key,
                    totalLabels: labels.length,
                    labelsWithLsdata: labelsWithLsdata,
                    matchingLabels: matchingLabels,
                    sampleLabelTexts: sampleLabelTexts,
                });
                results.notFound.push(key);
                continue;
            }

            fillInput(el, value);
            results.filled.push(key);
        } catch (e) {
            results.errors.push({ field: key, error: e.message || String(e) });
        }
    }

    return results;
};
