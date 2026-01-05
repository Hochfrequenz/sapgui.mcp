(args) => {
    // Note: findInputByLabel is provided by find_field_utils.js (concatenated before this file)
    const label = args.label;
    const value = args.value;

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
            // Treat as label text - use shared utility
            const result = findInputByLabel(label);

            if (result === null) {
                return { success: false, error: `Field not found: ${label}` };
            }

            // Check for ambiguous match
            if (result.ambiguous) {
                const matchDescriptions = result.matches
                    .map((m) => {
                        if (m.lsdataField) {
                            return `${m.selector} (${m.lsdataField})`;
                        }
                        return m.selector;
                    })
                    .join(', ');

                return {
                    success: false,
                    error:
                        `Label "${label}" matches ${result.count} fields. ` +
                        `Use a specific CSS selector instead: ${matchDescriptions}`,
                    ambiguous: true,
                    matchCount: result.count,
                    matchingSelectors: result.matches,
                };
            }

            el = result.element;
            selectorUsed = result.selector;
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
