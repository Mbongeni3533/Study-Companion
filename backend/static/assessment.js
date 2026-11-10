/* Assessment - the thinking check shown to new accounts. Plain English only. */
(() => {
  "use strict";

  const STORAGE_KEY = "study-companion.session";
  const API = "/assessment";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function esc(value) {
    return String(value ?? "").replace(/[&<>\"']/g, (char) => ({
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
      try { data = JSON.parse(text); } catch { data = null; }
    }
    if (!response.ok) {
      let detail = data && data.detail;
      if (Array.isArray(detail)) detail = detail.map((item) => item.msg || "").join(", ");
      throw new Error(detail || `Request failed (${response.status})`);
    }
    return data;
  }

  function mount(container, opts = {}) {
    const onComplete = typeof opts.onComplete === "function" ? opts.onComplete : () => {};

    const state = {
      loading: true,
      error: null,
      intro: null,
      questions: [],
      profile: null,
      step: "intro", // intro | question | result
      index: 0,
      answers: {},
      submitting: false,
      resultProfile: null,
    };

    async function load() {
      try {
        const data = await api("");
        state.intro = data.intro || {};
        state.questions = Array.isArray(data.questions) ? data.questions : [];
        state.profile = data.profile || null;
        state.loading = false;
      } catch (error) {
        state.loading = false;
        state.error = error.message;
      }
      paint();
    }

    function paint() {
      if (state.loading) {
        container.innerHTML = `<div class="assessment-loading">Loading your check...</div>`;
        return;
      }
      if (state.error) {
        container.innerHTML = `
          <div class="assessment-card">
            <h2>Could not load the check</h2>
            <p class="muted">${esc(state.error)}</p>
            <button class="btn btn-primary" data-action="retry">Try again</button>
          </div>`;
        const btn = container.querySelector('[data-action="retry"]');
        if (btn) btn.addEventListener("click", () => { state.loading = true; state.error = null; paint(); load(); });
        return;
      }
      if (state.step === "intro") renderIntro();
      else if (state.step === "question") renderQuestion();
      else if (state.step === "result") renderResult();
    }

    function renderIntro() {
      const intro = state.intro || {};
      const hasProfile = !!state.profile;
      container.innerHTML = `
        <div class="assessment-intro">
          <p class="assessment-eyebrow">${esc(intro.eyebrow || "Before you start")}</p>
          <h1 class="assessment-title">${esc(intro.title || "A quick check, not an exam")}</h1>
          <p class="assessment-body">${esc(intro.body || "")}</p>
          <p class="assessment-note">${esc(intro.note || "")}</p>
          ${hasProfile ? `
            <div class="assessment-current">
              <p class="small muted">Your current result: <strong>${esc(state.profile.level_label || "")}</strong></p>
            </div>` : ""}
          <div class="assessment-actions">
            <button class="btn btn-primary btn-lg" data-action="start">${esc(intro.start || "Start the check")}</button>
            <button class="btn btn-ghost" data-action="skip">${esc(intro.skip || "Skip for now")}</button>
          </div>
          <p class="assessment-privacy small muted">Only you can see your result.</p>
        </div>`;
      container.querySelector('[data-action="start"]').addEventListener("click", () => {
        state.step = "question";
        state.index = 0;
        state.answers = {};
        paint();
      });
      container.querySelector('[data-action="skip"]').addEventListener("click", () => {
        window.location.hash = "#/dashboard";
      });
    }

    function renderQuestion() {
      const q = state.questions[state.index];
      if (!q) { state.step = "result"; paint(); return; }
      const total = state.questions.length;
      const chosen = state.answers[q.id];
      const progress = ((state.index) / total) * 100;
      container.innerHTML = `
        <div class="assessment-question-card">
          <div class="assessment-progress">
            <div class="assessment-progress-bar" style="width:${progress}%"></div>
          </div>
          <p class="assessment-progress-label">Question ${state.index + 1} of ${total}</p>
          <h2 class="assessment-prompt">${esc(q.prompt)}</h2>
          <div class="assessment-options" role="radiogroup" aria-label="${esc(q.prompt)}">
            ${q.options.map((opt) => `
              <button type="button" class="assessment-option ${chosen === opt.id ? "selected" : ""}" data-option="${esc(opt.id)}" aria-pressed="${chosen === opt.id}">
                <span class="assessment-option-dot" aria-hidden="true"></span>
                <span class="assessment-option-label">${esc(opt.label)}</span>
              </button>`).join("")}
          </div>
          <div class="assessment-nav">
            <button class="btn btn-ghost" data-action="back" ${state.index === 0 ? "disabled" : ""}>Back</button>
            <button class="btn btn-primary" data-action="next" ${chosen ? "" : "disabled"}>${state.index === total - 1 ? "See my result" : "Next"}</button>
          </div>
        </div>`;
      container.querySelectorAll(".assessment-option").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.answers[q.id] = btn.dataset.option;
          paint();
        });
      });
      const back = container.querySelector('[data-action="back"]');
      if (back) back.addEventListener("click", () => {
        if (state.index > 0) { state.index -= 1; paint(); }
      });
      const next = container.querySelector('[data-action="next"]');
      if (next) next.addEventListener("click", async () => {
        if (!state.answers[q.id]) return;
        if (state.index < total - 1) {
          state.index += 1;
          paint();
        } else {
          await submit();
        }
      });
    }

    async function submit() {
      state.submitting = true;
      paint();
      try {
        const result = await api("/submit", { method: "POST", body: { answers: state.answers } });
        state.resultProfile = result.profile;
        state.profile = result.profile;
        state.step = "result";
        state.submitting = false;
        try { onComplete(result.profile, result.user); } catch (e) { /* ignore */ }
        paint();
      } catch (error) {
        state.submitting = false;
        state.error = error.message;
        paint();
      }
    }

    function renderResult() {
      const p = state.resultProfile || state.profile || {};
      const levelLabel = p.level_label || "Steady pace";
      const summary = Array.isArray(p.summary) ? p.summary : [];
      const actions = Array.isArray(p.coach_actions) ? p.coach_actions : [];
      const styleLabel = p.style_label || "";
      container.innerHTML = `
        <div class="assessment-result">
          <p class="assessment-eyebrow">You're set</p>
          <h1 class="assessment-title">${esc(levelLabel)}</h1>
          ${styleLabel ? `<p class="assessment-style">${esc(styleLabel)}</p>` : ""}
          <ul class="assessment-summary">
            ${summary.map((line) => `<li>${esc(line)}</li>`).join("")}
          </ul>
          ${actions.length ? `
            <div class="assessment-coach">
              <h3>What your coach will do</h3>
              <ul>
                ${actions.map((a) => `<li>${esc(a)}</li>`).join("")}
              </ul>
            </div>` : ""}
          <div class="assessment-actions">
            <button class="btn btn-primary btn-lg" data-action="start-studying">Start studying</button>
            <button class="btn btn-ghost" data-action="retake">Retake the check</button>
          </div>
        </div>`;
      container.querySelector('[data-action="start-studying"]').addEventListener("click", () => {
        window.location.hash = "#/dashboard";
      });
      container.querySelector('[data-action="retake"]').addEventListener("click", () => {
        state.step = "intro";
        state.resultProfile = null;
        state.answers = {};
        state.index = 0;
        paint();
      });
    }

    load();
  }

  window.Assessment = { mount };
})();
