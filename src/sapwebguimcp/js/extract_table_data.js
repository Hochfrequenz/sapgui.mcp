(params) => {
    const { startRow, endRow, maxRows } = params;

    // Find table elements (various SAP table implementations)
    const tableSelectors = [
        'table[role="grid"]', // ALV Grid
        '.sapMList table', // SAPUI5 List
        'table.urTbl', // Classic SAP table
        '[role="treegrid"]', // Tree grid
        'table', // Fallback to any table
    ];

    let table = null;
    for (const selector of tableSelectors) {
        table = document.querySelector(selector);
        if (table) break;
    }

    if (!table) {
        return { error: 'No table found on current screen' };
    }

    // Get headers
    const headers = [];
    const headerCells = table.querySelectorAll('th, [role="columnheader"]');
    headerCells.forEach((cell) => {
        // Limit header text length and clean whitespace
        let text = cell.textContent.trim().substring(0, 50);
        headers.push(text);
    });

    // If no headers found in th, try first row
    if (headers.length === 0) {
        const firstRow = table.querySelector('tr');
        if (firstRow) {
            firstRow.querySelectorAll('td').forEach((cell) => {
                let text = cell.textContent.trim().substring(0, 50);
                headers.push(text);
            });
        }
    }

    // Get rows with limits
    const rows = [];
    const dataRows = table.querySelectorAll('tbody tr, tr[role="row"]');
    const maxEnd = startRow + maxRows - 1;
    const actualEndRow = endRow ? Math.min(endRow, maxEnd) : Math.min(dataRows.length, maxEnd);

    // Track which columns have data (to filter out empty columns)
    const columnsWithData = new Set();

    for (let i = startRow - 1; i < Math.min(actualEndRow, dataRows.length); i++) {
        const row = dataRows[i];
        if (!row) continue;

        const cells = row.querySelectorAll('td, [role="gridcell"]');
        const rowData = {};

        cells.forEach((cell, idx) => {
            // Limit cell text to 200 chars to prevent huge values
            let cellText = cell.textContent.trim().substring(0, 200);
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
};
