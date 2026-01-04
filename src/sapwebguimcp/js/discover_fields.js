() => {
    const fields = [];

    /**
     * Extract a meaningful field identifier from SAP's lsdata JSON.
     * SAP encodes field info in lsdata attribute, e.g.:
     * lsdata="{...\"SID\":\"wnd[0]/usr/.../txtBUT000-NAME_FIRST\"...}"
     * We extract the field ID like "BUT000-NAME_FIRST" or "ADDR2_DATA-STREET"
     */
    function extractFieldId(lsdata) {
        if (!lsdata) return null;
        try {
            // Look for patterns like txtFIELD-NAME, ctxtFIELD-NAME, cmbFIELD-NAME
            const match = lsdata.match(/(?:txt|ctxt|cmb|chk)([A-Z0-9_]+-[A-Z0-9_]+)/);
            if (match) return match[1];

            // Look for SID containing field identifiers
            const sidMatch = lsdata.match(/"SID":"[^"]*\/([a-z]+)?([A-Z][A-Z0-9_]+-[A-Z0-9_]+)"/);
            if (sidMatch) return sidMatch[2];
        } catch (e) {
            // Ignore parsing errors
        }
        return null;
    }

    /**
     * Generate reliable CSS selectors for SAP fields.
     * Prefer lsdata-based selectors over IDs (which contain problematic : characters).
     */
    function generateSelectors(el, fieldId) {
        const selectors = [];

        // 1. Best: lsdata-based selector with field ID
        if (fieldId) {
            selectors.push(`input[lsdata*='${fieldId}']`);
        }

        // 2. Good: title attribute (visible tooltip)
        const title = el.getAttribute('title');
        if (title && title.length < 100) {
            selectors.push(`input[title="${title.replace(/"/g, '\\"')}"]`);
        }

        // 3. OK: aria-labelledby reference
        const ariaLabelledBy = el.getAttribute('aria-labelledby');
        if (ariaLabelledBy) {
            selectors.push(`input[aria-labelledby="${ariaLabelledBy}"]`);
        }

        // 4. Fallback: name attribute
        if (el.name) {
            selectors.push(`input[name="${el.name}"]`);
        }

        // 5. Last resort: escaped ID (may not work in all CSS parsers)
        if (el.id && !el.id.includes(':')) {
            selectors.push(`#${el.id}`);
        }

        return selectors;
    }

    // Find all input elements
    document.querySelectorAll('input, select, textarea').forEach((el) => {
        // Skip hidden and submit buttons
        if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button') {
            return;
        }

        // Skip if not visible
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
            return;
        }

        // Skip readonly dropdowns (combo boxes)
        if (el.readOnly && el.getAttribute('aria-roledescription') === 'Dropdown-Listenfeld') {
            return;
        }

        const lsdata = el.getAttribute('lsdata');
        const fieldId = extractFieldId(lsdata);
        const selectors = generateSelectors(el, fieldId);

        const field = {
            id: el.id || '',
            name: el.name || '',
            type: el.type || el.tagName.toLowerCase(),
            value: el.value ? el.value.substring(0, 50) : '',
            label: '',
            fieldId: fieldId || '',
            selector: selectors[0] || '', // Best selector
            alternativeSelectors: selectors.slice(1), // Other options
        };

        // Get label from title attribute (SAP uses this for field descriptions)
        const title = el.getAttribute('title');
        if (title) {
            field.label = title.substring(0, 100);
        }

        // If no label, try aria-labelledby
        if (!field.label) {
            const ariaLabelledBy = el.getAttribute('aria-labelledby');
            if (ariaLabelledBy) {
                const labelEl = document.getElementById(ariaLabelledBy);
                if (labelEl) {
                    field.label = labelEl.textContent.trim().substring(0, 100);
                }
            }
        }

        // If no label, look for standard label element
        if (!field.label && el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) {
                field.label = label.textContent.trim().substring(0, 100);
            }
        }

        // SAP-specific: look for label with lsdata["1"] pointing to this input's ID
        if (!field.label && el.id) {
            const labels = document.querySelectorAll('label[lsdata]');
            for (const label of labels) {
                try {
                    const lsdata = JSON.parse(label.getAttribute('lsdata'));
                    if (lsdata['1'] === el.id && lsdata['3']) {
                        field.label = lsdata['3'].substring(0, 100);
                        break;
                    }
                } catch {
                    // Ignore parsing errors
                }
            }
        }

        // If still no label, look for nearby text
        if (!field.label) {
            const parent = el.parentElement;
            if (parent) {
                const prevSibling = el.previousElementSibling;
                if (prevSibling && prevSibling.tagName !== 'INPUT') {
                    field.label = prevSibling.textContent.trim().substring(0, 100);
                }
            }
        }

        fields.push(field);
    });

    return fields;
};
