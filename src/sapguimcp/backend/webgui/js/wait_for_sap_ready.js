() => {
    // SAP WebGUI toolbar buttons with class "lsButton" and role="button"
    // are rendered after client-side JS initialization completes.
    // Their presence indicates the screen is interactive.
    const buttons = document.querySelectorAll('.lsButton[role="button"]');
    for (const btn of buttons) {
        const style = window.getComputedStyle(btn);
        if (
            style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            btn.offsetWidth > 0 &&
            btn.offsetHeight > 0
        ) {
            return true;
        }
    }
    return false;
};
