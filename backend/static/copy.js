/* Shared clipboard feedback for copy buttons and live regions. */
(() => {
  "use strict";

  function showCopied(button, duration) {
    if (!button) return;
    if (!button.dataset.copyLabel) button.dataset.copyLabel = button.textContent.trim();
    clearTimeout(button._copyTimer);
    button.textContent = "Copied";
    button.classList.add("is-copied");
    button._copyTimer = setTimeout(() => {
      button.textContent = button.dataset.copyLabel;
      button.classList.remove("is-copied");
    }, duration);
  }

  function announce(status, message) {
    if (!status || !message) return;
    clearTimeout(status._copyAnnounceTimer);
    status.textContent = "";
    status._copyAnnounceTimer = setTimeout(() => {
      status.textContent = message;
    }, 80);
  }

  function legacyCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    area.setAttribute("readonly", "");
    document.body.appendChild(area);
    area.focus();
    area.select();
    area.setSelectionRange(0, text.length);
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    area.remove();
    return copied;
  }

  async function write(text, options = {}) {
    const { button = null, status = null, message = "", duration = 1800 } = options;
    let copied = false;

    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch (error) {
      copied = legacyCopy(text);
    }

    if (!copied) return false;

    showCopied(button, duration);
    announce(status, message);
    return true;
  }

  window.StudyCopy = { write };
})();
