/**
 * Get available options from a SAP dropdown/combobox field.
 *
 * SAP WebGUI dropdowns have a hidden listbox containing all options.
 * The listbox ID is stored in the input's lsdata["3"] or aria-controls attribute.
 * Options have data-itemkey (code) and data-itemvalue2 (description) attributes.
 *
 * @param {string} elementId - The ID of the dropdown input element
 * @returns {Object} - { success: boolean, options: string[], error?: string }
 */
(elementId) => {
    const element = document.getElementById(elementId);
    if (!element) {
        return { success: false, options: [], error: `Element not found: ${elementId}` };
    }

    // Verify it's a dropdown (ct=CB for ComboBox)
    // Note: ct=CBS is an autocomplete field, NOT a dropdown - don't use aria-haspopup
    const ct = element.getAttribute('ct');
    if (ct !== 'CB') {
        return { success: false, options: [], error: 'Element is not a dropdown (no ct=CB)' };
    }

    // Find the listbox element
    let listbox = null;

    // Method 1: aria-controls attribute
    const ariaControls = element.getAttribute('aria-controls');
    if (ariaControls) {
        listbox = document.getElementById(ariaControls);
    }

    // Method 2: lsdata["3"] contains listbox ID
    if (!listbox) {
        const lsdataAttr = element.getAttribute('lsdata');
        if (lsdataAttr) {
            try {
                const lsdata = JSON.parse(lsdataAttr);
                if (lsdata['3']) {
                    listbox = document.getElementById(lsdata['3']);
                }
            } catch {
                // JSON parse error, continue
            }
        }
    }

    // Method 3: Search for any listbox that might be associated
    if (!listbox) {
        const allListboxes = document.querySelectorAll('[role="listbox"]');
        for (const lb of allListboxes) {
            if (
                lb.id &&
                element.id &&
                lb.id.includes(element.name || element.id.split(':').pop())
            ) {
                listbox = lb;
                break;
            }
        }
    }

    if (!listbox) {
        return { success: false, options: [], error: 'Listbox not found for this dropdown' };
    }

    // Extract options (no need to make visible for reading)
    const optionElements = listbox.querySelectorAll('[role="option"], [data-itemkey]');
    const options = [];

    for (const opt of optionElements) {
        const itemKey = opt.getAttribute('data-itemkey') || '';
        const itemValue2 = opt.getAttribute('data-itemvalue2') || '';
        const text = opt.textContent.trim();

        // Build display string: "KEY - Description" or just description
        const displayText = itemValue2 || text;
        if (displayText && displayText.trim()) {
            options.push(itemKey ? `${itemKey} - ${displayText}` : displayText);
        } else if (itemKey && itemKey.trim()) {
            options.push(itemKey);
        }
    }

    return { success: true, options };
};
