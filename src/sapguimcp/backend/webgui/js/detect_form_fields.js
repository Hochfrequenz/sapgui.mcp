() => {
    const fields = [];

    /**
     * Get label text for an input element.
     * SAP uses various methods to associate labels with inputs.
     */
    function getLabel(el) {
        // 1. Title attribute (SAP uses this for field descriptions)
        const title = el.getAttribute('title');
        if (title) {
            return title.substring(0, 100);
        }

        // 2. aria-labelledby reference
        const ariaLabelledBy = el.getAttribute('aria-labelledby');
        if (ariaLabelledBy) {
            const labelEl = document.getElementById(ariaLabelledBy);
            if (labelEl) {
                return labelEl.textContent.trim().substring(0, 100);
            }
        }

        // 3. Standard label element
        if (el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) {
                return label.textContent.trim().substring(0, 100);
            }
        }

        // 4. SAP-specific: look for label with lsdata["1"] pointing to this input's ID
        if (el.id) {
            const labels = document.querySelectorAll('label[lsdata]');
            for (const label of labels) {
                try {
                    const lsdata = JSON.parse(label.getAttribute('lsdata'));
                    if (lsdata['1'] === el.id && lsdata['3']) {
                        return lsdata['3'].substring(0, 100);
                    }
                } catch {
                    // Ignore parsing errors
                }
            }
        }

        // 5. Look for nearby text in parent
        const parent = el.parentElement;
        if (parent) {
            const prevSibling = el.previousElementSibling;
            if (prevSibling && prevSibling.tagName !== 'INPUT') {
                const text = prevSibling.textContent.trim();
                if (text.length > 0 && text.length < 100) {
                    return text;
                }
            }
        }

        return '';
    }

    /**
     * Determine field type from SAP control type attribute.
     */
    function getFieldType(el) {
        const ct = el.getAttribute('ct');

        // ComboBox/Dropdown - only ct=CB is a true dropdown
        // ct=CBS (ComboBox with Server) is an autocomplete field, NOT a dropdown
        if (ct === 'CB') {
            return 'dropdown';
        }

        // Checkbox
        if (ct === 'CHK' || el.type === 'checkbox') {
            return 'checkbox';
        }

        // Radio button
        if (ct === 'RB' || el.type === 'radio') {
            return 'radio';
        }

        // Default to text
        return 'text';
    }

    // Find all input elements
    document.querySelectorAll('input, select').forEach((el) => {
        // Skip hidden and submit buttons
        if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button') {
            return;
        }

        // Skip if not visible
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
            return;
        }

        // Skip if in a hidden container
        if (el.offsetParent === null) {
            return;
        }

        const fieldType = getFieldType(el);
        const isReadonly = el.readOnly || el.disabled || el.hasAttribute('readonly');

        const field = {
            id: el.id || '',
            label: getLabel(el),
            field_type: fieldType,
            current_value: el.value || null,
            checked: fieldType === 'checkbox' || fieldType === 'radio' ? el.checked : null,
            readonly: isReadonly,
            options: null, // Will be populated separately for dropdowns if requested
        };

        // Only include fields with an ID (needed for targeting)
        if (field.id) {
            fields.push(field);
        }
    });

    return fields;
};
