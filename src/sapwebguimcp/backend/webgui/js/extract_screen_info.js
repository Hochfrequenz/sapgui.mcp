() => {
    const info = {
        transaction: '',
        title: document.title,
        url: window.location.href,
        program: '',
        dynpro: '',
    };

    // Try to find transaction code from various locations
    // OK-Code field might contain current transaction
    const okCodeField = document.querySelector('#ToolbarOkCode, input[id*="okcode" i]');
    if (okCodeField && okCodeField.value) {
        info.transaction = okCodeField.value.replace(/^\/[no]/, '');
    }

    // Check title bar for transaction info
    // SAP often shows "Transaction - Description" or similar
    const titleMatch = document.title.match(/^([A-Z0-9_\/]+)\s*[-:]|\(([A-Z0-9_]+)\)/);
    if (titleMatch) {
        info.transaction = info.transaction || (titleMatch[1] || titleMatch[2] || '').trim();
    }

    // Look for technical info in hidden fields or data attributes
    const techInfo = document.querySelector(
        '[data-program], [data-dynpro], [data-tcode], ' +
            'input[name*="program" i], input[name*="dynpro" i]'
    );
    if (techInfo) {
        info.program = techInfo.getAttribute('data-program') || techInfo.getAttribute('name') || '';
        info.dynpro = techInfo.getAttribute('data-dynpro') || '';
    }

    // Try to extract from URL if it contains transaction info
    const urlMatch = window.location.href.match(/[?&](?:tcode|transaction)=([^&]+)/i);
    if (urlMatch) {
        info.transaction = info.transaction || urlMatch[1];
    }

    return info;
};
