(args) => {
    const label = args.label;
    const value = args.value;

    /**
     * Find an input element by its associated label text.
     * SAP Web GUI uses various patterns for labels - not always standard <label> elements.
     * Returns { element, selector } or null.
     */
    function findInputByLabel(labelText) {
        // 1. Try standard label with 'for' attribute
        const labels = document.querySelectorAll('label');
        for (const label of labels) {
            if (label.textContent.trim() === labelText && label.htmlFor) {
                const input = document.getElementById(label.htmlFor);
                if (input) return { element: input, selector: `#${input.id}` };
            }
        }

        // 2. Try aria-label match
        const ariaInputs = document.querySelectorAll(
            `input[aria-label="${labelText}"], textarea[aria-label="${labelText}"]`
        );
        if (ariaInputs.length > 0) {
            const input = ariaInputs[0];
            return { element: input, selector: `[aria-label="${labelText}"]` };
        }

        // 3. Try title attribute match
        const titleInputs = document.querySelectorAll(
            `input[title="${labelText}"], textarea[title="${labelText}"]`
        );
        if (titleInputs.length > 0) {
            const input = titleInputs[0];
            return { element: input, selector: `[title="${labelText}"]` };
        }

        // 4. Find text node matching label, then look for nearby input
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
            const matches = document.querySelectorAll(label);
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

        fillInput(el, value);
        return { success: true, selectorUsed };
    } catch (e) {
        return { success: false, error: e.message || String(e) };
    }
};
