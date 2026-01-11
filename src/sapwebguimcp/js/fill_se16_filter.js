(args) => {
    // Fill a filter field in SE16N selection criteria grid
    // Finds the row with matching technical field name (button text) and fills the From-Value input
    const fieldName = args.fieldName;
    const value = args.value;
    const debug = { gridsFound: 0, rowsScanned: 0, buttonsFound: [], fieldsAvailable: [] };

    // Find the selection criteria grid - look for the grid containing field names
    const grids = document.querySelectorAll('[role="grid"]');
    debug.gridsFound = grids.length;

    for (const grid of grids) {
        // Find all rows in this grid
        const rows = grid.querySelectorAll('[role="row"]');

        for (const row of rows) {
            debug.rowsScanned++;
            // Look for button with the technical field name in the last cell
            const buttons = row.querySelectorAll('button');
            let fieldNameButton = null;

            for (const btn of buttons) {
                const text = btn.textContent?.trim();
                if (text) {
                    debug.buttonsFound.push(text);
                    // Collect field names that look like technical names (all caps)
                    if (/^[A-Z0-9_]+$/.test(text)) {
                        debug.fieldsAvailable.push(text);
                    }
                }
                if (text === fieldName) {
                    fieldNameButton = btn;
                    break;
                }
            }

            if (fieldNameButton) {
                // Found the row! Now find the Von-Wert (From-Value) input field
                // It's the first textbox input in the row (after the Option dropdown)
                const cells = row.querySelectorAll('[role="gridcell"]');
                let inputCount = 0;

                for (const cell of cells) {
                    const input = cell.querySelector('input[type="text"], input:not([type])');
                    if (input) {
                        inputCount++;
                        // First input is Von-Wert (From-Value)
                        if (inputCount === 1) {
                            input.focus();
                            input.value = value;
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            input.blur();
                            return { success: true, field: fieldName, value: value };
                        }
                    }
                }
                return {
                    success: false,
                    error: 'Input not found in row for field: ' + fieldName,
                    debug,
                };
            }
        }
    }
    // Limit debug output to first 20 fields
    debug.fieldsAvailable = debug.fieldsAvailable.slice(0, 20);
    debug.buttonsFound = debug.buttonsFound.slice(0, 30);
    return { success: false, error: 'Field not found: ' + fieldName, debug };
};
