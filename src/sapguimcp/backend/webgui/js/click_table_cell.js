(params) => {
    const { row, column, action, performClick } = params;

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
    const isHotspot = Boolean(innerSpan && isHotspotCell(innerSpan));
    const clickTarget = isHotspot && innerSpan ? innerSpan : cellElement;
    const targetId = isHotspot && innerSpan ? innerSpanId : cellId;

    // If performClick is true, simulate a complete mouse interaction
    // SAP WebGUI uses event delegation that requires realistic mouse events
    if (performClick && clickTarget) {
        // Scroll element into view first
        clickTarget.scrollIntoView({ block: 'center', inline: 'center' });

        // Get element position for realistic event coordinates
        const rect = clickTarget.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;

        const eventOptions = {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: x,
            clientY: y,
            screenX: x,
            screenY: y,
            button: 0,
            buttons: 1,
        };

        // Dispatch complete mouse event sequence for SAP event handlers
        if (action === 'dblclick') {
            // Double-click sequence: mousedown, mouseup, click, mousedown, mouseup, click, dblclick
            clickTarget.dispatchEvent(new MouseEvent('mousedown', eventOptions));
            clickTarget.dispatchEvent(new MouseEvent('mouseup', eventOptions));
            clickTarget.dispatchEvent(new MouseEvent('click', eventOptions));
            clickTarget.dispatchEvent(new MouseEvent('mousedown', eventOptions));
            clickTarget.dispatchEvent(new MouseEvent('mouseup', eventOptions));
            clickTarget.dispatchEvent(new MouseEvent('click', eventOptions));
            clickTarget.dispatchEvent(new MouseEvent('dblclick', eventOptions));
        } else {
            // Single click sequence: mousedown, mouseup, click
            clickTarget.dispatchEvent(new MouseEvent('mousedown', eventOptions));
            clickTarget.dispatchEvent(new MouseEvent('mouseup', eventOptions));
            clickTarget.dispatchEvent(new MouseEvent('click', eventOptions));
        }
    }

    return {
        selector: escapeCssSelector(targetId),
        wasHotspot: isHotspot,
        row: row,
        column: colIndex,
        tableId: tableId,
        clicked: Boolean(performClick),
    };
};
