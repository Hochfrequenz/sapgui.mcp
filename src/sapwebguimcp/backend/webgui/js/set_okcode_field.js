(params) => {
    const { transactionInput } = params;

    const field = document.getElementById('ToolbarOkCode');
    if (field) {
        // Focus the field first
        field.focus();

        // Set the value directly
        field.value = transactionInput;

        // Trigger input/change events so SAP knows the value changed
        field.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
        field.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
    }
};
