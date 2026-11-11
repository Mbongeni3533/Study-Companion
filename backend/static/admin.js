(() => {
  "use strict";

  const KEY_STORAGE = "study-companion.admin-key";
  const $ = (selector) => document.querySelector(selector);

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

  const fmtDate = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  };

  function showError(message) {
    const node = $("#admin-error");
    if (!message) {
      node.hidden = true;
      node.textContent = "";
      return;
    }
    node.hidden = false;
    node.textContent = message;
  }

  function render(rows) {
    const count = $("#admin-count");
    if (!rows.length) {
      count.textContent = "No feedback yet.";
      $("#admin-table").innerHTML = '<div class="admin-empty">No feedback has been submitted yet.</div>';
      return;
    }
    count.textContent = `${rows.length} feedback ${rows.length === 1 ? "entry" : "entries"}, newest first.`;
    $("#admin-table").innerHTML = `
      <table class="admin-table">
        <thead>
          <tr>
            <th>User</th>
            <th>Rating</th>
            <th>Category</th>
            <th>Page</th>
            <th>Date</th>
            <th>Feedback</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((row) => {
              const name = row.user_name || "Guest";
              const email = row.user_email || (row.user_id ? "No email on file" : "Anonymous session");
              return `
                <tr>
                  <td><span class="admin-user"><strong>${esc(name)}</strong><span>${esc(email)}</span></span></td>
                  <td>${row.rating ? `${esc(row.rating)} / 5` : "—"}</td>
                  <td><span class="chip">${esc(row.category || "general")}</span></td>
                  <td><span class="admin-page">${esc(row.page || "—")}</span></td>
                  <td><span class="admin-date">${esc(fmtDate(row.created_at))}</span></td>
                  <td><div class="admin-message">${esc(row.message || "")}</div></td>
                </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;
  }

  async function loadFeedback() {
    const input = $("#admin-key");
    const key = input.value.trim();
    if (!key) {
      showError("Enter the admin key.");
      input.focus();
      return;
    }
    sessionStorage.setItem(KEY_STORAGE, key);
    showError("");
    const button = $("#admin-load");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Loading...";
    try {
      const response = await fetch("/feedback?limit=200", {
        headers: { "X-Admin-Key": key },
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error((data && data.detail) || `Request failed (${response.status})`);
      }
      render(Array.isArray(data) ? data : []);
    } catch (error) {
      showError(error.message || "Could not load feedback.");
      $("#admin-count").textContent = "Feedback could not be loaded.";
      $("#admin-table").innerHTML = '<div class="admin-empty">Check the admin key and try again.</div>';
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  $("#admin-key-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadFeedback();
  });

  $("#admin-refresh").addEventListener("click", loadFeedback);

  $("#admin-clear").addEventListener("click", () => {
    sessionStorage.removeItem(KEY_STORAGE);
    $("#admin-key").value = "";
    $("#admin-key").focus();
    showError("");
    $("#admin-count").textContent = "Enter the admin key to load feedback.";
    $("#admin-table").innerHTML = '<div class="admin-empty">No feedback loaded yet.</div>';
  });

  const saved = sessionStorage.getItem(KEY_STORAGE);
  if (saved) {
    $("#admin-key").value = saved;
    loadFeedback();
  }
})();
