/**
 * Get available options from a dropdown/combobox field.
 * This script clicks the dropdown to open the listbox, extracts options, then closes it.
 *
 * @param {string} elementId - The ID of the dropdown input element
 * @returns {Object} - { success: boolean, options: string[], error?: string }
 */
(elementId) => {
    return new Promise((resolve) => {
        const element = document.getElementById(elementId);
        if (!element) {
            resolve({ success: false, options: [], error: `Element not found: ${elementId}` });
            return;
        }

        // Verify it's a dropdown
        const ct = element.getAttribute('ct');
        if (ct !== 'CB' && element.getAttribute('aria-haspopup') !== 'true') {
            resolve({ success: false, options: [], error: 'Element is not a dropdown' });
            return;
        }

        // Click to open the listbox
        element.click();
        element.focus();

        // Wait for listbox to appear
        setTimeout(() => {
            // Find the visible listbox (SAP keeps old ones hidden in DOM)
            const listboxes = document.querySelectorAll('[role="listbox"]');
            let visibleListbox = null;

            for (const lb of listboxes) {
                // Check if visible (offsetParent !== null or check computed style)
                if (lb.offsetParent !== null) {
                    visibleListbox = lb;
                    break;
                }
                // Also check display style
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
                resolve({ success: false, options: [], error: 'Listbox not found after clicking dropdown' });
                return;
            }

            // Extract options
            const optionElements = visibleListbox.querySelectorAll('[role="option"]');
            const options = [];
            for (const opt of optionElements) {
                const text = opt.textContent.trim();
                if (text) {
                    options.push(text);
                }
            }

            // Close the listbox by clicking elsewhere or pressing Escape
            document.body.click();
            element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

            // Wait a bit for listbox to close
            setTimeout(() => {
                resolve({ success: true, options: options });
            }, 100);
        }, 300); // Wait 300ms for listbox to open
    });
};
