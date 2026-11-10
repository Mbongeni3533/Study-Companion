/* Toolbox - CVs, application letters, humanising, integrity checks and
 * counselling, rendered inside the Study Companion shell.
 *
 * Every panel talks to /toolbox/* with the same bearer token the app uses. The
 * writing agents fall back to the server's rules engine, so the page works with
 * no AI key configured; when one is present the same endpoints return AI output.
 */
(() => {
  "use strict";

  const STORAGE_KEY = "study-companion.session";
  const API = "/toolbox";
  const TABS = [
    ["cv", "CV builder"],
    ["letters", "Emails & letters"],
    ["humanize", "Humanizer"],
    ["integrity", "Integrity"],
    ["dictionary", "Dictionary"],
    ["counselling", "Counselling"],
  ];

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function token() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      return saved && saved.token ? saved.token : null;
    } catch {
      return null;
    }
  }

  async function api(path, options = {}) {
    const { method = "GET", body } = options;
    const headers = { Accept: "application/json" };
    const bearer = token();
    if (bearer) headers.Authorization = `Bearer ${bearer}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";

    const response = await fetch(API + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
    if (!response.ok) {
      let detail = data && data.detail;
      if (Array.isArray(detail)) detail = detail.map((item) => item.msg || "").join(", ");
      throw new Error(detail || `Request failed (${response.status})`);
    }
    return data;
  }

  /** Read from an app route (/documents/...) rather than the /toolbox API. */
  async function appGet(path) {
    const bearer = token();
    const response = await fetch(path, {
      headers: { Accept: "application/json", ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) },
    });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    return response.json();
  }

  function toast(message, kind = "info") {
    const root = document.getElementById("toasts");
    if (!root) return;
    const node = document.createElement("div");
    node.className = `toast ${kind}`;
    node.textContent = message;
    root.appendChild(node);
    setTimeout(() => {
      node.style.opacity = "0";
      setTimeout(() => node.remove(), 220);
    }, 3600);
  }

  /* ------------------------------------------------------------ markdown */
  function inline(value) {
    return esc(value)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[\s(])_([^_]+)_/g, "$1<em>$2</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function renderMarkdown(text) {
    const lines = String(text || "").split("\n");
    const blocks = [];
    let list = null;
    const flush = () => {
      if (list) {
        blocks.push(`<ul>${list.join("")}</ul>`);
        list = null;
      }
    };
    for (const raw of lines) {
      const line = raw.trimEnd();
      const trimmed = line.trim();
      if (!trimmed) {
        flush();
        continue;
      }
      if (trimmed.startsWith("### ")) {
        flush();
        blocks.push(`<h4>${inline(trimmed.slice(4))}</h4>`);
      } else if (trimmed.startsWith("## ")) {
        flush();
        blocks.push(`<h3>${inline(trimmed.slice(3))}</h3>`);
      } else if (trimmed.startsWith("# ")) {
        flush();
        blocks.push(`<h2>${inline(trimmed.slice(2))}</h2>`);
      } else if (/^[-*] /.test(trimmed)) {
        list = list || [];
        list.push(`<li>${inline(trimmed.slice(2))}</li>`);
      } else {
        flush();
        blocks.push(`<p>${inline(trimmed)}</p>`);
      }
    }
    flush();
    return blocks.join("");
  }

  /* ---------------------------------------------------------------- helpers */
  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied to clipboard.", "success");
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      toast("Copied.", "success");
    }
  }

  async function downloadCvPdf(button) {
    if (!docs.cv) {
      toast("Generate a CV first.", "error");
      return;
    }
    const restore = busy(button, "Building PDF…");
    try {
      const bearer = token();
      const response = await fetch(`${API}/cv/pdf`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
        },
        body: JSON.stringify({ document: docs.cv, full_name: cvFullName || null }),
      });
      if (!response.ok) {
        let detail = `Request failed (${response.status})`;
        try {
          const data = await response.json();
          if (data.detail) detail = data.detail;
        } catch {
          /* keep the status message */
        }
        throw new Error(detail);
      }
      const blob = await response.blob();
      const slug = (cvFullName || "cv")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${slug || "cv"}-cv.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast("PDF downloaded.", "success");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      restore();
    }
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function busy(button, label) {
    if (!button) return () => {};
    const original = button.textContent;
    button.disabled = true;
    button.textContent = label;
    return () => {
      button.disabled = false;
      button.textContent = original;
    };
  }

  function chipList(list, variant = "") {
    return (list || []).map((item) => `<span class="chip ${variant}">${esc(item)}</span>`).join("");
  }

  function nameList(text) {
    return String(text || "")
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function lineList(text) {
    return String(text || "")
      .split("\n")
      .map((item) => item.trim().replace(/^[-*•]\s*/, ""))
      .filter(Boolean);
  }

  /* ------------------------------------------------------------------ shell */
  const SHELL = `
    <div class="tb tb-scope">
      <header class="tb-hero">
        <p class="tb-eyebrow">Toolbox</p>
        <h1>Get the application written.</h1>
        <p class="tb-lede">
          Six agents for the work that surrounds studying: a CV that matches your
          profession, letters that sound like you, a rewrite that strips the robot
          out of your prose, a check for copied text, and a counsellor when you want
          a person to look at it.
        </p>
        <p class="tb-mode" id="tb-mode"></p>
      </header>

      <nav class="tb-tabs" role="tablist" aria-label="Toolbox tools">
        ${TABS.map(
          ([key, label], index) => `
          <button role="tab" data-tb-tab="${key}" id="tb-tab-${key}" aria-controls="tb-panel-${key}"
            aria-selected="${index === 0 ? "true" : "false"}" class="${index === 0 ? "active" : ""}">
            ${label}
          </button>`
        ).join("")}
      </nav>

      <div class="tb-panels">
        <!-- ------------------------------------------------------------- CV -->
        <section class="tb-panel" id="tb-panel-cv" role="tabpanel" aria-labelledby="tb-tab-cv">
          <div class="tb-split">
            <form class="tb-card" id="tb-cv-form">
              <div class="tb-card-head">
                <h2>CV builder</h2>
                <p>Fill what you have. The agent fills the structure; it never invents a job or a date.</p>
              </div>

              <div class="tb-row2">
                <div class="field"><label for="tb-cv-name">Full name</label><input id="tb-cv-name" maxlength="120" /></div>
                <div class="field"><label for="tb-cv-email">Email</label><input id="tb-cv-email" type="email" maxlength="200" /></div>
              </div>
              <div class="tb-row2">
                <div class="field"><label for="tb-cv-phone">Phone</label><input id="tb-cv-phone" maxlength="60" placeholder="Optional" /></div>
                <div class="field"><label for="tb-cv-location">Location</label><input id="tb-cv-location" maxlength="120" placeholder="City, country" /></div>
              </div>
              <div class="tb-row2">
                <div class="field">
                  <label for="tb-cv-profession">Profession</label>
                  <input id="tb-cv-profession" list="tb-professions" maxlength="120" placeholder="Start typing…" />
                  <datalist id="tb-professions"></datalist>
                </div>
                <div class="field"><label for="tb-cv-target">Target role</label><input id="tb-cv-target" maxlength="160" placeholder="e.g. Junior Backend Developer" /></div>
              </div>
              <div class="tb-row2">
                <div class="field"><label for="tb-cv-years">Years of experience</label><input id="tb-cv-years" type="number" min="0" max="60" placeholder="0" /></div>
                <div class="field"><label for="tb-cv-skills">Skills (comma separated)</label><input id="tb-cv-skills" placeholder="Leave blank to use your profession's defaults" /></div>
              </div>

              <div class="tb-section">
                <div class="tb-section-head">
                  <h3>Experience</h3>
                  <button type="button" class="btn btn-ghost btn-sm" id="tb-add-exp">Add role</button>
                </div>
                <div id="tb-cv-exp"></div>
              </div>

              <div class="field"><label for="tb-cv-education">Education (one per line)</label><textarea id="tb-cv-education" rows="2" placeholder="BSc Computer Science, University of Pretoria, 2024"></textarea></div>
              <div class="field"><label for="tb-cv-certifications">Certifications you hold (one per line)</label><textarea id="tb-cv-certifications" rows="2" placeholder="Only ones you actually hold - the agent will not add any"></textarea></div>
              <div class="field"><label for="tb-cv-achievements">Achievements (one per line)</label><textarea id="tb-cv-achievements" rows="2" placeholder="One result with a number in it"></textarea></div>
              <div class="field"><label for="tb-cv-jd">Paste the job advert (optional)</label><textarea id="tb-cv-jd" rows="3" placeholder="The agent checks which of its keywords your CV already covers"></textarea></div>

              <button type="submit" class="btn btn-primary" id="tb-cv-submit">Build my CV</button>
            </form>

            <div class="tb-card tb-output" id="tb-cv-output">
              <div class="tb-card-head"><h2>Your CV</h2><p>Markdown you can paste anywhere.</p></div>
              <div class="tb-placeholder">
                <p>Nothing generated yet. Fill the form and the draft appears here.</p>
              </div>
            </div>
          </div>
        </section>

        <!-- -------------------------------------------------------- letters -->
        <section class="tb-panel" id="tb-panel-letters" role="tabpanel" aria-labelledby="tb-tab-letters" hidden>
          <div class="tb-split">
            <form class="tb-card" id="tb-lt-form">
              <div class="tb-card-head">
                <h2>Emails &amp; letters</h2>
                <p>Cover letters and application emails, written around your profession and the role.</p>
              </div>

              <div class="tb-pills" role="group" aria-label="What are you writing">
                <button type="button" class="tb-pill active" data-lt-kind="cover_letter">Cover letter</button>
                <button type="button" class="tb-pill" data-lt-kind="email">Application email</button>
              </div>

              <div class="tb-row2">
                <div class="field">
                  <label for="tb-lt-profession">Profession</label>
                  <input id="tb-lt-profession" list="tb-professions" maxlength="120" placeholder="Start typing…" />
                </div>
                <div class="field"><label for="tb-lt-role">Role applied for</label><input id="tb-lt-role" maxlength="160" placeholder="e.g. Data Analyst" /></div>
              </div>
              <div class="tb-row2">
                <div class="field"><label for="tb-lt-company">Company</label><input id="tb-lt-company" maxlength="160" placeholder="Optional" /></div>
                <div class="field"><label for="tb-lt-recipient">Addressed to</label><input id="tb-lt-recipient" maxlength="160" placeholder="Hiring Manager" /></div>
              </div>
              <div class="tb-row2">
                <div class="field"><label for="tb-lt-tone">Tone</label><select id="tb-lt-tone"></select></div>
                <div class="field"><label for="tb-lt-name">Sign off as</label><input id="tb-lt-name" maxlength="120" /></div>
              </div>
              <div class="field">
                <label for="tb-lt-highlights">Things you want mentioned (one per line)</label>
                <textarea id="tb-lt-highlights" rows="4" placeholder="A result with a number in it is worth ten adjectives"></textarea>
              </div>
              <div class="field"><label for="tb-lt-jd">Paste the advert (optional)</label><textarea id="tb-lt-jd" rows="2"></textarea></div>

              <button type="submit" class="btn btn-primary" id="tb-lt-submit">Write it</button>
            </form>

            <div class="tb-card tb-output" id="tb-lt-output">
              <div class="tb-card-head"><h2>Your letter</h2><p>Read it out loud before sending - that catches what templates hide.</p></div>
              <div class="tb-placeholder"><p>Nothing written yet.</p></div>
            </div>
          </div>
        </section>

        <!-- ------------------------------------------------------- humanize -->
        <section class="tb-panel" id="tb-panel-humanize" role="tabpanel" aria-labelledby="tb-tab-humanize" hidden>
          <div class="tb-card">
            <div class="tb-card-head">
              <h2>Humanizer</h2>
              <p>Strips clichés, filler and machine phrasing. Every change is listed so you can reject any that alters your meaning.</p>
            </div>
            <div class="tb-row2">
              <div class="field">
                <label for="tb-hz-tone">Tone</label>
                <select id="tb-hz-tone">
                  <option value="professional">Professional</option>
                  <option value="warm">Warm</option>
                  <option value="direct">Direct</option>
                  <option value="academic">Academic (no contractions)</option>
                </select>
              </div>
              <div class="field tb-align-end">
                <button type="button" class="btn btn-ghost btn-sm" id="tb-hz-sample">Paste a sample</button>
              </div>
            </div>
            <div class="field">
              <label for="tb-hz-input">Your text</label>
              <textarea id="tb-hz-input" rows="9" placeholder="Paste the paragraph that sounds like a machine wrote it…"></textarea>
            </div>
            <button type="button" class="btn btn-primary" id="tb-hz-submit">Humanise it</button>
          </div>

          <div id="tb-hz-output" class="tb-output-block"></div>
        </section>

        <!-- -------------------------------------------------------- integrity -->
        <section class="tb-panel" id="tb-panel-integrity" role="tabpanel" aria-labelledby="tb-tab-integrity" hidden>
          <div class="tb-card">
            <div class="tb-card-head">
              <h2>Integrity check</h2>
              <p>Finds text copied from your own library, uncited quotes, repeated sentences and AI-sounding phrasing.</p>
            </div>
            <div class="field">
              <label for="tb-ig-text">The text you are about to submit</label>
              <textarea id="tb-ig-text" rows="9" placeholder="Paste your essay, report or paragraph…"></textarea>
            </div>
            <div class="tb-row2">
              <div class="field">
                <label for="tb-ig-course">Compare against</label>
                <select id="tb-ig-course"><option value="">All my material</option></select>
              </div>
              <div class="field tb-align-end">
                <button type="button" class="btn btn-primary" id="tb-ig-submit">Run the check</button>
              </div>
            </div>
          </div>

          <div id="tb-ig-output" class="tb-output-block"></div>
        </section>

        <!-- ------------------------------------------------------ dictionary -->
        <section class="tb-panel" id="tb-panel-dictionary" role="tabpanel" aria-labelledby="tb-tab-dictionary" hidden>
          <div class="tb-card">
            <div class="tb-card-head">
              <h2>English dictionary</h2>
              <p>Look up a word's meaning, pronunciation, examples and synonyms.</p>
            </div>
            <div class="tb-row2">
              <div class="field"><label for="tb-dict-word">Word</label><input id="tb-dict-word" maxlength="60" placeholder="e.g. serendipity" /></div>
              <div class="field tb-align-end"><button type="button" class="btn btn-primary" id="tb-dict-submit">Look it up</button></div>
            </div>
          </div>
          <div id="tb-dict-output" class="tb-output-block"></div>
        </section>

        <!-- ------------------------------------------------------ counselling -->
        <section class="tb-panel" id="tb-panel-counselling" role="tabpanel" aria-labelledby="tb-tab-counselling" hidden>
          <div class="tb-card">
            <div class="tb-card-head">
              <h2>Book a counselling session</h2>
              <p>Thirty minutes with a careers or study counsellor. Pick a free slot below.</p>
            </div>
            <div id="tb-co-body" class="tb-loading">Loading counsellors…</div>
          </div>
        </section>
      </div>
    </div>`;

  /* ------------------------------------------------------------------ state */
  let meta = null;
  let currentUser = null;
  let activeTab = "cv";
  let letterKind = "cover_letter";
  let selectedSlot = null;
  let counsellingLoaded = false;
  let docs = { cv: "", letter: "" };
  let cvFullName = "";

  const SAMPLE = `In today's fast-paced world, it is important to note that students must delve into a plethora of resources in order to facilitate their learning. Furthermore, educators utilize a myriad of digital tools, and it is essential that we leverage these robust platforms to elevate outcomes.`;

  /* ------------------------------------------------------------------ setup */
  function experienceRow(values = {}) {
    const row = document.createElement("div");
    row.className = "tb-exp-row";
    row.innerHTML = `
      <div class="tb-row3">
        <div class="field"><label>Role</label><input data-exp="role" maxlength="160" value="${esc(values.role || "")}" /></div>
        <div class="field"><label>Organisation</label><input data-exp="organisation" maxlength="160" value="${esc(values.organisation || "")}" /></div>
        <div class="field"><label>Dates</label><input data-exp="period" maxlength="80" placeholder="2023 - now" value="${esc(values.period || "")}" /></div>
      </div>
      <div class="field">
        <label>Achievements (one per line)</label>
        <textarea data-exp="highlights" rows="3" placeholder="What you did, and what changed because of it">${esc(values.highlights || "")}</textarea>
      </div>
      <button type="button" class="btn btn-quiet btn-sm" data-remove-exp>Remove this role</button>`;
    return row;
  }

  function setTab(tab, container) {
    if (!TABS.some(([key]) => key === tab)) tab = "cv";
    activeTab = tab;
    $$("[data-tb-tab]", container).forEach((button) => {
      const on = button.dataset.tbTab === tab;
      button.classList.toggle("active", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
    });
    TABS.forEach(([key]) => {
      const panel = $(`#tb-panel-${key}`, container);
      if (panel) panel.hidden = key !== tab;
    });
    if (tab === "counselling" && !counsellingLoaded) loadCounselling(container);
    if (tab === "integrity") loadCourses();
  }

  async function loadMeta(container) {
    try {
      meta = await api("/meta");
    } catch (error) {
      toast(error.message, "error");
      return;
    }

    const datalist = $("#tb-professions", container);
    datalist.innerHTML = meta.professions
      .map((item) => `<option value="${esc(item.label)}"></option>`)
      .join("");

    const defaultProfession = (currentUser && currentUser.profession) || "";
    ["#tb-cv-profession", "#tb-lt-profession"].forEach((selector) => {
      const input = $(selector, container);
      if (input && !input.value) input.value = defaultProfession;
    });

    const tones = $("#tb-lt-tone", container);
    tones.innerHTML = meta.tones
      .map((tone) => `<option value="${esc(tone.key)}" title="${esc(tone.note)}">${esc(tone.label)}</option>`)
      .join("");

    const mode = $("#tb-mode", container);
    mode.textContent = meta.ai_available
      ? "Writing agents are running with AI assistance."
      : "Writing agents are running on the built-in rules engine - no AI key configured, everything still works.";
  }

  async function loadCourses() {
    try {
      const courses = await appGet("/documents/courses");
      const select = $("#tb-ig-course");
      if (!select) return;
      select.innerHTML =
        `<option value="">All my material</option>` +
        (courses || []).map((course) => `<option value="${esc(course.id)}">${esc(course.title)}</option>`).join("");
    } catch {
      /* the check still works against the whole library */
    }
  }

  /* --------------------------------------------------------------------- CV */
  async function submitCV(container) {
    const button = $("#tb-cv-submit", container);
    const restore = busy(button, "Writing…");
    try {
      const payload = {
        profession: $("#tb-cv-profession", container).value.trim() || "Student",
        full_name: $("#tb-cv-name", container).value.trim() || null,
        email: $("#tb-cv-email", container).value.trim() || null,
        phone: $("#tb-cv-phone", container).value.trim() || null,
        location: $("#tb-cv-location", container).value.trim() || null,
        target_role: $("#tb-cv-target", container).value.trim() || null,
        years_experience: Number($("#tb-cv-years", container).value) || null,
        skills: nameList($("#tb-cv-skills", container).value),
        education: lineList($("#tb-cv-education", container).value),
        certifications: lineList($("#tb-cv-certifications", container).value),
        achievements: lineList($("#tb-cv-achievements", container).value),
        job_description: $("#tb-cv-jd", container).value.trim() || null,
        experience: $$(".tb-exp-row", container)
          .map((row) => ({
            role: $('[data-exp="role"]', row).value.trim(),
            organisation: $('[data-exp="organisation"]', row).value.trim(),
            period: $('[data-exp="period"]', row).value.trim(),
            highlights: lineList($('[data-exp="highlights"]', row).value),
          }))
          .filter((item) => item.role || item.organisation),
      };

      const result = await api("/cv", { method: "POST", body: payload });
      docs.cv = result.document;
      cvFullName = payload.full_name || "";
      const output = $("#tb-cv-output", container);
      output.innerHTML = `
        <div class="tb-card-head">
          <h2>${esc(result.profession_label)} CV</h2>
          <p>${result.source === "ai" ? "Written with AI assistance" : "Built by the rules engine"} · check every line before sending.</p>
        </div>
        <div class="tb-doc">${renderMarkdown(result.document)}</div>
        <div class="tb-actions">
          <button class="btn btn-primary btn-sm" data-pdf="cv">Download PDF</button>
          <button class="btn btn-ghost btn-sm" data-copy="cv">Copy</button>
          <button class="btn btn-ghost btn-sm" data-download="cv">Markdown</button>
        </div>
        ${
          result.suggestions && result.suggestions.length
            ? `<div class="tb-note"><h3>Before you send it</h3><ul>${result.suggestions
                .map((tip) => `<li>${esc(tip)}</li>`)
                .join("")}</ul></div>`
            : ""
        }
        ${
          result.matched_keywords && result.matched_keywords.length
            ? `<div class="tb-keywords"><span class="tb-label">Advert keywords already covered</span><div class="tb-chips">${chipList(
                result.matched_keywords,
                "chip-emerald"
              )}</div></div>`
            : ""
        }
        ${
          result.missing_keywords && result.missing_keywords.length
            ? `<div class="tb-keywords"><span class="tb-label">Worth adding</span><div class="tb-chips">${chipList(
                result.missing_keywords,
                "chip-amber"
              )}</div></div>`
            : ""
        }`;
    } catch (error) {
      toast(error.message, "error");
    } finally {
      restore();
    }
  }

  /* ---------------------------------------------------------------- letters */
  async function submitLetter(container) {
    const button = $("#tb-lt-submit", container);
    const restore = busy(button, "Writing…");
    try {
      const payload = {
        kind: letterKind,
        profession: $("#tb-lt-profession", container).value.trim() || "Student",
        role: $("#tb-lt-role", container).value.trim(),
        company: $("#tb-lt-company", container).value.trim(),
        recipient: $("#tb-lt-recipient", container).value.trim() || null,
        tone: $("#tb-lt-tone", container).value || "professional",
        highlights: lineList($("#tb-lt-highlights", container).value),
        job_description: $("#tb-lt-jd", container).value.trim() || null,
        your_name: $("#tb-lt-name", container).value.trim() || null,
      };
      if (payload.role.length < 2) {
        toast("Name the role you are applying for.", "error");
        return;
      }

      const result = await api("/letters", { method: "POST", body: payload });
      docs.letter = (result.subject ? `Subject: ${result.subject}\n\n` : "") + result.body;
      const output = $("#tb-lt-output", container);
      output.innerHTML = `
        <div class="tb-card-head">
          <h2>${letterKind === "email" ? "Application email" : "Cover letter"}</h2>
          <p>${result.source === "ai" ? "Written with AI assistance" : "Written by the rules engine"} · ${docs.letter.split(/\s+/).length} words</p>
        </div>
        ${result.subject ? `<p class="tb-subject"><span>Subject</span>${esc(result.subject)}</p>` : ""}
        <div class="tb-doc tb-letter">${renderMarkdown(result.body)}</div>
        <div class="tb-actions">
          <button class="btn btn-ghost btn-sm" data-copy="letter">Copy</button>
          <button class="btn btn-ghost btn-sm" data-download="letter">Download .md</button>
        </div>
        ${
          result.tips && result.tips.length
            ? `<div class="tb-note"><h3>Make it yours</h3><ul>${result.tips.map((tip) => `<li>${esc(tip)}</li>`).join("")}</ul></div>`
            : ""
        }`;
    } catch (error) {
      toast(error.message, "error");
    } finally {
      restore();
    }
  }

  /* --------------------------------------------------------------- humanize */
  function metricsRow(label, metrics, other) {
    const delta = metrics.reading_ease - other.reading_ease;
    return `
      <div class="tb-metric">
        <span class="tb-metric-label">${label}</span>
        <strong>${metrics.words}</strong> words · avg ${metrics.average_sentence_words} · ease ${metrics.reading_ease}
        ${delta > 0 ? `<span class="tb-delta">+${delta.toFixed(1)}</span>` : ""}
      </div>`;
  }

  async function submitHumanize(container) {
    const text = $("#tb-hz-input", container).value.trim();
    if (text.length < 20) {
      toast("Paste at least a couple of sentences.", "error");
      return;
    }
    const button = $("#tb-hz-submit", container);
    const restore = busy(button, "Rewriting…");
    try {
      const result = await api("/humanize", {
        method: "POST",
        body: { text, tone: $("#tb-hz-tone", container).value },
      });
      const output = $("#tb-hz-output", container);
      output.innerHTML = `
        <div class="tb-card">
          <div class="tb-card-head">
            <h2>Rewritten</h2>
            <p>${result.changes.length} change(s)${result.source === "ai" ? " · AI-assisted rewrite" : ""}</p>
          </div>
          <div class="tb-doc">${result.text
            .split("\n\n")
            .map((para) => `<p>${inline(para)}</p>`)
            .join("")}</div>
          <div class="tb-actions">
            <button class="btn btn-ghost btn-sm" id="tb-hz-apply">Use this version</button>
            <button class="btn btn-ghost btn-sm" data-copy="humanized">Copy</button>
          </div>
          <div class="tb-metrics">
            ${metricsRow("Before", result.before, result.after)}
            ${metricsRow("After", result.after, result.before)}
            <div class="tb-metric"><span class="tb-metric-label">Long sentences</span><strong>${result.after.long_sentences}</strong> left</div>
          </div>
          ${
            result.changes.length
              ? `<div class="tb-note"><h3>What changed</h3><ul class="tb-changes">${result.changes
                  .map(
                    (change) =>
                      `<li><span class="tb-was">${esc(change.before)}</span><span class="tb-arrow">→</span><span class="tb-now">${esc(
                        change.after
                      )}</span><span class="tb-why">${esc(change.reason)}</span></li>`
                  )
                  .join("")}</ul></div>`
              : ""
          }
          ${
            result.notes && result.notes.length
              ? `<div class="tb-scope">${result.notes.map((note) => `<p>${esc(note)}</p>`).join("")}</div>`
              : ""
          }
        </div>`;
      output.querySelector("#tb-hz-apply").addEventListener("click", () => {
        $("#tb-hz-input", container).value = result.text;
        toast("Replaced your text with the rewrite.", "success");
      });
      output.querySelector('[data-copy="humanized"]').addEventListener("click", () => copyText(result.text));
    } catch (error) {
      toast(error.message, "error");
    } finally {
      restore();
    }
  }

  /* -------------------------------------------------------------- integrity */
  function levelChip(level) {
    const map = { low: ["Looks clean", "chip-emerald"], medium: ["Review it", "chip-amber"], high: ["High overlap", "chip-rose"] };
    const [label, cls] = map[level] || map.low;
    return `<span class="chip ${cls}">${label}</span>`;
  }

  async function submitIntegrity(container) {
    const text = $("#tb-ig-text", container).value.trim();
    if (text.length < 40) {
      toast("Paste at least a short paragraph.", "error");
      return;
    }
    const button = $("#tb-ig-submit", container);
    const restore = busy(button, "Checking…");
    try {
      const result = await api("/integrity", {
        method: "POST",
        body: { text, course_id: $("#tb-ig-course", container).value || null },
      });
      const output = $("#tb-ig-output", container);
      output.innerHTML = `
        <div class="tb-card">
          <div class="tb-card-head">
            <h2>Result ${levelChip(result.level)}</h2>
            <p>${esc(result.verdict)}</p>
          </div>
          <div class="tb-score">
            <div class="tb-score-bar"><span class="level-${result.level}" style="width:${Math.max(
              2,
              result.similarity_score
            )}%"></span></div>
            <div class="tb-score-text">
              <strong>${result.similarity_score}%</strong> matched text
              <span class="muted">· ${result.originality_score}% found nowhere in your library</span>
            </div>
          </div>
          ${
            result.matches.length
              ? `<div class="tb-note"><h3>Matched passages</h3><ul class="tb-matches">${result.matches
                  .map(
                    (match) =>
                      `<li>
                        <div class="tb-match-head"><span class="chip chip-amber">${match.similarity}%</span> <span class="muted">${esc(
                        match.source
                      )}</span></div>
                        <p>${esc(match.sentence)}</p>
                      </li>`
                  )
                  .join("")}</ul></div>`
              : ""
          }
          ${
            result.flags.length
              ? `<div class="tb-note"><h3>Also flagged</h3><ul>${result.flags
                  .map((flag) => `<li><strong>${esc(flag.label)}</strong> ${esc(flag.detail)}</li>`)
                  .join("")}</ul></div>`
              : ""
          }
          <div class="tb-shell-note">
            <p>${esc(result.scope)}</p>
            <p class="muted">Checked ${result.sources_checked} source(s) and ${result.passages_checked} passage(s).</p>
          </div>
        </div>`;
    } catch (error) {
      toast(error.message, "error");
    } finally {
      restore();
    }
  }

  /* ----------------------------------------------------------- dictionary */
  async function submitDictionary(container) {
    const word = $("#tb-dict-word", container).value.trim();
    if (!word) {
      toast("Type a word to look up.", "error");
      return;
    }
    const button = $("#tb-dict-submit", container);
    const restore = busy(button, "Looking up…");
    try {
      const result = await api(`/dictionary/${encodeURIComponent(word)}`);
      const output = $("#tb-dict-output", container);
      const groups = [];
      let currentPos = null;
      let items = [];
      for (const entry of result.entries || []) {
        if (entry.part_of_speech !== currentPos) {
          if (items.length) groups.push({ pos: currentPos, items });
          currentPos = entry.part_of_speech;
          items = [];
        }
        items.push(entry);
      }
      if (items.length) groups.push({ pos: currentPos, items });

      output.innerHTML = `
        <div class="tb-card">
          <div class="tb-card-head">
            <h2>${esc(result.word)}${result.phonetic ? ` <span class="muted">${esc(result.phonetic)}</span>` : ""}</h2>
            <p>${result.entries.length} definition(s) · ${esc(result.source)}</p>
          </div>
          ${groups
            .map(
              (group) => `
            <div class="tb-note">
              <h3>${esc(group.pos || "definition")}</h3>
              <ul>${group.items
                .map(
                  (item) => `
                <li>
                  <p>${esc(item.definition)}</p>
                  ${item.example ? `<p class="muted small"><em>${esc(item.example)}</em></p>` : ""}
                  ${
                    item.synonyms && item.synonyms.length
                      ? `<p class="small"><span class="tb-label">Synonyms</span> ${chipList(item.synonyms, "chip-violet")}</p>`
                      : ""
                  }
                  ${
                    item.antonyms && item.antonyms.length
                      ? `<p class="small"><span class="tb-label">Antonyms</span> ${chipList(item.antonyms, "chip-amber")}</p>`
                      : ""
                  }
                </li>`
                )
                .join("")}</ul>
            </div>`
            )
            .join("")}
        </div>`;
    } catch (error) {
      toast(error.message, "error");
      $("#tb-dict-output", container).innerHTML = "";
    } finally {
      restore();
    }
  }

  /* ------------------------------------------------------------- counselling */
  async function loadCounselling(container) {
    const body = $("#tb-co-body", container);
    if (!body) return;
    counsellingLoaded = true;
    try {
      const data = await api("/counselling");
      renderCounselling(container, data);
    } catch (error) {
      counsellingLoaded = false;
      body.innerHTML = `<p class="form-error">${esc(error.message)}</p>`;
    }
  }

  function renderCounselling(container, data) {
    const body = $("#tb-co-body", container);
    selectedSlot = null;
    const upcoming = data.sessions.filter((session) => session.status === "booked");
    const past = data.sessions.filter((session) => session.status !== "booked");

    body.innerHTML = `
      <div class="tb-counsellors">
        ${data.counsellors
          .map(
            (person) => `
          <article class="tb-counsellor">
            <div class="tb-counsellor-top">
              <span class="avatar">${esc(
                person.name
                  .split(" ")
                  .slice(0, 2)
                  .map((part) => part[0])
                  .join("")
              )}</span>
              <div>
                <h3>${esc(person.name)}</h3>
                <p class="muted small">${esc(person.title)}</p>
              </div>
            </div>
            <p class="small">${esc(person.bio)}</p>
            <div class="tb-chips">${chipList(person.specialties, "chip-violet")}</div>
            <p class="small muted">Languages: ${esc(person.languages.join(", "))}${
              person.next_slot ? ` · Next: ${esc(person.next_slot)}` : ""
            }</p>
          </article>`
          )
          .join("")}
      </div>

      <div class="tb-booking">
        <div class="tb-row2">
          <div class="field">
            <label for="tb-co-counsellor">Counsellor</label>
            <select id="tb-co-counsellor">
              ${data.counsellors
                .map((person) => `<option value="${esc(person.id)}">${esc(person.name)}</option>`)
                .join("")}
            </select>
          </div>
          <div class="field">
            <label for="tb-co-focus">What do you need?</label>
            <select id="tb-co-focus">
              ${data.focus_options.map((focus) => `<option value="${esc(focus)}">${esc(focus)}</option>`).join("")}
            </select>
          </div>
        </div>
        <span class="tb-label">Free slots <span class="muted">(UTC)</span></span>
        <div class="tb-slots" id="tb-co-slots"></div>
        <div class="field">
          <label for="tb-co-notes">Anything the counsellor should know? (optional)</label>
          <textarea id="tb-co-notes" rows="2" maxlength="1000"></textarea>
        </div>
        <button class="btn btn-primary" id="tb-co-book" disabled>Pick a slot first</button>
      </div>

      <div class="tb-note">
        <h3>Your sessions</h3>
        ${
          upcoming.length || past.length
            ? `<ul class="tb-sessions">${[...upcoming, ...past]
                .map(
                  (session) => `
              <li class="${session.status !== "booked" ? "cancelled" : ""}">
                <div>
                  <strong>${esc(session.counsellor_name)}</strong>
                  <span class="muted small"> · ${esc(session.focus)}</span>
                  <div class="muted small">${new Date(session.scheduled_for).toLocaleString(undefined, {
                    weekday: "short",
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                    timeZone: "UTC",
                  })} UTC · ${session.duration_minutes} min</div>
                </div>
                ${
                  session.status === "booked"
                    ? `<button class="btn btn-ghost btn-sm" data-cancel-booking="${esc(session.id)}">Cancel</button>`
                    : `<span class="chip">${esc(session.status)}</span>`
                }
              </li>`
                )
                .join("")}</ul>`
            : `<p class="muted small">No sessions booked yet.</p>`
        }
      </div>`;

    const slotsNode = $("#tb-co-slots", container);
    const counsellorSelect = $("#tb-co-counsellor", container);
    const bookButton = $("#tb-co-book", container);

    function paintSlots() {
      const counsellorId = counsellorSelect.value;
      const slots = data.slots.filter((slot) => slot.counsellor_id === counsellorId).slice(0, 8);
      slotsNode.innerHTML = slots.length
        ? slots
            .map(
              (slot) =>
                `<button type="button" class="tb-slot" data-slot="${esc(slot.date)}|${esc(slot.time)}">${esc(
                  slot.label
                )}</button>`
            )
            .join("")
        : `<p class="muted small">No free slots in the next two weeks with this counsellor. Try another.</p>`;
    }

    counsellorSelect.addEventListener("change", paintSlots);
    paintSlots();

    slotsNode.addEventListener("click", (event) => {
      const button = event.target.closest("[data-slot]");
      if (!button) return;
      $$("[data-slot]", slotsNode).forEach((node) => node.classList.remove("selected"));
      button.classList.add("selected");
      const [date, time] = button.dataset.slot.split("|");
      selectedSlot = { date, time, counsellor_id: counsellorSelect.value, label: button.textContent };
      bookButton.disabled = false;
      bookButton.textContent = `Book ${selectedSlot.label}`;
    });

    bookButton.addEventListener("click", async () => {
      if (!selectedSlot) return;
      const restore = busy(bookButton, "Booking…");
      try {
        await api("/counselling", {
          method: "POST",
          body: {
            counsellor_id: selectedSlot.counsellor_id,
            focus: $("#tb-co-focus", container).value,
            date: selectedSlot.date,
            time: selectedSlot.time,
            notes: $("#tb-co-notes", container).value.trim() || null,
          },
        });
        toast("Session booked. It is in your sessions list below.", "success");
        const fresh = await api("/counselling");
        renderCounselling(container, fresh);
      } catch (error) {
        toast(error.message, "error");
        restore();
      }
    });

    body.querySelectorAll("[data-cancel-booking]").forEach((button) => {
      button.addEventListener("click", async () => {
        const restore = busy(button, "Cancelling…");
        try {
          await api(`/counselling/${button.dataset.cancelBooking}/cancel`, { method: "POST" });
          toast("Booking cancelled.", "success");
          const fresh = await api("/counselling");
          renderCounselling(container, fresh);
        } catch (error) {
          toast(error.message, "error");
          restore();
        }
      });
    });
  }

  /* ------------------------------------------------------------------- mount */
  function mount(container, options = {}) {
    currentUser = options.user || null;
    container.innerHTML = SHELL;
    // A remount replaces the panel markup, so its loaded state goes with it.
    counsellingLoaded = false;
    selectedSlot = null;

    const expHost = $("#tb-cv-exp", container);
    expHost.appendChild(experienceRow());

    $("#tb-add-exp", container).addEventListener("click", () => expHost.appendChild(experienceRow()));
    expHost.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-remove-exp]");
      if (!remove) return;
      if ($$(".tb-exp-row", expHost).length === 1) {
        $$("input, textarea", remove.parentElement).forEach((field) => (field.value = ""));
        return;
      }
      remove.parentElement.remove();
    });

    // CV + letter prefill from the signed-in profile.
    const user = currentUser;
    if (user) {
      $("#tb-cv-name", container).value = user.name && user.name !== "Guest student" ? user.name : "";
      $("#tb-cv-email", container).value = user.email || "";
      $("#tb-lt-name", container).value = user.name && user.name !== "Guest student" ? user.name : "";
    }

    $("#tb-cv-form", container).addEventListener("submit", (event) => {
      event.preventDefault();
      submitCV(container);
    });
    $("#tb-lt-form", container).addEventListener("submit", (event) => {
      event.preventDefault();
      submitLetter(container);
    });

    $$("[data-lt-kind]", container).forEach((button) => {
      button.addEventListener("click", () => {
        letterKind = button.dataset.ltKind;
        $$("[data-lt-kind]", container).forEach((node) => node.classList.toggle("active", node === button));
      });
    });

    $("#tb-hz-sample", container).addEventListener("click", () => {
      $("#tb-hz-input", container).value = SAMPLE;
    });
    $("#tb-hz-submit", container).addEventListener("click", () => submitHumanize(container));
    $("#tb-ig-submit", container).addEventListener("click", () => submitIntegrity(container));
    $("#tb-dict-submit", container).addEventListener("click", () => submitDictionary(container));
    $("#tb-dict-word", container).addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitDictionary(container);
      }
    });

    container.addEventListener("click", (event) => {
      const tabButton = event.target.closest("[data-tb-tab]");
      if (tabButton) {
        setTab(tabButton.dataset.tbTab, container);
        return;
      }
      const pdf = event.target.closest("[data-pdf=\"cv\"]");
      if (pdf) {
        downloadCvPdf(pdf);
        return;
      }
      const copy = event.target.closest("[data-copy]");
      if (copy) {
        if (copy.dataset.copy === "cv") copyText(docs.cv);
        if (copy.dataset.copy === "letter") copyText(docs.letter);
        return;
      }
      const download = event.target.closest("[data-download]");
      if (download) {
        const key = download.dataset.download;
        if (docs[key]) {
          downloadText(key === "cv" ? "cv.md" : "cover-letter.md", docs[key]);
        }
      }
    });

    loadMeta(container);
    setTab(options.tab || activeTab, container);
  }

  window.Toolbox = { mount };
})();
