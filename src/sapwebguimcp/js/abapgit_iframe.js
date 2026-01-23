/**
 * abapGit iframe utilities.
 *
 * abapGit UI runs inside an iframe within SAP Web GUI. These utilities
 * help locate and interact with elements inside that iframe.
 */

/**
 * Find the abapGit iframe document.
 * @returns {Object} Result with found, id, error fields
 */
function findAbapGitIframe() {
    const iframeCandidates = [
        document.querySelector('iframe#C116'),
        document.querySelector('iframe[id^="C"]'),
        document.querySelector('iframe'),
    ].filter(Boolean);

    for (const candidate of iframeCandidates) {
        try {
            const doc = candidate.contentDocument || candidate.contentWindow?.document;
            if (doc && doc.body?.innerText?.includes('Repository')) {
                return { found: true, id: candidate.id, doc: doc };
            }
        } catch (e) {
            // Ignore cross-origin errors
        }
    }
    return { found: false, error: 'No iframe with abapGit content found' };
}

/**
 * Get the abapGit iframe document or throw error.
 * @returns {Document} The iframe document
 * @throws {Error} If iframe not found
 */
function getAbapGitDoc() {
    const result = findAbapGitIframe();
    if (!result.found) {
        throw new Error(result.error);
    }
    return result.doc;
}

/**
 * Find menu arrow element (expand indicator) in an element.
 * Supports various arrow characters used in different abapGit versions.
 * @param {Element} container - Container element to search in
 * @returns {Element|null} The menu arrow element or null
 */
function findMenuArrow(container) {
    const links = Array.from(container.querySelectorAll('a'));
    return links.find((el) => {
        const text = el.innerText || '';
        // Match common arrow/expand indicators
        return (
            /[▸►▶▷▹▻→›»]/.test(text) ||
            el.classList.contains('expand') ||
            el.getAttribute('title')?.toLowerCase().includes('expand')
        );
    });
}

/**
 * Find a repository row by pattern matching.
 * @param {string} pattern - Pattern to match (name, package, or URL)
 * @returns {Object} Result with found, repoName, row, error fields
 */
function findRepoRow(pattern) {
    let iframeDoc;
    try {
        iframeDoc = getAbapGitDoc();
    } catch (e) {
        return { error: e.message };
    }

    const lowerPattern = pattern.toLowerCase();
    const allRows = Array.from(iframeDoc.querySelectorAll('tr'));
    const repoRow = allRows.find((tr) => {
        const text = (tr.innerText || '').toLowerCase();
        return text.includes(lowerPattern);
    });

    if (!repoRow) {
        return { error: 'Repo not found: ' + pattern };
    }

    // Find menu arrow in this row
    const menuArrow = findMenuArrow(repoRow);
    if (!menuArrow) {
        return { error: 'No menu arrow in repo row' };
    }

    // Extract repo info
    const rowLinks = Array.from(repoRow.querySelectorAll('a'));
    const nameLink = rowLinks.find((a) => a.innerText && !/[▸►▶▷▹▻→›»]/.test(a.innerText));
    const repoName = nameLink?.innerText?.trim() || 'Unknown';

    return {
        found: true,
        repoName: repoName,
        hasMenuArrow: true,
    };
}

/**
 * Click the menu arrow for a repository.
 * @param {string} pattern - Pattern to match the repo
 * @returns {Object} Result with clicked, error fields
 */
function clickMenuArrow(pattern) {
    let iframeDoc;
    try {
        iframeDoc = getAbapGitDoc();
    } catch (e) {
        return { error: e.message };
    }

    const lowerPattern = pattern.toLowerCase();
    const allRows = Array.from(iframeDoc.querySelectorAll('tr'));
    const repoRow = allRows.find((tr) => {
        const text = (tr.innerText || '').toLowerCase();
        return text.includes(lowerPattern);
    });

    if (!repoRow) {
        return { error: 'Repo not found' };
    }

    const menuArrow = findMenuArrow(repoRow);
    if (!menuArrow) {
        return { error: 'No menu arrow found' };
    }

    menuArrow.click();
    return { clicked: true };
}

/**
 * Click an action link (Pull, Stage, etc.) from expanded menu.
 * Supports case-insensitive matching and common translations.
 * @param {string} actionText - Action text to find (e.g., "Pull", "Stage")
 * @returns {Object} Result with clicked, href, error, available fields
 */
function clickAction(actionText) {
    let iframeDoc;
    try {
        iframeDoc = getAbapGitDoc();
    } catch (e) {
        return { error: e.message };
    }

    const allLinks = Array.from(iframeDoc.querySelectorAll('a'));
    const actionLinks = allLinks.filter((a) => a.className?.includes('action_link'));

    // Map of action names to possible variations (EN/DE)
    const actionVariants = {
        pull: ['pull', 'ziehen', 'holen'],
        stage: ['stage', 'bereitstellen', 'staging'],
        diff: ['diff', 'vergleichen', 'unterschiede'],
        check: ['check', 'prüfen', 'syntax check'],
    };

    const searchTerms = actionVariants[actionText.toLowerCase()] || [actionText.toLowerCase()];

    // Find action link (case-insensitive, supports variants)
    const actionLink = actionLinks.find((a) => {
        const linkText = (a.innerText?.trim() || '').toLowerCase();
        return searchTerms.some((term) => linkText === term || linkText.includes(term));
    });

    if (!actionLink) {
        const available = actionLinks
            .map((a) => a.innerText?.trim())
            .filter(Boolean)
            .slice(0, 15);
        return {
            error: 'Action link not found: ' + actionText,
            available: available,
            searchedFor: searchTerms,
        };
    }

    actionLink.click();
    return { clicked: true, href: actionLink.href, clickedText: actionLink.innerText?.trim() };
}

/**
 * Clear the repository filter input.
 * @returns {Object} Result with cleared, wasEmpty, method, error fields
 */
function clearFilter() {
    let iframeDoc;
    try {
        iframeDoc = getAbapGitDoc();
    } catch (e) {
        return { error: e.message };
    }

    const filterInput =
        iframeDoc.querySelector('input#filter') || iframeDoc.querySelector('input[name="filter"]');

    if (!filterInput) {
        return { cleared: false, error: 'No filter input found' };
    }

    // Check if filter has a value
    if (!filterInput.value) {
        return { cleared: true, wasEmpty: true };
    }

    // Clear the filter
    filterInput.value = '';
    filterInput.dispatchEvent(new Event('input', { bubbles: true }));

    // Submit the form to apply the cleared filter
    const form = filterInput.closest('form');
    if (form) {
        const submitBtn = form.querySelector('input[type="submit"], button[type="submit"]');
        if (submitBtn) {
            submitBtn.click();
            return { cleared: true, method: 'submit_button' };
        }
    }

    return { cleared: true, method: 'input_cleared' };
}

/**
 * Find a token/password input field in a document.
 * Checks for:
 * 1. input[type="password"]
 * 2. Text inputs with labels containing "password" or "token"
 * @param {Document} doc - Document to search in
 * @returns {Element|null} The input element or null
 */
function findTokenInput(doc) {
    if (!doc) return null;

    // First try password type inputs
    const passwordInput = doc.querySelector('input[type="password"]');
    if (passwordInput && isVisible(passwordInput)) {
        return passwordInput;
    }

    // Look for text inputs with token/password labels
    const allInputs = Array.from(doc.querySelectorAll('input[type="text"], input:not([type])'));
    for (const input of allInputs) {
        if (!isVisible(input)) continue;

        // Check preceding label or sibling text
        const label = input.labels?.[0]?.innerText?.toLowerCase() || '';
        const prevText = input.previousElementSibling?.innerText?.toLowerCase() || '';
        const placeholder = (input.placeholder || '').toLowerCase();
        const name = (input.name || '').toLowerCase();
        const id = (input.id || '').toLowerCase();

        if (
            label.includes('token') ||
            label.includes('password') ||
            prevText.includes('token') ||
            prevText.includes('password') ||
            placeholder.includes('token') ||
            placeholder.includes('password') ||
            name.includes('token') ||
            name.includes('password') ||
            name.includes('pass') ||
            id.includes('token') ||
            id.includes('password') ||
            id.includes('pass')
        ) {
            return input;
        }
    }

    return null;
}

/**
 * Check if a login dialog is present.
 * A login dialog is detected when there is a visible token/password input field.
 * @returns {Object} Result with hasLoginDialog, tokenInputId, location fields
 */
function checkLoginDialog() {
    // First check in main document (SAP dialog layer)
    const mainInput = findTokenInput(document);
    if (mainInput) {
        return {
            hasLoginDialog: true,
            tokenInputId: mainInput.id || null,
            tokenInputName: mainInput.name || null,
            tokenInputType: mainInput.type || 'text',
            location: 'main_document',
        };
    }

    // Check for SAP dialog with login text
    const dialogCheck = document.querySelector('[role="dialog"]');
    if (dialogCheck) {
        // Create a temporary document fragment to search within dialog
        const dialogInput = findTokenInput({
            querySelector: (s) => dialogCheck.querySelector(s),
            querySelectorAll: (s) => dialogCheck.querySelectorAll(s),
        });
        if (dialogInput) {
            return {
                hasLoginDialog: true,
                tokenInputId: dialogInput.id || null,
                tokenInputName: dialogInput.name || null,
                tokenInputType: dialogInput.type || 'text',
                location: 'sap_dialog',
            };
        }
    }

    // Check inside iframes
    const iframeCandidates = [
        document.querySelector('iframe#C116'),
        document.querySelector('iframe[id^="C"]'),
        document.querySelector('iframe'),
    ].filter(Boolean);

    for (const candidate of iframeCandidates) {
        try {
            const doc = candidate.contentDocument || candidate.contentWindow?.document;
            const iframeInput = findTokenInput(doc);
            if (iframeInput) {
                return {
                    hasLoginDialog: true,
                    tokenInputId: iframeInput.id || null,
                    tokenInputName: iframeInput.name || null,
                    tokenInputType: iframeInput.type || 'text',
                    location: 'iframe',
                };
            }
        } catch (e) {
            /* ignore cross-origin errors */
        }
    }

    // No token/password field found - no login dialog
    return {
        hasLoginDialog: false,
        tokenInputId: null,
        tokenInputName: null,
    };
}

/**
 * Check if an element is visible on screen.
 * @param {Element} el - Element to check
 * @returns {boolean} True if element is visible
 */
function isVisible(el) {
    if (!el) return false;
    // Handle mock document objects from findTokenInput
    if (typeof window === 'undefined') return true;
    try {
        const style = window.getComputedStyle(el);
        return (
            style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            style.opacity !== '0' &&
            el.offsetParent !== null
        );
    } catch (e) {
        return true; // Assume visible if we can't check
    }
}

/**
 * Set input value using native setter to bypass framework interception.
 * This is more reliable than just setting .value directly.
 * @param {HTMLInputElement} input - The input element
 * @param {string} value - The value to set
 */
function setInputValueNative(input, value) {
    // Focus the input first (like a real user would)
    input.focus();

    // Try to use the native setter to bypass any framework wrappers
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value'
    )?.set;

    if (nativeInputValueSetter) {
        nativeInputValueSetter.call(input, value);
    } else {
        // Fallback to direct assignment
        input.value = value;
    }

    // Dispatch events to notify any listeners
    // Use InputEvent for better compatibility
    input.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
    input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));

    // Keep focus on the input
    input.focus();
}

/**
 * Fill the token/password field securely.
 * Token is passed as argument, not embedded in JS string.
 * @param {string} token - The PAT token to fill
 * @returns {Object} Result with filled, method, error fields
 */
function fillToken(token) {
    // First try main document
    const mainInput = findTokenInput(document);
    if (mainInput) {
        setInputValueNative(mainInput, token);
        // Verify the value was set
        const valueSet = mainInput.value === token;
        return {
            filled: true,
            valueVerified: valueSet,
            method: 'main_document',
            inputType: mainInput.type,
            inputId: mainInput.id,
        };
    }

    // Check SAP dialog
    const dialogCheck = document.querySelector('[role="dialog"]');
    if (dialogCheck) {
        const dialogInput = findTokenInput({
            querySelector: (s) => dialogCheck.querySelector(s),
            querySelectorAll: (s) => dialogCheck.querySelectorAll(s),
        });
        if (dialogInput) {
            setInputValueNative(dialogInput, token);
            const valueSet = dialogInput.value === token;
            return {
                filled: true,
                valueVerified: valueSet,
                method: 'sap_dialog',
                inputType: dialogInput.type,
                inputId: dialogInput.id,
            };
        }
    }

    // Try looking in iframes
    const iframeCandidates = [
        document.querySelector('iframe#C116'),
        document.querySelector('iframe[id^="C"]'),
        document.querySelector('iframe'),
    ].filter(Boolean);

    for (const iframe of iframeCandidates) {
        try {
            const doc = iframe.contentDocument || iframe.contentWindow?.document;
            const iframeInput = findTokenInput(doc);
            if (iframeInput) {
                setInputValueNative(iframeInput, token);
                const valueSet = iframeInput.value === token;
                return {
                    filled: true,
                    valueVerified: valueSet,
                    method: 'iframe',
                    inputType: iframeInput.type,
                    inputId: iframeInput.id,
                };
            }
        } catch (e) {
            /* ignore */
        }
    }

    return { filled: false, error: 'Token/password field not found' };
}

/**
 * Click the Continue/Weiter button in a login dialog.
 * Searches for buttons with text like "Weiter", "Continue", "OK", "Submit".
 * @returns {Object} Result with clicked, buttonText, error fields
 */
function clickContinueButton() {
    // Button text variants (German and English)
    const buttonTexts = ['weiter', 'continue', 'ok', 'submit', 'anmelden', 'login'];

    // First check main document for buttons
    const allButtons = Array.from(
        document.querySelectorAll('button, input[type="submit"], input[type="button"], a.button, [role="button"]')
    );

    for (const btn of allButtons) {
        const text = (btn.innerText || btn.value || '').toLowerCase().trim();
        if (buttonTexts.some((t) => text.includes(t)) && isVisible(btn)) {
            btn.click();
            return { clicked: true, buttonText: btn.innerText || btn.value, location: 'main_document' };
        }
    }

    // Check SAP dialog
    const dialogCheck = document.querySelector('[role="dialog"]');
    if (dialogCheck) {
        const dialogButtons = Array.from(
            dialogCheck.querySelectorAll(
                'button, input[type="submit"], input[type="button"], a.button, [role="button"]'
            )
        );
        for (const btn of dialogButtons) {
            const text = (btn.innerText || btn.value || '').toLowerCase().trim();
            if (buttonTexts.some((t) => text.includes(t)) && isVisible(btn)) {
                btn.click();
                return { clicked: true, buttonText: btn.innerText || btn.value, location: 'sap_dialog' };
            }
        }
    }

    // Check inside iframes
    const iframeCandidates = [
        document.querySelector('iframe#C116'),
        document.querySelector('iframe[id^="C"]'),
        document.querySelector('iframe'),
    ].filter(Boolean);

    for (const iframe of iframeCandidates) {
        try {
            const doc = iframe.contentDocument || iframe.contentWindow?.document;
            if (!doc) continue;

            const iframeButtons = Array.from(
                doc.querySelectorAll(
                    'button, input[type="submit"], input[type="button"], a.button, [role="button"]'
                )
            );
            for (const btn of iframeButtons) {
                const text = (btn.innerText || btn.value || '').toLowerCase().trim();
                if (buttonTexts.some((t) => text.includes(t))) {
                    btn.click();
                    return { clicked: true, buttonText: btn.innerText || btn.value, location: 'iframe' };
                }
            }
        } catch (e) {
            /* ignore cross-origin errors */
        }
    }

    // List available buttons for debugging
    const available = allButtons
        .filter((b) => isVisible(b))
        .map((b) => b.innerText || b.value || b.className)
        .filter(Boolean)
        .slice(0, 10);

    return { clicked: false, error: 'Continue button not found', available: available };
}

/**
 * Check for error messages or success indicators after an action.
 * Only reports errors for clear, unambiguous error states.
 * @returns {Object} Result with hasError, hasSuccess, message fields
 */
function checkActionResult() {
    let iframeDoc;
    try {
        iframeDoc = getAbapGitDoc();
    } catch (e) {
        // If we can't find the iframe, assume success (page may have navigated)
        return { hasError: false, hasSuccess: true, message: null };
    }

    const bodyText = iframeDoc.body?.innerText || '';

    // Only check for CLEAR error indicators - be conservative
    // These are specific error messages, not just words that might appear in normal context
    const clearErrorPatterns = [
        /syntax\s+error/i,
        /activation\s+failed/i,
        /pull\s+failed/i,
        /exception\s+occurred/i,
        /abap\s+runtime\s+error/i,
        /short\s+dump/i,
    ];

    const hasError = clearErrorPatterns.some((p) => p.test(bodyText));

    // Check for success indicators
    const successPatterns = [
        /pull.*success/i,
        /objects\s+imported/i,
        /no\s+changes/i,
        /already\s+up\s+to\s+date/i,
        /nothing\s+to\s+pull/i,
    ];

    const hasSuccess = successPatterns.some((p) => p.test(bodyText));

    // Extract relevant message from page - look for specific message containers
    const messageElement = iframeDoc.querySelector('.message, .alert-danger, .error-message');
    const message = messageElement?.innerText?.trim() || null;

    return {
        hasError: hasError,
        hasSuccess: hasSuccess || !hasError, // Default to success if no clear error
        message: message,
        bodyPreview: bodyText.substring(0, 1000),
    };
}

// Export for use
if (typeof module !== 'undefined') {
    module.exports = {
        findAbapGitIframe,
        getAbapGitDoc,
        findMenuArrow,
        findRepoRow,
        clickMenuArrow,
        clickAction,
        clearFilter,
        checkLoginDialog,
        fillToken,
        clickContinueButton,
        checkActionResult,
    };
}
