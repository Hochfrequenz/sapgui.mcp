/**
 * Find the main form input field on a SAP transaction's initial screen.
 *
 * This is used as a last-resort fallback when fill_field / fill_form
 * cannot locate the field by label.  Unlike discover_fields()[0] which
 * may return the transaction code combobox in the toolbar, this function
 * explicitly skips toolbar, banner, and combobox inputs.
 *
 * @param {Object} args - { value: string, labels: string[] }
 * @returns {{ filled: boolean, strategy?: string, label?: string, id?: string }}
 */
(args) => {
    const { value, labels } = args;

    // 1. Try title-attribute match for each label
    for (const label of labels) {
        const byTitle = document.querySelector(`input[title="${label}"]`);
        if (byTitle && byTitle.offsetParent !== null) {
            byTitle.focus();
            byTitle.value = value;
            byTitle.dispatchEvent(new Event('input', { bubbles: true }));
            byTitle.dispatchEvent(new Event('change', { bubbles: true }));
            return { filled: true, strategy: 'title', label, id: byTitle.id };
        }
    }

    // 2. Find first visible text input that is NOT in toolbar/banner/combobox
    const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
    for (const input of inputs) {
        // Skip combobox inputs (transaction code field)
        const role = input.getAttribute('role');
        if (role === 'combobox') continue;
        const ct = input.getAttribute('ct');
        if (ct === 'CB') continue;
        // Skip inputs inside toolbars or banners (transaction code area)
        if (input.closest('[role="toolbar"]')) continue;
        if (input.closest('[role="banner"]')) continue;
        // Skip hidden/invisible inputs
        if (input.offsetParent === null) continue;
        // Skip disabled/readonly inputs
        if (input.disabled || input.readOnly) continue;

        input.focus();
        input.value = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return { filled: true, strategy: 'first-visible-input', id: input.id };
    }

    return { filled: false };
};
