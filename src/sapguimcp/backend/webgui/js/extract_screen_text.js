() => {
    const result = {
        title: document.title,
        statusBar: '',
        mainContent: [],
        labels: [],
        buttons: [],
        tabs: [],
        tableHeaders: [],
    };

    // Get status bar message
    const statusBar = document.querySelector(
        '.urMsgBarTxt, .sapMSGtext, [class*="message" i], [id*="StatusBar" i]'
    );
    if (statusBar) {
        result.statusBar = statusBar.textContent.trim();
    }

    // Get all labels (for adaptive field discovery)
    document.querySelectorAll('label, .urLbl, [class*="label" i]').forEach((el) => {
        const text = el.textContent.trim();
        if (text && text.length < 100) {
            result.labels.push(text);
        }
    });

    // Get all buttons
    document
        .querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]')
        .forEach((el) => {
            const text = el.textContent.trim() || el.value || el.getAttribute('title') || '';
            if (text && text.length < 50) {
                result.buttons.push(text);
            }
        });

    // Get tab labels
    document.querySelectorAll('[role="tab"], .sapMTabStrip button').forEach((el) => {
        const text = el.textContent.trim();
        if (text) {
            result.tabs.push(text);
        }
    });

    // Get table headers
    document.querySelectorAll('th, [role="columnheader"]').forEach((el) => {
        const text = el.textContent.trim();
        if (text) {
            result.tableHeaders.push(text);
        }
    });

    // Get main content text (limited to avoid too much noise)
    const mainArea = document.querySelector(
        '#content, #MAIN_CONTENT, [role="main"], .sapMPage, body'
    );
    if (mainArea) {
        // Get visible text, excluding scripts and styles
        const walker = document.createTreeWalker(mainArea, NodeFilter.SHOW_TEXT, {
            acceptNode: function (node) {
                const parent = node.parentElement;
                if (!parent) return NodeFilter.FILTER_REJECT;
                const tag = parent.tagName.toLowerCase();
                if (tag === 'script' || tag === 'style' || tag === 'noscript') {
                    return NodeFilter.FILTER_REJECT;
                }
                const text = node.textContent.trim();
                if (text.length > 0 && text.length < 200) {
                    return NodeFilter.FILTER_ACCEPT;
                }
                return NodeFilter.FILTER_REJECT;
            },
        });
        let count = 0;
        while (walker.nextNode() && count < 200) {
            const text = walker.currentNode.textContent.trim();
            if (text && !result.mainContent.includes(text)) {
                result.mainContent.push(text);
                count++;
            }
        }
    }

    return result;
};
