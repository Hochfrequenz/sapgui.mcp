() => {
    const fields = [];

    // Find all input elements
    document.querySelectorAll('input, select, textarea').forEach((el) => {
        // Skip hidden and submit buttons
        if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button') {
            return;
        }

        // Skip if not visible
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
            return;
        }

        const field = {
            id: el.id || '',
            name: el.name || '',
            type: el.type || el.tagName.toLowerCase(),
            value: el.value ? el.value.substring(0, 50) : '',
            label: '',
            selector: '',
        };

        // Find associated label
        if (el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) {
                field.label = label.textContent.trim().substring(0, 50);
            }
        }

        // If no label found, look for nearby text
        if (!field.label) {
            const parent = el.parentElement;
            if (parent) {
                const prevSibling = el.previousElementSibling;
                if (prevSibling && prevSibling.tagName !== 'INPUT') {
                    field.label = prevSibling.textContent.trim().substring(0, 50);
                }
            }
        }

        // Generate best selector
        if (el.id) {
            field.selector = `#${el.id}`;
        } else if (el.name) {
            field.selector = `input[name="${el.name}"]`;
        } else if (field.label) {
            field.selector = `input:near(:text("${field.label}"))`;
        }

        fields.push(field);
    });

    return fields;
};
