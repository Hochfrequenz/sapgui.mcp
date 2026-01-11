(args) => {
    // Fill a filter field in SE16N selection criteria grid by row index
    // Uses row index from SE11 field order mapping instead of searching by field name
    const rowIndex = args.rowIndex;  // 0-based index (first data row after header)
    const value = args.value;
    const fieldName = args.fieldName || '';  // Optional, for error messages
    const debug = { gridsFound: 0, dataRowsFound: 0, targetRowFound: false };

    // Find the selection criteria grid
    const grids = document.querySelectorAll('[role="grid"]');
    debug.gridsFound = grids.length;

    for (const grid of grids) {
        // Check if this is the selection criteria grid by looking for typical elements
        const gridText = grid.textContent || '';
        if (!gridText.includes('Feldname') && !gridText.includes('Field') &&
            !gridText.includes('Option') && !gridText.includes('Von-Wert') &&
            !gridText.includes('From-Value')) {
            continue;  // Skip non-selection-criteria grids
        }

        // Find all rows - skip header row (first row with columnheader elements)
        const allRows = grid.querySelectorAll('[role="row"]');
        const dataRows = [];

        for (const row of allRows) {
            // Skip header rows (contain columnheader elements)
            if (row.querySelector('[role="columnheader"]')) {
                continue;
            }
            // Skip empty placeholder rows (all cells say "Leer" or are empty)
            const cells = row.querySelectorAll('[role="gridcell"]');
            let hasContent = false;
            for (const cell of cells) {
                const text = cell.textContent?.trim() || '';
                if (text && text !== 'Leer' && text !== '') {
                    hasContent = true;
                    break;
                }
            }
            if (hasContent) {
                dataRows.push(row);
            }
        }

        debug.dataRowsFound = dataRows.length;

        // Get the target row by index
        if (rowIndex < 0 || rowIndex >= dataRows.length) {
            return {
                success: false,
                error: `Row index ${rowIndex} out of bounds (${dataRows.length} data rows available)`,
                debug,
                fieldName
            };
        }

        const targetRow = dataRows[rowIndex];
        debug.targetRowFound = true;

        // Find the Von-Wert (From-Value) input field in this row
        // It's typically the first text input in the row
        const inputs = targetRow.querySelectorAll('input[type="text"], input:not([type])');
        let inputCount = 0;

        for (const input of inputs) {
            // Skip hidden or disabled inputs
            if (input.disabled || input.type === 'hidden') continue;
            inputCount++;

            // First visible input is Von-Wert (From-Value)
            if (inputCount === 1) {
                input.focus();
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.blur();
                return {
                    success: true,
                    rowIndex,
                    fieldName,
                    value,
                    inputsInRow: inputs.length
                };
            }
        }

        return {
            success: false,
            error: `No input field found in row ${rowIndex} for field '${fieldName}' (row had ${inputs.length} inputs)`,
            debug
        };
    }

    return {
        success: false,
        error: `Selection criteria grid not found (searched ${debug.gridsFound} grids)`,
        debug
    };
};
