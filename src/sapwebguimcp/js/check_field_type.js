/**
 * Check if a field is a dropdown/combobox and get its element ID.
 * Used by sap_fill_form to determine how to handle each field.
 *
 * This function uses the same label lookup strategy as detect_form_fields.js
 * to ensure consistency when finding fields by label.
 *
 * @param {string} key - Field label text or CSS selector
 * @returns {Object} - { found: boolean, isDropdown?: boolean, elementId?: string }
 */
(key) => {
    let el;

    // Check if it's a CSS selector
    if (key.startsWith('#') || key.startsWith('.') || key.includes('[')) {
        // Use CSS.escape for SAP IDs containing special characters (e.g., "M0:46:1:1:2:1::0:21")
        // Skip escaping if already escaped (contains \:)
        let escapedKey = key;
        if (key.startsWith('#') && !key.includes('\\')) {
            escapedKey = '#' + CSS.escape(key.slice(1));
        }
        try {
            el = document.querySelector(escapedKey);
        } catch {
            // Selector parsing failed
            el = null;
        }
    } else {
        // Normalize key for comparison (trim whitespace)
        const normalizedKey = key.trim();

        // Find by label using multiple methods (matching detect_form_fields.js)
        // Method 1: Find input by title attribute (most common for SAP fields)
        // First try exact match, then try startsWith match for robustness
        const inputsWithTitle = document.querySelectorAll('input[title], select[title]');
        for (const input of inputsWithTitle) {
            const title = input.getAttribute('title');
            if (title) {
                const normalizedTitle = title.substring(0, 100).trim();
                // Exact match first
                if (normalizedTitle === normalizedKey) {
                    el = input;
                    break;
                }
            }
        }
        // Try startsWith match if exact match failed (handles truncation edge cases)
        if (!el) {
            for (const input of inputsWithTitle) {
                const title = input.getAttribute('title');
                if (title && title.startsWith(normalizedKey)) {
                    el = input;
                    break;
                }
            }
        }
        // Try key startsWith title (in case key is longer than actual title)
        if (!el) {
            for (const input of inputsWithTitle) {
                const title = input.getAttribute('title');
                if (title && normalizedKey.startsWith(title.trim())) {
                    el = input;
                    break;
                }
            }
        }

        // Method 2: Find by lsdata["3"] label text
        if (!el) {
            const labels = document.querySelectorAll('label[lsdata]');
            for (const label of labels) {
                try {
                    const parsed = JSON.parse(label.getAttribute('lsdata'));
                    if (parsed['3'] && parsed['1']) {
                        const normalizedLabel = parsed['3'].substring(0, 100).trim();
                        if (normalizedLabel === normalizedKey) {
                            el = document.getElementById(parsed['1']);
                            if (el) break;
                        }
                    }
                } catch {
                    // Invalid JSON, skip
                }
            }
        }

        // Method 3: Find by aria-labelledby reference
        if (!el) {
            const allInputs = document.querySelectorAll('input, select');
            for (const input of allInputs) {
                const ariaLabelledBy = input.getAttribute('aria-labelledby');
                if (ariaLabelledBy) {
                    const labelEl = document.getElementById(ariaLabelledBy);
                    if (labelEl) {
                        const normalizedLabel = labelEl.textContent.trim().substring(0, 100);
                        if (normalizedLabel === normalizedKey) {
                            el = input;
                            break;
                        }
                    }
                }
            }
        }

        // Method 4: Find by standard label[for] element
        if (!el) {
            const standardLabels = document.querySelectorAll('label[for]');
            for (const label of standardLabels) {
                const normalizedLabel = label.textContent.trim().substring(0, 100);
                if (normalizedLabel === normalizedKey) {
                    el = document.getElementById(label.getAttribute('for'));
                    if (el) break;
                }
            }
        }
    }

    if (!el) {
        return { found: false };
    }

    // Only ct=CB is a true dropdown (ComboBox with predefined options)
    // ct=CBS (ComboBox with Server) is an autocomplete field, NOT a dropdown
    // aria-haspopup is too broad - it's set on CBS fields too
    const ct = el.getAttribute('ct');
    const isDropdown = ct === 'CB';
    return { found: true, isDropdown, elementId: el.id };
};
