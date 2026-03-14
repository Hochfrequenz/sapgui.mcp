() => {
    // Various SAP Web GUI status bar selectors - ordered from most to least specific
    const statusSelectors = [
        '#LSMSG_AREA', // Classic status area (most reliable)
        '.urMsgBarTxt', // SAP message bar text element
        '.sapMSGtext', // SAPUI5 message text
        '#\\~MSGLINE', // Message line in selection screens
        '[id*="msgline" i]', // Message line variations
    ];

    let statusElement = null;
    let message = '';

    // Helper function to clean up status bar text by removing toolbar/button garbage
    const cleanStatusText = (text) => {
        if (!text) return '';

        // Remove common toolbar button labels and UI garbage
        // These appear when the selector captures the whole status bar container
        const garbagePatterns = [
            /Meldungsleiste/gi, // "Status bar" label in German
            /Details anzeigen/gi, // "Show details" button
            /Ausführen/gi, // "Execute" button
            /Hervorgehoben/gi, // "Highlighted" button state
            /\s*x\s*$/gi, // Close button "x" at end
            /[\ufffd]/g, // Replacement character (encoding issue)
        ];

        let cleaned = text;
        for (const pattern of garbagePatterns) {
            cleaned = cleaned.replace(pattern, ' ');
        }

        // Collapse multiple spaces and trim
        cleaned = cleaned.replace(/\s+/g, ' ').trim();

        // If we have duplicate messages (e.g., "Pull successful Pull successful"), take the first
        const parts = cleaned.split(/\s{2,}/);
        if (parts.length > 1) {
            cleaned = parts[0].trim();
        }

        return cleaned;
    };

    for (const selector of statusSelectors) {
        statusElement = document.querySelector(selector);
        if (statusElement) {
            // First, try to find a specific text element within the status area
            const textSpan = statusElement.querySelector(
                '.lsMsgText, .urMsgText, span:not([class*="btn"]):not([class*="Btn"])'
            );
            if (textSpan) {
                message = cleanStatusText(textSpan.textContent);
            } else {
                // Fall back to the container's text content and clean it up
                message = cleanStatusText(statusElement.textContent);
            }

            if (message && message.length > 0) {
                break;
            }
            message = ''; // Reset and try next selector
        }
    }

    // If still no message, try broader selectors as last resort
    if (!message) {
        const broadSelectors = ['[id*="StatusBar" i]', '[class*="msgbar" i]', '[id*="msgarea" i]'];
        for (const selector of broadSelectors) {
            statusElement = document.querySelector(selector);
            if (statusElement) {
                // Look for the actual message text element within
                const msgText = statusElement.querySelector(
                    '.lsMsgText, .urMsgText, [class*="msgtext" i]'
                );
                if (msgText) {
                    message = cleanStatusText(msgText.textContent);
                    if (message) break;
                } else {
                    // Try the whole container and clean it
                    message = cleanStatusText(statusElement.textContent);
                    if (message) break;
                }
            }
        }
    }

    if (!message) {
        return { type: 'none', message: '' };
    }

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
