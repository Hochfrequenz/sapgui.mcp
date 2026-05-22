(params) => {
    const { startRow, endRow, maxRows } = params;

    /**
     * Escape special CSS characters for use in selectors.
     * SAP ALV grids use IDs like "grid#C120#1,2#if" which need escaping.
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
     * Hotspots have lsdata["23"] = "UNDERLINE_HOTSPOT".
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

    /**
     * Extract data from SAP ALV grid (table with ct="STCS").
     */
    function extractAlvGrid(alvTable) {
        const tableId = alvTable.id;
        const headers = [];
        const rows = [];
        const hotspotColumns = [];
        const columnMap = {};

        // Parse selection mode from lsdata
        let selectionMode = 'NONE';
        const tableLsdata = alvTable.getAttribute('lsdata');
        if (tableLsdata) {
            try {
                const parsed = JSON.parse(tableLsdata);
                if (parsed['10']) selectionMode = parsed['10'];
            } catch {
                // Ignore parse errors
            }
        }

        // Find header cells (row 0 in grid pattern)
        // Headers are in elements like grid#C120#0,1, grid#C120#0,2, etc.
        let colIdx = 0;
        while (true) {
            const headerCell = document.getElementById(`grid#${tableId}#0,${colIdx}`);
            if (!headerCell) break;

            const headerText = headerCell.textContent.trim().substring(0, 50);
            headers.push(headerText);
            columnMap[headerText] = colIdx;

            // Check if this column has hotspots by checking first data row
            const firstDataCell = document.getElementById(`grid#${tableId}#1,${colIdx}#if`);
            if (firstDataCell && isHotspotCell(firstDataCell)) {
                hotspotColumns.push(colIdx);
            }

            colIdx++;
        }

        // If no grid# pattern headers found, fall back to DOM traversal
        if (headers.length === 0) {
            const headerCells = alvTable.querySelectorAll('[role="columnheader"], th');
            headerCells.forEach((cell, idx) => {
                const text = cell.textContent.trim().substring(0, 50);
                headers.push(text);
                columnMap[text] = idx;
            });
        }

        // Extract data rows
        const maxEnd = startRow + maxRows - 1;
        const actualEndRow = endRow ? Math.min(endRow, maxEnd) : maxEnd;

        for (let rowNum = startRow; rowNum <= actualEndRow; rowNum++) {
            const rowData = {};
            const cellsInfo = {};
            let hasData = false;

            for (let col = 0; col < headers.length; col++) {
                const headerName = headers[col] || `col_${col + 1}`;

                // Try grid# pattern first (SAP ALV standard), then bracket
                // notation tableId[row,col] (used by SE24 editable grids).
                const gridCellId = `grid#${tableId}#${rowNum},${col}`;
                const gridSpanId = `${gridCellId}#if`;
                const bracketCellId = `${tableId}[${rowNum},${col}]`;

                let cellElement =
                    document.getElementById(gridCellId) || document.getElementById(bracketCellId);
                let innerSpan = document.getElementById(gridSpanId);
                const cellId = cellElement ? cellElement.id : gridCellId;

                // Get cell text — for editable grids (e.g., SE24 methods),
                // cells contain <input> elements whose values are not in textContent.
                let cellText = '';
                if (innerSpan) {
                    cellText = innerSpan.textContent.trim().substring(0, 200);
                } else if (cellElement) {
                    cellText = cellElement.textContent.trim().substring(0, 200);
                }
                if (!cellText && cellElement) {
                    const input = cellElement.querySelector('input, textarea');
                    if (input) cellText = (input.value || '').trim().substring(0, 200);
                }

                if (cellText) {
                    rowData[headerName] = cellText;
                    hasData = true;

                    // Determine click target and build selector
                    // Use Boolean() to ensure we return true/false, not null/undefined
                    const isHotspot = Boolean(innerSpan && isHotspotCell(innerSpan));
                    const clickTarget = isHotspot ? gridSpanId : cellId;
                    const selector = escapeCssSelector(clickTarget);

                    cellsInfo[headerName] = {
                        selector: selector,
                        clickable: true,
                        hotspot: isHotspot,
                    };
                }
            }

            if (hasData) {
                rows.push({
                    row: rowNum,
                    data: rowData,
                    cells: cellsInfo,
                });
            } else {
                // No more data rows
                break;
            }
        }

        return {
            headers: headers,
            rows: rows,
            totalRows: rows.length,
            startRow: startRow,
            endRow: rows.length > 0 ? rows[rows.length - 1].row : startRow,
            alv: {
                table_id: tableId,
                selection_mode: selectionMode,
                hotspot_columns: hotspotColumns,
                column_map: columnMap,
            },
        };
    }

    /**
     * Extract data from a regular (non-ALV) table.
     */
    function extractRegularTable(table) {
        const headers = [];
        const headerCells = table.querySelectorAll("th, [role='columnheader']");
        headerCells.forEach((cell) => {
            const text = cell.textContent.trim().substring(0, 50);
            headers.push(text);
        });

        // If no headers found in th, try first row
        if (headers.length === 0) {
            const firstRow = table.querySelector('tr');
            if (firstRow) {
                firstRow.querySelectorAll('td').forEach((cell) => {
                    const text = cell.textContent.trim().substring(0, 50);
                    headers.push(text);
                });
            }
        }

        // Get rows with limits
        const rows = [];
        const dataRows = table.querySelectorAll("tbody tr, tr[role='row']");
        const maxEnd = startRow + maxRows - 1;
        const actualEndRow = endRow ? Math.min(endRow, maxEnd) : Math.min(dataRows.length, maxEnd);

        // Track which columns have data
        const columnsWithData = new Set();

        for (let i = startRow - 1; i < Math.min(actualEndRow, dataRows.length); i++) {
            const row = dataRows[i];
            if (!row) continue;

            const cells = row.querySelectorAll("td, [role='gridcell']");
            const rowData = {};

            cells.forEach((cell, idx) => {
                let cellText = cell.textContent.trim().substring(0, 200);
                // For editable grids (e.g., SE24 methods), cells contain input elements
                // whose values are not captured by textContent.
                if (!cellText) {
                    const input = cell.querySelector('input, textarea');
                    if (input) cellText = (input.value || '').trim().substring(0, 200);
                }
                if (cellText) {
                    const headerName = headers[idx] || `col_${idx + 1}`;
                    rowData[headerName] = cellText;
                    columnsWithData.add(headerName);
                }
            });

            if (Object.keys(rowData).length > 0) {
                rows.push({ row: i + 1, data: rowData });
            }
        }

        // Filter headers to only include columns that have data
        const usedHeaders = headers.filter(
            (h, idx) => columnsWithData.has(h) || columnsWithData.has(`col_${idx + 1}`)
        );

        return {
            headers: usedHeaders,
            totalRows: dataRows.length,
            returnedRows: rows.length,
            truncated: dataRows.length > actualEndRow,
            rows: rows,
        };
    }

    // Main logic: detect ALV grid first, then fall back to regular table
    const alvTable = document.querySelector('table[ct="STCS"]');
    if (alvTable) {
        return extractAlvGrid(alvTable);
    }

    // Find regular table elements
    const tableSelectors = [
        'table[role="grid"]',
        '.sapMList table',
        'table.urTbl',
        '[role="treegrid"]',
        'table',
    ];

    let table = null;
    for (const selector of tableSelectors) {
        table = document.querySelector(selector);
        if (table) break;
    }

    if (!table) {
        return { error: 'No table found on current screen' };
    }

    return extractRegularTable(table);
};
