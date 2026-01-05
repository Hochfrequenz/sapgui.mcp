(args) => {
    const label = args.label;
    const value = args.value;

    /**
     * Find an input element by its associated label text.
     * SAP Web GUI uses various patterns for labels - not always standard <label> elements.
     * Returns { element, selector } or null.
     */
    function findInputByLabel(labelText) {
        const normalizedLabel = labelText.trim();

        // 1. Try title attribute match (most common for SAP fields - same as detect_form_fields.js)
        const inputsWithTitle = document.querySelectorAll(
            'input[title], select[title], textarea[title]'
        );
        for (const input of inputsWithTitle) {
            const title = input.getAttribute('title');
            if (title) {
                const normalizedTitle = title.substring(0, 100).trim();
                if (normalizedTitle === normalizedLabel) {
                    return {
                        element: input,
                        selector: input.id ? `#${input.id}` : `[title="${title}"]`,
                    };
                }
            }
        }
        // Try startsWith match for truncation edge cases
        for (const input of inputsWithTitle) {
            const title = input.getAttribute('title');
            if (title && title.startsWith(normalizedLabel)) {
                return {
                    element: input,
                    selector: input.id ? `#${input.id}` : `[title="${title}"]`,
                };
            }
        }

        // 2. SAP-specific: labels use lsdata["1"] for associated input ID
        // and lsdata["3"] for the label text
        const labels = document.querySelectorAll('label');
        for (const label of labels) {
            const lsdata = label.getAttribute('lsdata');
            if (!lsdata) continue;
            try {
                const parsed = JSON.parse(lsdata);
                // Check if this label's text (key "3") matches
                if (parsed['3'] && parsed['1']) {
                    const normalizedParsed = parsed['3'].substring(0, 100).trim();
                    if (normalizedParsed === normalizedLabel) {
                        const input = document.getElementById(parsed['1']);
                        if (input) return { element: input, selector: `#${input.id}` };
                    }
                }
            } catch {
                // Not valid JSON, skip
            }
        }

        // 3. Try standard label with 'for' attribute
        for (const label of labels) {
            if (label.textContent.trim() === normalizedLabel && label.htmlFor) {
                const input = document.getElementById(label.htmlFor);
                if (input) return { element: input, selector: `#${input.id}` };
            }
        }

        // 4. Try aria-label match
        const ariaInputs = document.querySelectorAll(
            `input[aria-label="${labelText}"], textarea[aria-label="${labelText}"]`
        );
        if (ariaInputs.length > 0) {
            const input = ariaInputs[0];
            return { element: input, selector: `[aria-label="${labelText}"]` };
        }

        // 5. Find text node matching label, then look for nearby input
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
                    if (input) {
                        const selector = input.id
                            ? `#${input.id}`
                            : input.name
                              ? `[name="${input.name}"]`
                              : null;
                        return { element: input, selector };
                    }
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
                        if (input) {
                            const selector = input.id
                                ? `#${input.id}`
                                : input.name
                                  ? `[name="${input.name}"]`
                                  : null;
                            return { element: input, selector };
                        }
                        sibling = sibling.nextElementSibling;
                    }

                    // Check parent's next sibling
                    const parentSibling = container.parentElement?.nextElementSibling;
                    if (parentSibling) {
                        const input = parentSibling.querySelector('input, textarea, select');
                        if (input) {
                            const selector = input.id
                                ? `#${input.id}`
                                : input.name
                                  ? `[name="${input.name}"]`
                                  : null;
                            return { element: input, selector };
                        }
                    }
                }
            }
        }

        return null;
    }

    /**
     * Check if an element is a dropdown/combobox.
     * SAP dropdowns have ct="CB" attribute and are readonly.
     */
    function isDropdown(el) {
        return el.getAttribute('ct') === 'CB' && el.hasAttribute('readonly');
    }

    /**
     * Fill a single input element with a value, dispatching appropriate events.
     */
    function fillInput(el, val) {
        el.focus();
        el.value = val;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.blur();
    }

    try {
        let el;
        let selectorUsed = null;

        // Check if it's a CSS selector
        if (label.startsWith('#') || label.startsWith('.') || label.includes('[')) {
            // Use CSS.escape for SAP IDs containing special characters (e.g., "M0:46:1:1:2:1::0:21")
            // Skip escaping if already escaped (contains \:)
            let escapedLabel = label;
            if (label.startsWith('#') && !label.includes('\\')) {
                escapedLabel = '#' + CSS.escape(label.slice(1));
            }
            const matches = document.querySelectorAll(escapedLabel);
            if (matches.length === 0) {
                return { success: false, error: `Field not found: ${label}` };
            }
            if (matches.length > 1) {
                return {
                    success: false,
                    error: `Selector matches ${matches.length} elements, expected 1: ${label}`,
                };
            }
            el = matches[0];
            selectorUsed = label;
        } else {
            // Treat as label text
            const result = findInputByLabel(label);
            if (result) {
                el = result.element;
                selectorUsed = result.selector;
            }
        }

        if (!el) {
            return { success: false, error: `Field not found: ${label}` };
        }

        // Check if this is a dropdown - return without filling so Python can handle it
        if (isDropdown(el)) {
            return {
                success: false,
                isDropdown: true,
                elementId: el.id,
                selectorUsed,
                error: 'Field is a dropdown, requires special handling',
            };
        }

        fillInput(el, value);
        return { success: true, selectorUsed };
    } catch (e) {
        return { success: false, error: e.message || String(e) };
    }
};
