(args) => {
    // Fill a filter field in SE16N selection criteria grid
    // Finds the row with matching technical field name and fills the From-Value input
    const fieldName = args.fieldName;
    const value = args.value;
    const debug = {
        gridsFound: 0,
        rowsScanned: 0,
        buttonsFound: [],
        fieldsAvailable: [],
        rowNames: [],
    };

    // Find the selection criteria grid - look for the grid containing field names
    const grids = document.querySelectorAll('[role="grid"]');
    debug.gridsFound = grids.length;

    for (const grid of grids) {
        // Find all rows in this grid
        const rows = grid.querySelectorAll('[role="row"]');

        for (const row of rows) {
            debug.rowsScanned++;

            // SAP Web GUI uses lazy column rendering - the Technical Name column
            // may not be in the DOM. Try multiple strategies to find the field:
            let foundRow = false;

            // Strategy 1: Check lsdata for SID containing the field name
            // The SID structure is like: .../txtGS_SELFIELDS-FIELDNAME[col,row]
            // We need to look for the actual field name in the input element's lsdata
            const elementsWithLsdata = row.querySelectorAll('[lsdata]');
            for (const el of elementsWithLsdata) {
                const lsdata = el.getAttribute('lsdata');
                if (!lsdata) continue;
                // Check if this lsdata references the field name in the SID
                // Example: tblSAPLSE16NSELFIELDS_TC/ctxtGS_SELFIELDS-LOW[2,0] references TCODE in row 0
                if (lsdata.includes('SELFIELDS-LOW') || lsdata.includes('SELFIELDS-HIGH')) {
                    // This is a filter input field - extract row index
                    const match = lsdata.match(/\[(\d+),(\d+)\]/);
                    if (match) {
                        const colIdx = parseInt(match[1]);
                        const rowIdx = parseInt(match[2]);
                        debug.fieldsAvailable.push(`row${rowIdx}_col${colIdx}`);
                    }
                }
                if (lsdata.includes(fieldName)) {
                    foundRow = true;
                    debug.fieldsAvailable.push(fieldName);
                    break;
                }
            }

            // Strategy 2: Check button text (backward compatibility)
            if (!foundRow) {
                const allButtons = row.querySelectorAll('button, [role="button"]');
                for (const btn of allButtons) {
                    const text = btn.textContent?.trim();
                    if (text) {
                        if (!debug.buttonsFound.includes(text)) {
                            debug.buttonsFound.push(text);
                        }
                        if (/^[A-Z0-9_]+$/.test(text)) {
                            if (!debug.fieldsAvailable.includes(text)) {
                                debug.fieldsAvailable.push(text);
                            }
                        }
                    }
                    if (text === fieldName) {
                        foundRow = true;
                        break;
                    }
                }
            }

            // Strategy 3: Check if row's innerText or any child has the field name
            if (!foundRow) {
                const rowText = row.innerText || '';
                if (new RegExp('\\b' + fieldName + '\\b', 'i').test(rowText)) {
                    foundRow = true;
                    debug.fieldsAvailable.push(fieldName);
                }
            }

            if (foundRow) {
                // Found the row! Now find the Von-Wert (From-Value) input field
                // SAP Web GUI uses lazy column rendering, so try multiple selectors
                // to find text inputs in the row
                let inputs = row.querySelectorAll('input[type="text"], input:not([type])');
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
                            field: fieldName,
                            value: value,
                            inputsFound: inputs.length,
                        };
                    }
                }
                return {
                    success: false,
                    error:
                        'Input not found in row for field: ' +
                        fieldName +
                        ' (row had ' +
                        inputs.length +
                        ' inputs)',
                    debug,
                    rowName: rowName.substring(0, 100),
                };
            }
        }
    }
    // Limit debug output to first 20 fields
    debug.fieldsAvailable = debug.fieldsAvailable.slice(0, 20);
    debug.buttonsFound = debug.buttonsFound.slice(0, 30);
    return { success: false, error: 'Field not found: ' + fieldName, debug };
};
