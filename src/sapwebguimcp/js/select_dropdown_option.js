/**
 * Select an option from a dropdown/combobox field.
 * This script clicks the dropdown, finds the matching option, and clicks it.
 *
 * @param {string} elementId - The ID of the dropdown input element
 * @param {string} optionText - The exact text of the option to select
 * @returns {Object} - { success: boolean, selected?: string, available_options?: string[], error?: string }
 */
(elementId, optionText) => {
    return new Promise((resolve) => {
        const element = document.getElementById(elementId);
        if (!element) {
            resolve({ success: false, error: `Element not found: ${elementId}` });
            return;
        }

        // Verify it's a dropdown
        const ct = element.getAttribute('ct');
        if (ct !== 'CB' && element.getAttribute('aria-haspopup') !== 'true') {
            resolve({ success: false, error: 'Element is not a dropdown' });
            return;
        }

        // Click to open the listbox
        element.click();
        element.focus();

        // Wait for listbox to appear
        setTimeout(() => {
            // Find the visible listbox
            const listboxes = document.querySelectorAll('[role="listbox"]');
            let visibleListbox = null;

            for (const lb of listboxes) {
                if (lb.offsetParent !== null) {
                    visibleListbox = lb;
                    break;
                }
                const style = window.getComputedStyle(lb);
                if (style.display !== 'none' && style.visibility !== 'hidden') {
                    visibleListbox = lb;
                    break;
                }
            }

            if (!visibleListbox) {
                // Try aria-controls reference
                const ariaControls = element.getAttribute('aria-controls');
                if (ariaControls) {
                    visibleListbox = document.getElementById(ariaControls);
                }
            }

            if (!visibleListbox) {
                resolve({ success: false, error: 'Listbox not found after clicking dropdown' });
                return;
            }

            // Find matching option and collect all options
            const optionElements = visibleListbox.querySelectorAll('[role="option"]');
            const availableOptions = [];
            let matchingOption = null;

            for (const opt of optionElements) {
                const text = opt.textContent.trim();
                if (text) {
                    availableOptions.push(text);
                    if (text === optionText) {
                        matchingOption = opt;
                    }
                }
            }

            if (!matchingOption) {
                // Close the listbox before returning error
                document.body.click();
                element.dispatchEvent(
                    new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })
                );

                resolve({
                    success: false,
                    error: `Option '${optionText}' not found in dropdown`,
                    available_options: availableOptions,
                });
                return;
            }

            // Click the matching option via JavaScript (standard click often fails)
            matchingOption.click();

            // Wait for selection to be applied
            setTimeout(() => {
                resolve({ success: true, selected: optionText });
            }, 200);
        }, 300); // Wait 300ms for listbox to open
    });
};
