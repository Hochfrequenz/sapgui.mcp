() => {
    // Extracts the SAP username from the page DOM after login.
    // Returns { user: "USER01" } or { user: null } if not found.
    const el = document.getElementById('sysInfoAreaMenuItemSAPITS_MBAR_USER');
    if (!el) return { user: null };

    // Strategy 1: lsdata JSON — key "13" is the username in SAP's lsdata encoding
    const lsdata = el.getAttribute('lsdata');
    if (lsdata) {
        try {
            const data = JSON.parse(lsdata);
            if (data['13']) return { user: String(data['13']) };
        } catch (e) {
            /* fall through */
        }
    }

    // Strategy 2: aria-label last word
    const label = el.getAttribute('aria-label');
    if (label) {
        const parts = label.trim().split(/\s+/);
        if (parts.length >= 2) return { user: parts[parts.length - 1] };
    }

    return { user: null };
};
