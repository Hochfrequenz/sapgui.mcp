(args) => {
    // Read the rows of the SE16N selection-criteria grid so the caller can place a filter by the
    // row's TECHNICAL FIELD NAME instead of by position.
    //
    // SE16N does not offer every SE11 field as a selection field; when it leaves one out, positions
    // shift and an index taken from SE11 lands on the wrong row (#924).
    //
    // The Web GUI renders this grid as a split table: the label column and the other columns sit in
    // different <tr> elements, so DOM containment does not pair them. Every cell does carry an lsdata
    // SID naming its column and position, e.g. "...txtGS_SELFIELDS-FIELDNAME[6,0]" or
    // "...ctxtGS_SELFIELDS-LOW[2,0]" (column, row). Cells are grouped by that row number.
    //
    // Per row we return:
    //   rowIndex   the row number from the SID
    //   label      the field's description (column SCRTEXT_M)
    //   fieldName  upper-case technical name (column FIELDNAME), or null when not in the DOM
    //   fillable   whether the From-Value (column LOW) is an input; false for rows SE16N shows
    //              but does not offer for selection (e.g. the client field)
    //   elementId, selector, elementType   the From-Value input to fill (null when not fillable)
    // The grid is rendered only partly (about 30 rows) and is not scrolled here: fields further down
    // the table are not in the DOM at all. The grid is padded with empty rows when the table has fewer
    // fields than that, so "no empty row" means the table may continue below what is rendered.
    const sidPattern = /GS_SELFIELDS-(SCRTEXT_M|FIELDNAME|LOW)\[(\d+),(\d+)\]/;
    const technicalName = /^[A-Za-z0-9_\/]+$/;

    // Find the selection criteria grid: by (DE/EN) column headers, else by SELFIELDS cells.
    const grids = document.querySelectorAll('[role="grid"]');
    let selectionGrid = null;
    for (const grid of grids) {
        const gridText = grid.textContent || '';
        if (
            gridText.includes('Feldname') ||
            gridText.includes('Field Name') ||
            gridText.includes('Von-Wert') ||
            gridText.includes('From Value') ||
            gridText.includes('From-Value') ||
            gridText.includes('Selektionskriterien') ||
            gridText.includes('Selection Criteria')
        ) {
            selectionGrid = grid;
            break;
        }
    }
    if (!selectionGrid) {
        for (const grid of grids) {
            if (grid.querySelector('[lsdata*="GS_SELFIELDS-"]')) {
                selectionGrid = grid;
                break;
            }
        }
    }
    if (!selectionGrid) {
        return {
            success: false,
            error: 'Selection criteria grid not found',
            debug: { gridsFound: grids.length },
        };
    }

    const byRow = new Map();
    const entryFor = (rowIndex) => {
        if (!byRow.has(rowIndex)) {
            byRow.set(rowIndex, {
                rowIndex,
                label: '',
                fieldName: null,
                fillable: false,
                elementId: null,
                selector: null,
                elementType: null,
            });
        }
        return byRow.get(rowIndex);
    };

    for (const element of selectionGrid.querySelectorAll('[lsdata*="GS_SELFIELDS-"]')) {
        const match = (element.getAttribute('lsdata') || '').match(sidPattern);
        if (!match) {
            continue;
        }
        const column = match[1];
        const columnIndex = parseInt(match[2], 10);
        const rowIndex = parseInt(match[3], 10);
        const entry = entryFor(rowIndex);
        const text = (element.textContent || '').trim();

        if (column === 'SCRTEXT_M') {
            if (!entry.label && text) {
                entry.label = text;
            }
        } else if (column === 'FIELDNAME') {
            if (!entry.fieldName && technicalName.test(text)) {
                entry.fieldName = text.toUpperCase();
            }
        } else if (column === 'LOW' && !entry.fillable) {
            // The cell wrapper (a <td>) is not an input; the control inside it is.
            const isControl =
                element.getAttribute('role') === 'textbox' || element.tagName === 'INPUT';
            if (!isControl) {
                continue;
            }
            const input = element.tagName === 'INPUT' ? element : element.querySelector('input');
            const target = input || element;
            entry.fillable = true;
            entry.elementId = target.id || null;
            entry.elementType = input ? 'input' : 'textbox';
            // Without an id, address the control by its SID. The cell wrapper carries the same SID, so
            // qualify by what the target is: the textbox itself, an input carrying the SID, or the
            // input nested in the textbox.
            const sid = `[lsdata*="GS_SELFIELDS-LOW[${columnIndex},${rowIndex}]"]`;
            let selector = `[role="textbox"]${sid}`;
            if (element.tagName === 'INPUT') {
                selector = `input${sid}`;
            } else if (input) {
                selector = `[role="textbox"]${sid} input`;
            }
            entry.selector = target.id ? `[id="${target.id}"]` : selector;
        }
    }

    const rows = [...byRow.values()].sort((a, b) => a.rowIndex - b.rowIndex);
    const hasPaddingRows = rows.some((row) => !row.label && !row.fieldName && !row.fillable);
    return {
        success: true,
        rows,
        renderedRows: rows.length,
        hasPaddingRows,
    };
};
