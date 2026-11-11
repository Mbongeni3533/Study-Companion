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

  const inviteLink = (code) => `${window.location.origin}/?invite=${encodeURIComponent(code)}`;

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch { ok = false; }
      area.remove();
      return ok;
    }
  }

  function showInviteError(message) {
    const node = $("#invite-error");
    node.hidden = !message;
    node.textContent = message || "";
  }

  function showInviteStatus(message, ok = true) {
    const node = $("#invite-status");
    node.textContent = message || "";
    node.classList.toggle("admin-status-ok", Boolean(message) && ok);
  }

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

  function renderInvites(codes) {
    const host = $("#admin-invites");
    if (!codes.length) {
      host.innerHTML = '<div class="admin-empty">No invitation links yet. Create one above.</div>';
      return;
    }
    host.innerHTML = `
      <table class="admin-table">
        <thead>
          <tr><th>Student</th><th>Code</th><th>Uses</th><th>Status</th><th>Invite link</th><th>Actions</th></tr>
        </thead>
        <tbody>
          ${codes
            .map((row) => {
              const expired = row.expires_at && new Date(row.expires_at).getTime() < Date.now();
              const used = Number(row.uses) >= Number(row.max_uses);
              const status = row.revoked ? "Revoked" : expired ? "Expired" : used ? "Used up" : "Active";
              const link = inviteLink(row.code);
              const mailto = row.email
                ? `mailto:${encodeURIComponent(row.email)}?subject=${encodeURIComponent("Your Study Companion beta invite")}&body=${encodeURIComponent(`You're invited to the Study Companion beta.\n\nCreate your account here: ${link}\n\nYour invite code is ${row.code}.`)}`
                : "";
              return `
                <tr>
                  <td>${esc(row.email || "Shared link")}</td>
                  <td><span class="admin-page">${esc(row.code)}</span></td>
                  <td>${esc(row.uses)} / ${esc(row.max_uses)}</td>
                  <td><span class="chip ${status === "Active" ? "chip-emerald" : ""}">${esc(status)}</span></td>
                  <td><a class="admin-link" href="${esc(link)}" target="_blank" rel="noopener">${esc(link)}</a></td>
                  <td><div class="admin-actions">
                    <button class="btn btn-ghost btn-sm" type="button" data-copy="${esc(link)}">Copy link</button>
                    ${mailto ? `<a class="btn btn-ghost btn-sm" href="${esc(mailto)}">Email</a>` : ""}
                  </div></td>
                </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;
    host.querySelectorAll("[data-copy]").forEach((button) => {
      button.addEventListener("click", async () => {
        const ok = await copyText(button.dataset.copy);
        showInviteStatus(ok ? "Invite link copied." : "Could not copy. Select the link manually.", ok);
      });
    });
  }

  async function loadInvites() {
    const key = $("#admin-key").value.trim();
    if (!key) {
      showInviteError("Enter the admin key.");
      return;
    }
    showInviteError("");
    try {
      const response = await fetch("/admin/invite-codes", {
        headers: { "X-Admin-Key": key },
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error((data && data.detail) || `Request failed (${response.status})`);
      renderInvites(Array.isArray(data) ? data : []);
    } catch (error) {
      showInviteError(error.message || "Could not load invitation links.");
      $("#admin-invites").innerHTML = '<div class="admin-empty">Check the admin key and try again.</div>';
    }
  }

  async function createInvite(event) {
    event.preventDefault();
    const key = $("#admin-key").value.trim();
    if (!key) {
      showInviteError("Enter the admin key.");
      $("#admin-key").focus();
      return;
    }
    const email = $("#invite-email").value.trim();
    const maxUses = Number($("#invite-uses").value) || 1;
    const button = $("#invite-create");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Creating...";
    showInviteError("");
    showInviteStatus("");
    try {
      const response = await fetch("/admin/invite-codes", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Key": key },
        body: JSON.stringify({ email: email || null, max_uses: maxUses, send_email: false }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error((data && data.detail) || `Request failed (${response.status})`);
      $("#invite-email").value = "";
      showInviteStatus(`Invite link created${email ? ` for ${email}` : ""}. Copy it below.`);
      await loadInvites();
    } catch (error) {
      showInviteError(error.message || "Could not create the invite link.");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
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
    loadInvites();
  });

  $("#admin-refresh").addEventListener("click", loadFeedback);
  $("#invite-refresh").addEventListener("click", loadInvites);
  $("#invite-form").addEventListener("submit", createInvite);

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
    loadInvites();
  }
})();
