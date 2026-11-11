(params) => {
    const { language, dropdownText } = params;

    // Set hidden language input
    const hiddenField = document.querySelector('#sap-language, input[name="sap-language"]');
    if (hiddenField) {
        hiddenField.value = language;
        hiddenField.dispatchEvent(new Event('input', { bubbles: true }));
        hiddenField.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // Also update the visible dropdown display; the text comes from the language pack
    const dropdown = document.querySelector('#sap-language-dropdown');
    if (dropdown) {
        dropdown.value = dropdownText;
    }
};
