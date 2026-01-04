() => {
  // Fast check for blocking popup layer
  const blockingLayer = document.querySelector(
    "#urPopupWindowBlockLayer, .lsBlockLayer"
  );

  if (!blockingLayer) {
    return null; // No popup blocking
  }

  // Find popup container
  const popup = document.querySelector(
    ".urPopupWindow, .lsPopup, [class*='urMessageBox']"
  );

  // Extract message text
  let message = null;
  const messageSelectors = [
    ".urMessageText",
    ".lsPopupText",
    ".urMsgBoxText",
    "[class*='MessageText']",
    ".sapMText",
  ];
  for (const sel of messageSelectors) {
    const el = popup?.querySelector(sel) || document.querySelector(sel);
    if (el?.textContent?.trim()) {
      message = el.textContent.trim();
      break;
    }
  }

  // Extract buttons
  const buttons = [];
  const buttonSelectors = [
    ".urPopupWindow button",
    ".lsPopup button",
    "[class*='urMessageBox'] button",
    ".urBtnStd",
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
        accesskey: btn.getAttribute("accesskey") || null,
        id: btn.id || null,
      });
    }
  }

  // Find close button (X in corner)
  let closeButtonId = null;
  const closeSelectors = [
    "[class*='urPopup'] [class*='close']",
    "[class*='urPopup'] [title*='Close']",
    "[class*='urPopup'] [title*='Schließen']",
    ".urPopupClose",
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
