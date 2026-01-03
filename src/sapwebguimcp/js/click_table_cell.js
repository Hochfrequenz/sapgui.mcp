(params) => {
    const { row, column, action } = params;

    /**
     * Escape special CSS characters for use in selectors.
     */
    function escapeCssSelector(id) {
        return (
            '#' +
            id
                .split('')
                .map((char) => (':[]#,'.includes(char) ? '\\' + char : char))
                .join('')
        );
    }

    /**
     * Check if a cell element is a clickable hotspot.
     */
    function isHotspotCell(element) {
        const lsdata = element.getAttribute('lsdata');
        if (!lsdata) return false;
        try {
            const parsed = JSON.parse(lsdata);
            return parsed['23'] === 'UNDERLINE_HOTSPOT';
        } catch {
            return lsdata.includes('UNDERLINE_HOTSPOT');
        }
    }

    // Find ALV grid table
    const alvTable = document.querySelector('table[ct="STCS"]');
    if (!alvTable) {
        return { error: 'No ALV grid found on current screen' };
    }

    const tableId = alvTable.id;

    // Resolve column if it's a string (header name)
    let colIndex = column;
    if (typeof column === 'string') {
        // Find column index by header text
        let idx = 0;
        let found = false;
        while (true) {
            const headerCell = document.getElementById(`grid#${tableId}#0,${idx}`);
            if (!headerCell) break;
            const headerText = headerCell.textContent.trim();
            if (headerText === column) {
                colIndex = idx;
                found = true;
                break;
            }
            idx++;
        }
        if (!found) {
            return { error: `Column "${column}" not found in table headers` };
        }
    }

    // Build cell IDs
    const cellId = `grid#${tableId}#${row},${colIndex}`;
    const innerSpanId = `${cellId}#if`;

    // Find the elements
    const cellElement = document.getElementById(cellId);
    const innerSpan = document.getElementById(innerSpanId);

    if (!cellElement && !innerSpan) {
        return { error: `Cell at row ${row}, column ${colIndex} not found` };
    }

    // Determine click target
    const isHotspot = innerSpan && isHotspotCell(innerSpan);
    const clickTarget = isHotspot && innerSpan ? innerSpan : cellElement;
    const targetId = isHotspot && innerSpan ? innerSpanId : cellId;

    // Return the selector and metadata - actual click will be done by Python
    return {
        selector: escapeCssSelector(targetId),
        wasHotspot: isHotspot,
        row: row,
        column: colIndex,
        tableId: tableId,
    };
};
