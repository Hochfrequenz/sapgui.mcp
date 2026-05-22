() => {
    // Fast check for blocking popup layer
    // Check both by ID and by class for maximum compatibility
    const blockingLayer = document.querySelector('#urPopupWindowBlockLayer, .lsBlockLayer');

    if (!blockingLayer) {
        return null; // No popup blocking
    }

    // Check if blocking layer is actually visible (not just present)
    const layerStyle = window.getComputedStyle(blockingLayer);
    if (layerStyle.display === 'none' || layerStyle.visibility === 'hidden') {
        return null; // Blocking layer exists but is hidden
    }

    // Find popup container (various SAP popup types)
    // Order matters: more specific selectors first
    const popupSelectors = [
        '.lsPWNew', // SAP Fiori-style popup (most common)
        "[class*='lsPopupWindow']", // Fallback for popup window variants
        '.urPopupWindow', // Classic WebGUI popup
        '.lsPopup', // Legacy popup
        "[class*='urMessageBox']", // Message box variant
    ];

    let popup = null;
    for (const sel of popupSelectors) {
        popup = document.querySelector(sel);
        if (popup) break;
    }

    // Extract message text from popup
    // SAP popups store the message in different places depending on type:
    // - Header title (lsPWNewHeaderTextOverflow) for confirmation dialogs
    // - Content section (lsPWNewContentSection) for validation errors
    let message = null;
    const messageSelectors = [
        // Header title - most common for confirmation dialogs
        '.lsPWNewHeaderTextOverflow span',
        '.lsPWNewHeaderTextOverflow',
        "[class*='header-title-txt']",
        // Content section - for validation errors and longer messages
        '.lsPWNewContentSection .urMessageText',
        '.lsPWNewContentSection .lsPopupText',
        ".lsPWNewContentSection span:not([class*='Button'])",
        '.urMessageText',
        '.lsPopupText',
        '.urMsgBoxText',
        "[class*='MessageText']",
        '.sapMText',
    ];

    for (const sel of messageSelectors) {
        const el = popup?.querySelector(sel) || document.querySelector(sel);
        const text = el?.textContent?.trim();
        // Skip if text is empty or looks like just button labels (short, common words)
        if (
            text &&
            text.length > 3 &&
            !['ja', 'nein', 'ok', 'cancel', 'abbrechen'].includes(text.toLowerCase())
        ) {
            message = text;
            break;
        }
    }

    // If still no message, try header title directly
    if (!message && popup) {
        const headerTitle = popup.querySelector(
            "[class*='HeaderTextOverflow'], [class*='header-title']"
        );
        if (headerTitle?.textContent?.trim()) {
            message = headerTitle.textContent.trim();
        }
    }

    // Try to extract body text from iframes in the popup (SAP uses iframes for some messages)
    // Store header title separately so we can combine with iframe body
    const headerTitle = message;
    let iframeBody = null;
    if (popup) {
        const iframes = popup.querySelectorAll('iframe');
        for (const iframe of iframes) {
            try {
                const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
                if (iframeDoc) {
                    // Look for text in the iframe body
                    const bodyText = iframeDoc.body?.textContent?.trim().replace(/\s+/g, ' ');
                    if (bodyText && bodyText.length > 3) {
                        iframeBody = bodyText;
                        break;
                    }
                }
            } catch (e) {
                // Cross-origin iframe, can't access content
            }
        }
    }

    // Combine header title with iframe body if both exist
    if (headerTitle && iframeBody) {
        message = `${headerTitle}: ${iframeBody}`;
    } else if (iframeBody) {
        message = iframeBody;
    }

    // Extract buttons from popup
    const buttons = [];
    const buttonSelectors = [
        '.lsPWNew button', // SAP Fiori-style popup buttons
        ".lsPWNew [role='button']",
        '.lsPWNewFooterSection button', // Footer buttons specifically
        "[class*='lsPopupWindow'] button",
        "[class*='lsPopupWindow'] [role='button']",
        '.urPopupWindow button',
        '.lsPopup button',
        "[class*='urMessageBox'] button",
        '.urBtnStd',
    ];
    const seenLabels = new Set();

    for (const sel of buttonSelectors) {
        const btns = document.querySelectorAll(sel);
        for (const btn of btns) {
            const label = btn.textContent?.trim();
            if (!label || seenLabels.has(label.toLowerCase())) continue;
            seenLabels.add(label.toLowerCase());

            buttons.push({
                label: label,
                accesskey: btn.getAttribute('accesskey') || null,
                id: btn.id || null,
            });
        }
    }

    // Find close button (X in corner)
    let closeButtonId = null;
    const closeSelectors = [
        ".lsPWNew [class*='close']",
        ".lsPWNew [title*='Close']",
        ".lsPWNew [title*='Schlie']", // German "Schließen"
        "[class*='urPopup'] [class*='close']",
        "[class*='urPopup'] [title*='Close']",
        "[class*='urPopup'] [title*='Schlie']",
        '.urPopupClose',
        "button[id*='close' i]",
    ];
    for (const sel of closeSelectors) {
        const closeBtn = document.querySelector(sel);
        if (closeBtn?.id) {
            closeButtonId = closeBtn.id;
            break;
        }
    }

    return {
        message: message,
        buttons: buttons,
        close_button_id: closeButtonId,
    };
};
