() => {
    // Various SAP Web GUI status bar selectors
    const statusSelectors = [
        '#LSMSG_AREA', // Classic status area
        '.urMsgBarTxt', // SAP message bar
        '.sapMSGtext', // SAPUI5 message
        '[id*="StatusBar" i]', // Status bar variations
        '[class*="msgbar" i]', // Message bar variations
        '[id*="msgarea" i]', // Message area
    ];

    let statusElement = null;
    for (const selector of statusSelectors) {
        statusElement = document.querySelector(selector);
        if (statusElement && statusElement.textContent.trim()) {
            break;
        }
    }

    if (!statusElement || !statusElement.textContent.trim()) {
        return { type: 'none', message: '' };
    }

    const message = statusElement.textContent.trim();

    // Determine message type based on CSS classes or icons
    let type = 'I'; // Default to info

    const parentClasses = (
        statusElement.className +
        ' ' +
        (statusElement.parentElement?.className || '')
    ).toLowerCase();

    // Check for error indicators
    if (
        parentClasses.includes('error') ||
        parentClasses.includes('fehler') ||
        statusElement.querySelector('[class*="error" i], .sapMsgError')
    ) {
        type = 'E';
    }
    // Check for warning indicators
    else if (
        parentClasses.includes('warning') ||
        parentClasses.includes('warnung') ||
        statusElement.querySelector('[class*="warning" i], .sapMsgWarning')
    ) {
        type = 'W';
    }
    // Check for success indicators
    else if (
        parentClasses.includes('success') ||
        parentClasses.includes('erfolg') ||
        statusElement.querySelector('[class*="success" i], .sapMsgSuccess')
    ) {
        type = 'S';
    }

    // Also check message content for common patterns
    const msgLower = message.toLowerCase();
    if (type === 'I') {
        // Only override if not already detected
        if (
            msgLower.includes('fehler') ||
            msgLower.includes('error') ||
            msgLower.includes('nicht gefunden') ||
            msgLower.includes('not found') ||
            msgLower.includes('ungültig') ||
            msgLower.includes('invalid')
        ) {
            type = 'E';
        } else if (msgLower.includes('warnung') || msgLower.includes('warning')) {
            type = 'W';
        } else if (
            msgLower.includes('gesichert') ||
            msgLower.includes('saved') ||
            msgLower.includes('angelegt') ||
            msgLower.includes('created') ||
            msgLower.includes('erfolgreich') ||
            msgLower.includes('successful')
        ) {
            type = 'S';
        }
    }

    return { type: type, message: message };
};
