(() => {
  "use strict";

  const SESSION_PATH = "/admin/session";
  const $ = (selector) => document.querySelector(selector);

  // Remove the admin key left by older builds; sessions now use HttpOnly cookies.
  try {
    sessionStorage.removeItem("study-companion.admin-key");
  } catch {
    // Storage can be unavailable in privacy-restricted browsers.
  }

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

  const fmtDate = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  };

  const inviteLink = (code) => `${window.location.origin}/?invite=${encodeURIComponent(code)}`;

  const HEALTH_METRIC_LABELS = {
    users_total: "Users",
    users_anonymous: "Anonymous users",
    courses_total: "Courses",
    documents_total: "Documents",
    documents_ready: "Ready documents",
    documents_failed: "Failed documents",
    documents_processing: "Processing documents",
    topics_total: "Topics",
    chunks_total: "Text chunks",
    feedback_total: "Feedback",
    feedback_unresolved: "Unresolved feedback",
    invite_codes_total: "Invite codes",
    invite_codes_active: "Active invites",
    invite_codes_exhausted: "Exhausted invites",
    study_minutes_total: "Study minutes",
    stale_processing_minutes: "Stale processing limit (min)",
    ai_enabled: "AI provider",
    beta_invite_only: "Invite-only beta",
    allow_anonymous_sessions: "Guest sessions",
    database: "Database",
    environment: "Environment",
  };

  function healthMetricLabel(key) {
    return HEALTH_METRIC_LABELS[key] || key.replace(/_/g, " ").replace(/^./, (char) => char.toUpperCase());
  }

  function healthMetricValue(key, value) {
    if (typeof value === "boolean") {
      if (key === "ai_enabled") return value ? "Enabled" : "Rules only";
      return value ? "Yes" : "No";
    }
    if (key === "database") return value === "postgres" ? "PostgreSQL" : "SQLite";
    if (typeof value === "number") return value.toLocaleString();
    return String(value ?? "—");
  }

  function showHealthStatus(message, ok = true) {
    const node = $("#health-status");
    if (!node) return;
    node.textContent = message || "";
    node.classList.toggle("admin-status-ok", Boolean(message) && ok);
    node.classList.toggle("admin-status-error", Boolean(message) && !ok);
  }

  function renderHealthAlerts(alerts) {
    const host = $("#health-alerts");
    if (!alerts.length) {
      host.hidden = true;
      host.innerHTML = "";
      $("#health-bulk-actions").hidden = true;
      return;
    }
    const failed = alerts.filter((alert) => alert.status === "failed").length;
    const stale = alerts.filter((alert) => alert.stale).length;
    const summary = [failed ? `${failed} failed` : "", stale ? `${stale} stuck` : ""].filter(Boolean).join(" · ");
    host.hidden = false;
    $("#health-bulk-actions").hidden = stale === 0;
    host.innerHTML = `
      <div class="health-alerts-head">
        <strong>Attention required</strong>
        <span>${esc(summary)}</span>
      </div>
      <div class="health-alert-list">${alerts
        .map((alert) => {
          const isStale = alert.stale || alert.action === "run_remediation";
          const meta = [alert.course_title, alert.age_minutes != null ? `No progress for ${alert.age_minutes} min` : ""]
            .filter(Boolean)
            .join(" · ");
          const detail = isStale
            ? "This document has not progressed within the stale-processing limit. Preview the fix before applying it."
            : alert.error || "This document failed processing and needs manual review.";
          return `
            <article class="health-alert ${isStale ? "health-alert--stale" : ""}">
              <span class="health-alert-status">${isStale ? "Stuck" : "Failed"}</span>
              <div class="health-alert-body">
                <strong>${esc(alert.filename || "Untitled document")}</strong>
                ${meta ? `<span class="health-alert-meta">${esc(meta)}</span>` : ""}
                <p>${esc(detail)}</p>
                ${isStale ? `<div class="health-alert-actions">
                  <button class="btn btn-ghost btn-sm" type="button" data-health-action="preview" data-document-id="${esc(alert.document_id)}" data-document-name="${esc(alert.filename || "document")}">Preview this fix</button>
                  <button class="btn btn-ghost btn-sm admin-danger" type="button" data-health-action="apply" data-document-id="${esc(alert.document_id)}" data-document-name="${esc(alert.filename || "document")}">Mark this failed</button>
                </div>` : `<div class="health-alert-actions">
                  <button class="btn btn-ghost btn-sm" type="button" data-health-action="retry" data-document-id="${esc(alert.document_id)}" data-document-name="${esc(alert.filename || "document")}">Retry processing</button>
                  <span class="health-alert-note">Or leave for manual review</span>
                </div>`}
              </div>
            </article>`;
        })
        .join("")}</div>`;
  }

  function renderSystemHealth(data) {
    const metrics = data.metrics || {};
    $("#health-summary").textContent = `Generated ${fmtDate(data.generated_at)} · ${data.ai_used ? "AI-assisted plan" : "Rule-based plan"}`;
    renderHealthAlerts(Array.isArray(data.alerts) ? data.alerts : []);

    const order = Object.keys(HEALTH_METRIC_LABELS);
    const entries = Object.entries(metrics).sort(([a], [b]) => {
      const ai = order.indexOf(a);
      const bi = order.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi) || a.localeCompare(b);
    });
    $("#health-metrics").innerHTML = entries.length
      ? entries
          .map(
            ([key, value]) => `
              <div class="health-metric">
                <strong>${esc(healthMetricValue(key, value))}</strong>
                <span>${esc(healthMetricLabel(key))}</span>
              </div>`
          )
          .join("")
      : '<div class="admin-empty">No metrics were returned.</div>';

    const findings = Array.isArray(data.findings) ? data.findings : [];
    $("#health-findings").innerHTML = findings.length
      ? findings
          .map((finding) => {
            const severity = ["error", "warning", "info"].includes(finding.severity) ? finding.severity : "info";
            return `
              <article class="health-finding health-finding--${severity}">
                <span class="health-severity">${esc(severity)}</span>
                <div class="health-finding-body">
                  <strong>${esc(finding.area || "system")}</strong>
                  <p>${esc(finding.message || "")}</p>
                  ${finding.suggested_action ? `<span class="health-action">Action: ${esc(finding.suggested_action)}</span>` : ""}
                </div>
              </article>`;
          })
          .join("")
      : '<div class="admin-empty">No findings. The system looks healthy.</div>';
  }

  async function loadSystemHealth() {
    const button = $("#health-refresh");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Running...";
    showHealthStatus("Running diagnostics…");
    try {
      const response = await fetch("/admin/agents/sysadmin/diagnostics", {
        credentials: "same-origin",
      });
      if (response.status === 403) {
        showLogin("Admin session expired. Enter the admin key again.");
        return;
      }
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error((data && data.detail) || `Request failed (${response.status})`);
      renderSystemHealth(data || {});
      const count = Array.isArray(data && data.findings) ? data.findings.length : 0;
      showHealthStatus(`Diagnostics complete: ${count} finding${count === 1 ? "" : "s"}.`);
    } catch (error) {
      $("#health-metrics").innerHTML = '<div class="admin-empty">System metrics could not be loaded.</div>';
      $("#health-alerts").hidden = true;
      $("#health-alerts").innerHTML = "";
      $("#health-bulk-actions").hidden = true;
      $("#health-findings").innerHTML = "";
      showHealthStatus(error.message || "Could not run diagnostics.", false);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function renderRemediation(data) {
    const host = $("#health-remediation");
    const actions = Array.isArray(data.actions) ? data.actions : [];
    const remaining = Array.isArray(data.remaining_issues) ? data.remaining_issues : [];
    const changes = Array.isArray(data.changes) ? data.changes : [];
    host.hidden = false;
    host.innerHTML = `
      <div class="health-remediation-head">
        <h3>Remediation scan</h3>
        <span>${data.document_id ? "Single document" : "All stale documents"} · ${data.dry_run ? "Dry run" : "Changes applied"} · ${esc(fmtDate(data.generated_at))}</span>
      </div>
      ${actions.length ? `<ul>${actions
        .map(
          (action) => `<li><strong>${esc(action.action || "check")}</strong><span>${esc(action.affected ?? 0)} affected</span>${action.detail ? `<span>${esc(action.detail)}</span>` : ""}</li>`
        )
        .join("")}</ul>` : '<div class="admin-empty">No checks were returned.</div>'}
      ${remaining.length ? `<p class="health-remaining">Needs manual review: ${remaining.map((item) => esc(item)).join(" ")}</p>` : ""}
      ${changes.length ? `<div class="health-changes">
        <h4>Recorded changes</h4>
        <ul>${changes
          .map(
            (change) => `<li><strong>${esc(change.document_filename || change.document_id || "document")}</strong><span>${esc(change.detail || change.action)}</span><time>${esc(fmtDate(change.created_at))}</time></li>`
          )
          .join("")}</ul>
      </div>` : ""}`;
  }

  async function retryDocument({ documentId, documentName, button }) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Retrying...";
    showHealthStatus(`Queueing a retry for ${documentName}…`);
    try {
      const response = await fetch(`/admin/agents/sysadmin/documents/${encodeURIComponent(documentId)}/retry`, {
        method: "POST",
        credentials: "same-origin",
      });
      if (response.status === 403) {
        showLogin("Admin session expired. Enter the admin key again.");
        return;
      }
      const data = await response.json().catch(() => null);
      if (response.status === 404 || response.status === 409) {
        await loadSystemHealth();
      }
      if (!response.ok) throw new Error((data && data.detail) || `Request failed (${response.status})`);
      await loadSystemHealth();
      showHealthStatus((data && data.message) || `Retry queued for ${documentName}.`);
    } catch (error) {
      showHealthStatus(error.message || "Could not retry this document.", false);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function runRemediationScan({ dryRun = true, documentId = null, button = null } = {}) {
    const actionButton = button || $("#health-bulk-preview");
    const original = actionButton.textContent;
    const params = new URLSearchParams({ dry_run: dryRun ? "true" : "false" });
    if (documentId) params.set("document_id", documentId);
    actionButton.disabled = true;
    actionButton.textContent = dryRun ? "Checking..." : "Applying...";
    showHealthStatus(
      dryRun
        ? `Running remediation dry run${documentId ? " for this document" : " for all stale documents"}…`
        : `Applying remediation${documentId ? " to this document" : " to all stale documents"}…`
    );
    try {
      const response = await fetch(`/admin/agents/sysadmin/remediate?${params.toString()}`, {
        method: "POST",
        credentials: "same-origin",
      });
      if (response.status === 403) {
        showLogin("Admin session expired. Enter the admin key again.");
        return;
      }
      const data = await response.json().catch(() => null);
      if (response.status === 404 || response.status === 409) {
        await loadSystemHealth();
      }
      if (!response.ok) throw new Error((data && data.detail) || `Request failed (${response.status})`);
      renderRemediation(data || {});
      const changed = Array.isArray(data && data.changes) ? data.changes.length : 0;
      if (data && !data.dry_run && changed) await loadSystemHealth();
      showHealthStatus(
        data && data.dry_run
          ? "Dry run complete. No documents were changed."
          : `Remediation complete. ${changed} document${changed === 1 ? "" : "s"} marked failed.`
      );
    } catch (error) {
      showHealthStatus(error.message || "Could not run the remediation scan.", false);
    } finally {
      actionButton.disabled = false;
      actionButton.textContent = original;
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

  const SUBSCRIBER_STATUSES = ["pending", "subscribed", "suspended"];
  const SUBSCRIBER_LABELS = {
    pending: "Pending",
    subscribed: "Subscribed",
    suspended: "Suspended",
  };

  function subscriberLabel(status) {
    return SUBSCRIBER_LABELS[status] || "Pending";
  }

  function showSubscriberStatus(message, ok = true) {
    const node = $("#subscriber-status");
    if (!node) return;
    node.textContent = message || "";
    node.classList.toggle("admin-status-ok", Boolean(message) && ok);
    node.classList.toggle("admin-status-error", Boolean(message) && !ok);
  }

  function renderSubscribers(data) {
    const rows = Array.isArray(data.subscribers) ? data.subscribers : [];
    const summary = data.summary || {};
    const total = Number(summary.total || rows.length);
    $("#subscriber-count").textContent = `${total} subscriber${total === 1 ? "" : "s"} · ${summary.subscribed || 0} subscribed · ${summary.pending || 0} pending · ${summary.suspended || 0} suspended${data.feed_enabled ? " · Google Sheet feed active" : ""}`;

    const stats = $("#subscriber-stats");
    stats.innerHTML = `
      <div><strong>${esc(total)}</strong><span>Total</span></div>
      <div><strong>${esc(summary.subscribed || 0)}</strong><span>Subscribed</span></div>
      <div><strong>${esc(summary.pending || 0)}</strong><span>Pending</span></div>
      <div><strong>${esc(summary.suspended || 0)}</strong><span>Suspended</span></div>`;
    stats.hidden = false;

    const sheet = $("#subscriber-sheet");
    if (data.sheet_url) {
      sheet.href = data.sheet_url;
      sheet.hidden = false;
    } else {
      sheet.hidden = true;
    }

    const host = $("#admin-subscribers");
    if (!rows.length) {
      host.innerHTML = '<div class="admin-empty">No registered subscribers yet.</div>';
    } else {
      host.innerHTML = `
        <table class="admin-table">
          <thead>
            <tr><th>Subscriber</th><th>Subscription</th><th>Plan</th><th>Joined</th><th>Last active</th><th>Actions</th></tr>
          </thead>
          <tbody>
            ${rows
              .map((row) => {
                const status = SUBSCRIBER_STATUSES.includes(row.subscription_status) ? row.subscription_status : "pending";
                const name = row.name || "Student";
                return `
                  <tr>
                    <td><span class="admin-user"><strong>${esc(name)}</strong><span>${esc(row.email || "No email on file")}</span></span></td>
                    <td>
                      <select class="subscriber-status subscriber-status--${esc(status)}" data-subscriber-status="${esc(row.id)}"
                        data-current="${esc(status)}" data-name="${esc(name)}" aria-label="Subscription status for ${esc(name)}">
                        ${SUBSCRIBER_STATUSES.map(
                          (value) => `<option value="${value}" ${value === status ? "selected" : ""}>${subscriberLabel(value)}</option>`
                        ).join("")}
                      </select>
                    </td>
                    <td>${esc(row.subscription_tier || "free")}</td>
                    <td><span class="admin-date">${esc(fmtDate(row.created_at))}</span></td>
                    <td><span class="admin-date">${esc(fmtDate(row.last_active_at))}</span></td>
                    <td><button class="btn btn-ghost btn-sm admin-danger" type="button" data-subscriber-delete="${esc(row.id)}"
                      data-name="${esc(name)}">Delete</button></td>
                  </tr>`;
              })
              .join("")}
          </tbody>
        </table>`;
    }

    host.querySelectorAll("[data-subscriber-status]").forEach((select) => {
      select.addEventListener("change", () => updateSubscriberStatus(select));
    });
    host.querySelectorAll("[data-subscriber-delete]").forEach((button) => {
      button.addEventListener("click", () => deleteSubscriber(button));
    });

    const events = Array.isArray(data.events) ? data.events : [];
    const activity = $("#subscriber-activity");
    activity.hidden = !events.length;
    $("#subscriber-events").innerHTML = events
      .map((event) => {
        const action = event.action === "status_changed" ? "Status changed" : event.action === "registered" ? "Registered" : event.action === "deleted" ? "Deleted" : event.action;
        return `<li><span class="subscriber-event-action">${esc(action)}</span><strong>${esc(event.name)}</strong>${event.email ? ` <span class="muted">${esc(event.email)}</span>` : ""}${event.status ? ` · ${esc(subscriberLabel(event.status))}` : ""}<time>${esc(fmtDate(event.created_at))}</time></li>`;
      })
      .join("");
  }

  async function loadSubscribers() {
    const host = $("#admin-subscribers");
    host.innerHTML = '<div class="admin-empty">Loading subscribers…</div>';
    try {
      const response = await fetch("/admin/subscribers", { credentials: "same-origin" });
      if (response.status === 403) {
        showLogin("Admin session expired. Enter the admin key again.");
        return;
      }
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error((data && data.detail) || `Request failed (${response.status})`);
      renderSubscribers(data || {});
    } catch (error) {
      host.innerHTML = '<div class="admin-empty">Subscribers could not be loaded. Check the admin key and try again.</div>';
      showSubscriberStatus(error.message || "Could not load subscribers.", false);
    }
  }

  async function updateSubscriberStatus(select) {
    const id = select.dataset.subscriberStatus;
    const name = select.dataset.name || "Subscriber";
    const next = select.value;
    const previous = select.dataset.current || next;
    select.disabled = true;
    showSubscriberStatus(`Saving ${name}'s subscription status…`);
    try {
      const response = await fetch(`/admin/subscribers/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ subscription_status: next }),
      });
      if (response.status === 403) {
        showLogin("Admin session expired. Enter the admin key again.");
        return;
      }
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error((data && data.detail) || `Request failed (${response.status})`);
      showSubscriberStatus(`${name} is now ${subscriberLabel(next).toLowerCase()}.`);
      await loadSubscribers();
    } catch (error) {
      select.value = previous;
      select.disabled = false;
      showSubscriberStatus(error.message || "Could not update the subscriber.", false);
    }
  }

  async function deleteSubscriber(button) {
    const id = button.dataset.subscriberDelete;
    const name = button.dataset.name || "this subscriber";
    if (!window.confirm(`Delete ${name}? This removes their account, courses, documents and study history.`)) return;
    button.disabled = true;
    button.textContent = "Deleting…";
    showSubscriberStatus(`Deleting ${name}…`);
    try {
      const response = await fetch(`/admin/subscribers/${encodeURIComponent(id)}`, {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (response.status === 403) {
        showLogin("Admin session expired. Enter the admin key again.");
        return;
      }
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error((data && data.detail) || `Request failed (${response.status})`);
      }
      showSubscriberStatus(`${name} was deleted.`);
      await loadSubscribers();
    } catch (error) {
      button.disabled = false;
      button.textContent = "Delete";
      showSubscriberStatus(error.message || "Could not delete the subscriber.", false);
    }
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
        const status = $("#invite-status");
        const copied = await window.StudyCopy.write(button.dataset.copy, {
          button,
          status,
          message: "Invite link copied.",
        });
        status.classList.toggle("admin-status-ok", copied);
        if (!copied) status.textContent = "Could not copy. Select the link manually.";
      });
    });
  }

  async function loadInvites() {
    showInviteError("");
    try {
      const response = await fetch("/admin/invite-codes", {
        credentials: "same-origin",
      });
      if (response.status === 403) {
        showLogin("Admin session expired. Enter the admin key again.");
        return;
      }
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
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ email: email || null, max_uses: maxUses, send_email: false }),
      });
      if (response.status === 403) {
        showLogin("Admin session expired. Enter the admin key again.");
        return;
      }
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
    const button = $("#admin-refresh");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Loading...";
    try {
      const response = await fetch("/feedback?limit=200", {
        credentials: "same-origin",
      });
      if (response.status === 403) {
        showLogin("Admin session expired. Enter the admin key again.");
        return;
      }
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

  async function openAdmin() {
    $("#admin-login").hidden = true;
    $("#admin-session").hidden = false;
    $("#admin-content").hidden = false;
    showError("");
    await Promise.all([loadSystemHealth(), loadSubscribers(), loadFeedback(), loadInvites()]);
  }

  function showLogin(message = "") {
    $("#admin-login").hidden = false;
    $("#admin-session").hidden = true;
    $("#admin-content").hidden = true;
    $("#admin-key").value = "";
    showError(message);
    $("#admin-key").focus();
  }

  async function signIn(event) {
    event.preventDefault();
    const input = $("#admin-key");
    const key = input.value.trim();
    if (!key) {
      showError("Enter the admin key.");
      input.focus();
      return;
    }
    const button = $("#admin-load");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Signing in...";
    showError("");
    try {
      const response = await fetch(SESSION_PATH, {
        method: "POST",
        headers: { "X-Admin-Key": key },
        credentials: "same-origin",
      });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error((data && data.detail) || "Invalid admin key.");
      }
      input.value = "";
      await openAdmin();
    } catch (error) {
      showError(error.message || "Could not sign in.");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function signOut() {
    try {
      await fetch(SESSION_PATH, { method: "DELETE", credentials: "same-origin" });
    } finally {
      showLogin();
    }
  }

  async function checkSession() {
    try {
      const response = await fetch(SESSION_PATH, { credentials: "same-origin" });
      if (response.ok) {
        await openAdmin();
      } else {
        showLogin();
      }
    } catch {
      showLogin();
    }
  }

  $("#admin-key-form").addEventListener("submit", signIn);
  $("#admin-refresh").addEventListener("click", loadFeedback);
  $("#health-refresh").addEventListener("click", loadSystemHealth);
  $("#health-bulk-preview").addEventListener("click", (event) => {
    runRemediationScan({ dryRun: true, button: event.currentTarget });
  });
  $("#health-bulk-apply").addEventListener("click", (event) => {
    if (!window.confirm("Mark ALL stale processing documents failed? This affects every stale document, not only one alert. Failed documents will remain available for manual review.")) return;
    runRemediationScan({ dryRun: false, button: event.currentTarget });
  });
  $("#health-alerts").addEventListener("click", (event) => {
    const button = event.target.closest("[data-health-action]");
    if (!button) return;
    const action = button.dataset.healthAction;
    const documentId = button.dataset.documentId;
    if (!documentId) return;
    if (action === "retry") {
      const name = button.dataset.documentName || "this document";
      if (!window.confirm(`Retry processing for "${name}"? The saved original file will be processed again and may take a few minutes.`)) return;
      retryDocument({ documentId, documentName: name, button });
      return;
    }
    if (action === "preview") {
      runRemediationScan({ dryRun: true, documentId, button });
      return;
    }
    if (action === "apply") {
      const name = button.dataset.documentName || "this document";
      if (!window.confirm(`Mark "${name}" failed? This affects only this document. Failed documents will remain available for manual review.`)) return;
      runRemediationScan({ dryRun: false, documentId, button });
    }
  });
  $("#subscriber-refresh").addEventListener("click", loadSubscribers);
  $("#invite-refresh").addEventListener("click", loadInvites);
  $("#invite-form").addEventListener("submit", createInvite);
  $("#admin-signout").addEventListener("click", signOut);

  $("#admin-clear").addEventListener("click", () => {
    $("#admin-key").value = "";
    $("#admin-key").focus();
    showError("");
  });

  checkSession();
})();
