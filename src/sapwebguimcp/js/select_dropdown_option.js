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

    // Find all options and collect available values, find matching option
    const optionElements = listbox.querySelectorAll('[role="option"], [data-itemkey]');
    const availableOptions = [];
    let matchingOption = null;
    let matchingKey = null;
    let matchingDescription = null;

    for (const opt of optionElements) {
        const itemKey = opt.getAttribute('data-itemkey') || '';
        const itemValue1 = opt.getAttribute('data-itemvalue1') || '';
        const itemValue2 = opt.getAttribute('data-itemvalue2') || '';
        const text = opt.textContent.trim();

        // Build display string for available options (same format as get_dropdown_options.js)
        const displayText = itemValue2 || itemValue1 || text;
        const formattedOption = itemKey ? `${itemKey} - ${displayText}` : displayText;
        if (displayText) {
            availableOptions.push(formattedOption);
        }

        // Match by key, formatted string, value1, value2, or full text
        if (
            itemKey === optionText ||
            formattedOption === optionText ||
            optionText.startsWith(itemKey + ' - ') ||
            itemValue1 === optionText ||
            itemValue2 === optionText ||
            text === optionText ||
            text.includes(optionText)
        ) {
            matchingOption = opt;
            matchingKey = itemKey;
            matchingDescription = displayText;
        }
    }

    if (!matchingOption) {
        return {
            success: false,
            error: `Option '${optionText}' not found in dropdown`,
            available_options: availableOptions,
        };
    }

    // Make the listbox visible so SAP can process the click
    const originalVisibility = listbox.style.visibility;
    const originalDisplay = listbox.style.display;
    listbox.style.visibility = 'visible';
    listbox.style.display = 'block';

    // First, click on the dropdown input to "open" it properly (triggers SAP event handlers)
    element.focus();
    element.click();

    // Mark the option as selected using SAP's aria-selected attribute
    matchingOption.setAttribute('aria-selected', 'true');

    // Click the matching option with full event sequence
    matchingOption.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
    matchingOption.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
    matchingOption.click();

    // Directly update the input value to match SAP's behavior
    // SAP dropdowns show the description (not the key) in the input field
    element.value = matchingDescription || matchingKey || optionText;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));

    // Also set data attributes that SAP might use
    element.setAttribute('data-selectedkey', matchingKey || '');

    // Hide listbox
    listbox.style.visibility = originalVisibility || 'hidden';
    listbox.style.display = originalDisplay || 'none';

    return { success: true, selected: matchingKey || optionText };
};
