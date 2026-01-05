/**
 * Select an option from a SAP dropdown/combobox field.
 *
 * SAP WebGUI dropdowns have a hidden listbox that must be made visible before selection.
 * The listbox ID is stored in the input's lsdata["3"] or aria-controls attribute.
 * Options have data-itemkey (code) and data-itemvalue2 (description) attributes.
 *
 * @param {Object} args - Arguments object (Playwright evaluate passes single arg)
 * @param {string} args.elementId - The ID of the dropdown input element
 * @param {string} args.optionText - The option to select (key code or visible text)
 * @returns {Object} - { success: boolean, selected?: string, available_options?: string[], error?: string }
 */
(args) => {
    const { elementId, optionText } = args;
    const element = document.getElementById(elementId);
    if (!element) {
        return { success: false, error: `Element not found: ${elementId}` };
    }

    // Verify it's a dropdown (ct=CB for ComboBox)
    // Note: ct=CBS is an autocomplete field, NOT a dropdown - don't use aria-haspopup
    const ct = element.getAttribute('ct');
    if (ct !== 'CB') {
        return { success: false, error: 'Element is not a dropdown (no ct=CB)' };
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

    // Method 3: Search for listbox with matching aria-owns containing this element's options
    if (!listbox) {
        const allListboxes = document.querySelectorAll('[role="listbox"]');
        for (const lb of allListboxes) {
            // Check if this listbox is associated with our input
            // Often the listbox ID contains part of the input field name
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
        return { success: false, error: 'Listbox not found for this dropdown' };
    }

    // Make the listbox visible (SAP keeps it hidden)
    const originalVisibility = listbox.style.visibility;
    const originalDisplay = listbox.style.display;
    listbox.style.visibility = 'visible';
    listbox.style.display = 'block';

    // Find all options and collect available values
    const optionElements = listbox.querySelectorAll('[role="option"], [data-itemkey]');
    const availableOptions = [];
    let matchingOption = null;

    for (const opt of optionElements) {
        const itemKey = opt.getAttribute('data-itemkey') || '';
        const itemValue1 = opt.getAttribute('data-itemvalue1') || '';
        const itemValue2 = opt.getAttribute('data-itemvalue2') || '';
        const text = opt.textContent.trim();

        // Build display string for available options
        const displayText = itemValue2 || itemValue1 || text;
        if (displayText) {
            availableOptions.push(itemKey ? `${itemKey} - ${displayText}` : displayText);
        }

        // Match by key, value1, value2, or full text
        if (
            itemKey === optionText ||
            itemValue1 === optionText ||
            itemValue2 === optionText ||
            text === optionText ||
            text.includes(optionText)
        ) {
            matchingOption = opt;
        }
    }

    if (!matchingOption) {
        // Hide listbox again before returning
        listbox.style.visibility = originalVisibility;
        listbox.style.display = originalDisplay;

        return {
            success: false,
            error: `Option '${optionText}' not found in dropdown`,
            available_options: availableOptions,
        };
    }

    // Click the matching option
    matchingOption.click();

    // Also dispatch events to ensure SAP processes the selection
    matchingOption.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    matchingOption.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));

    // Get the selected key for confirmation
    const selectedKey = matchingOption.getAttribute('data-itemkey') || optionText;

    // Hide listbox (SAP should do this automatically after selection, but ensure it)
    // Small delay to let SAP process the click
    setTimeout(() => {
        listbox.style.visibility = originalVisibility || 'hidden';
        listbox.style.display = originalDisplay || 'none';
    }, 100);

    return { success: true, selected: selectedKey };
};
