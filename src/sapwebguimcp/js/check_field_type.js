/**
 * Check if a field is a dropdown/combobox and get its element ID.
 * Used by sap_fill_form to determine how to handle each field.
 *
 * @param {string} key - Field label text or CSS selector
 * @returns {Object} - { found: boolean, isDropdown?: boolean, elementId?: string }
 */
(key) => {
    let el;

    // Check if it's a CSS selector
    if (key.startsWith('#') || key.startsWith('.') || key.includes('[')) {
        el = document.querySelector(key);
    } else {
        // Find by label - check lsdata["3"] for label text
        const labels = document.querySelectorAll('label[lsdata]');
        for (const label of labels) {
            try {
                const parsed = JSON.parse(label.getAttribute('lsdata'));
                if (parsed['3'] === key && parsed['1']) {
                    el = document.getElementById(parsed['1']);
                    break;
                }
            } catch {
                // Invalid JSON, skip
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
