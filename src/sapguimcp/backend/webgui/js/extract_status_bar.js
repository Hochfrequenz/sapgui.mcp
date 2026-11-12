(params) => {
    // Texts come from the language packs, merged over every language (#1044):
    // texts.noise - message-bar control texts (its label, buttons) that are not part of the message
    // texts.error / texts.warning / texts.success - keywords that infer the message type
    // texts.checkSuccess - syntax check success messages that contain error words, tested before error
    const { texts } = params;
    const matches = (text, message) => new RegExp(text.source, text.flags).test(message);

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

    // The dedicated message-text elements hold the message only; their text is never noise-filtered,
    // so message words such as "Executed" or "Ausführen" stay intact.
    const MESSAGE_TEXT = '.lsMsgText, .urMsgText, [class*="msgtext" i]';

    // Helper function to clean up status bar text by removing toolbar/button garbage.
    // stripNoise: the text is a container's or a generic span's textContent, which can hold the
    // message bar's own label and buttons ("Message Bar", "View Details", "Execute", ...).
    const cleanStatusText = (text, stripNoise) => {
        if (!text) return '';

        // Remove common toolbar button labels and UI garbage
        // These appear when the selector captures the whole status bar container
        const garbagePatterns = [
            // case-sensitive noise of the message bar, only outside the message-text elements
            ...(stripNoise ? [new RegExp(texts.noise.source, texts.noise.flags + 'g')] : []),
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
                message = cleanStatusText(textSpan.textContent, !textSpan.matches(MESSAGE_TEXT));
            } else {
                // Fall back to the container's text content and clean it up
                message = cleanStatusText(statusElement.textContent, true);
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
                const msgText = statusElement.querySelector(MESSAGE_TEXT);
                if (msgText) {
                    message = cleanStatusText(msgText.textContent, false);
                    if (message) break;
                } else {
                    // Try the whole container and clean it
                    message = cleanStatusText(statusElement.textContent, true);
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

    // Check for error indicators (CSS class names are English in every logon language)
    if (
        parentClasses.includes('error') || // lang-ok: CSS class name
        statusElement.querySelector('[class*="error" i], .sapMsgError')
    ) {
        type = 'E';
    }
    // Check for warning indicators
    else if (
        parentClasses.includes('warning') || // lang-ok: CSS class name
        statusElement.querySelector('[class*="warning" i], .sapMsgWarning')
    ) {
        type = 'W';
    }
    // Check for success indicators
    else if (
        parentClasses.includes('success') || // lang-ok: CSS class name
        statusElement.querySelector('[class*="success" i], .sapMsgSuccess')
    ) {
        type = 'S';
    }

    // Also check message content for common patterns (case-insensitive substrings)
    if (type === 'I') {
        // Only override if not already detected
        // checkSuccess first: "No syntax errors found" contains an error keyword (#1088);
        // "No syntax errors, but some warnings exist" is still a warning
        if (matches(texts.checkSuccess, message)) {
            type = matches(texts.warning, message) ? 'W' : 'S';
        } else if (matches(texts.error, message)) {
            type = 'E';
        } else if (matches(texts.warning, message)) {
            type = 'W';
        } else if (matches(texts.success, message)) {
            type = 'S';
        }
    }

    return { type: type, message: message };
};
