(args) => {
    // Find a filter field in SE16N selection criteria grid by row index
    // Returns the CSS selector for use with Playwright's native fill()
    //
    // SAP Web GUI uses lsdata attributes on elements that contain row/column indices:
    // Example: lsdata="...SELFIELDS-LOW[2,0]" means column 2, row 0
    // The row index in lsdata matches the field order from SE11.
    const rowIndex = args.rowIndex;  // 0-based index matching SE11 field order
    const fieldName = args.fieldName || '';  // Optional, for error messages
    const debug = { strategy: '', inputsFound: 0 };

    // First, find the selection criteria grid
    const grids = document.querySelectorAll('[role="grid"]');
    let selectionGrid = null;
    for (const grid of grids) {
        const gridText = grid.textContent || '';
        if (gridText.includes('Feldname') || gridText.includes('Field') ||
            gridText.includes('Von-Wert') || gridText.includes('From-Value') ||
            gridText.includes('Selektionskriterien')) {
            selectionGrid = grid;
            break;
        }
    }

    if (!selectionGrid) {
        return {
            success: false,
            error: 'Selection criteria grid not found',
            debug: { gridsFound: grids.length }
        };
    }

    // Pattern to match: SELFIELDS-LOW[col,rowIndex]
    const lsdataPattern = `SELFIELDS-LOW`;
    const rowPattern = `,${rowIndex}]`;

    // Strategy 1: Find textbox by lsdata pattern in grid
    const gridTextboxes = selectionGrid.querySelectorAll('[role="textbox"]');
    debug.gridTextboxes = gridTextboxes.length;

    for (const textbox of gridTextboxes) {
        const lsdata = textbox.getAttribute('lsdata') || '';
        if (lsdata.includes(lsdataPattern) && lsdata.includes(rowPattern)) {
            debug.strategy = 'grid-textbox-lsdata';

            // Found the textbox - now find actual input inside or the textbox itself
            let actualInput = textbox.querySelector('input');
            if (actualInput) {
                // Return selector for the input element
                return {
                    success: true,
                    rowIndex,
                    fieldName,
                    strategy: 'grid-textbox-input',
                    selector: actualInput.id ? `#${actualInput.id}` : `[lsdata*="SELFIELDS-LOW"][lsdata*=",${rowIndex}]"] input`,
                    elementId: actualInput.id || textbox.id,
                    elementType: 'input'
                };
            }

            // If no input, check if the textbox has contenteditable or is itself an input
            if (textbox.getAttribute('contenteditable') === 'true') {
                return {
                    success: true,
                    rowIndex,
                    fieldName,
                    strategy: 'grid-textbox-contenteditable',
                    selector: textbox.id ? `#${textbox.id}` : `[role="textbox"][lsdata*="SELFIELDS-LOW"][lsdata*=",${rowIndex}]"]`,
                    elementId: textbox.id,
                    elementType: 'contenteditable'
                };
            }

            // Return textbox selector - Playwright will handle clicking it
            return {
                success: true,
                rowIndex,
                fieldName,
                strategy: 'grid-textbox-direct',
                selector: textbox.id ? `#${textbox.id}` : null,
                elementId: textbox.id,
                elementType: 'textbox',
                lsdata: lsdata.substring(0, 100)
            };
        }
    }

    // Strategy 2: Search ALL inputs on page for SELFIELDS-LOW pattern
    const allInputs = document.querySelectorAll('input[lsdata]');
    debug.inputsFound = allInputs.length;

    for (const input of allInputs) {
        const lsdata = input.getAttribute('lsdata') || '';
        if (lsdata.includes(lsdataPattern) && lsdata.includes(rowPattern)) {
            return {
                success: true,
                rowIndex,
                fieldName,
                strategy: 'input-lsdata',
                selector: input.id ? `#${input.id}` : `input[lsdata*="SELFIELDS-LOW"][lsdata*=",${rowIndex}]"]`,
                elementId: input.id,
                elementType: 'input'
            };
        }
    }

    // Strategy 3: Try regex matching
    for (const input of allInputs) {
        const lsdata = input.getAttribute('lsdata') || '';
        if (lsdata.includes('SELFIELDS-LOW')) {
            const match = lsdata.match(/\[(\d+),(\d+)\]/);
            if (match && parseInt(match[2]) === rowIndex) {
                return {
                    success: true,
                    rowIndex,
                    fieldName,
                    strategy: 'input-lsdata-regex',
                    selector: input.id ? `#${input.id}` : null,
                    elementId: input.id,
                    elementType: 'input'
                };
            }
        }
    }

    // Collect debug samples
    const sampleTextboxes = [];
    for (let i = 0; i < Math.min(5, gridTextboxes.length); i++) {
        const tb = gridTextboxes[i];
        sampleTextboxes.push({
            id: tb.id,
            lsdata: (tb.getAttribute('lsdata') || '').substring(0, 80)
        });
    }
    debug.sampleTextboxes = sampleTextboxes;

    return {
        success: false,
        error: `No input found for row ${rowIndex} field '${fieldName}'`,
        debug
    };
};
