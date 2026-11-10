/* Study Companion - dependency-free browser client */
(() => {
  "use strict";

  /* ---------------------------------------------------------------- icons */
  const ICON_PATHS = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.6"/><rect x="14" y="3" width="7" height="7" rx="1.6"/><rect x="14" y="14" width="7" height="7" rx="1.6"/><rect x="3" y="14" width="7" height="7" rx="1.6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    settings: '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6"/>',
    book: '<path d="M4 19.5V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v13.5"/><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M8 3v14"/>',
    map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>',
    check: '<path d="m4 12.5 5 5L20 6.5"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    chat: '<path d="M21 12a8.5 8.5 0 0 1-12.3 7.6L4 21l1.4-4.7A8.5 8.5 0 1 1 21 12z"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.6"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 20h16"/>',
    trash: '<path d="M3.5 6h17M9 6V3.6h6V6M18.5 6l-1 14h-11l-1-14"/>',
    logout: '<path d="M9.5 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4.5"/><path d="M16 16.5 20.5 12 16 7.5M20.5 12H9"/>',
    close: '<path d="M6 6 18 18M18 6 6 18"/>',
    doc: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    refresh: '<path d="M20.5 12a8.5 8.5 0 1 1-2.5-6"/><path d="M20.5 4v5h-5"/>',
    alert: '<path d="M12 8v5M12 16.5h.01"/><path d="M10.3 3.9 2.6 17.2A1.8 1.8 0 0 0 4.2 20h15.6a1.8 1.8 0 0 0 1.6-2.8L13.7 3.9a1.8 1.8 0 0 0-3.4 0z"/>',
    flame: '<path d="M12 3s5 4.5 5 9a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5 0 2 1 3 2 3.5C11.5 8.5 12 6 12 3z"/>',
    user: '<circle cx="12" cy="8" r="3.6"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    toolbox: '<rect x="3" y="7.5" width="18" height="12.5" rx="2"/><path d="M8.5 7.5V5.5a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v2M3 12.5h18M10 12.5v2.5h4v-2.5"/>',
  };

  const icon = (name, cls = "") =>
    `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;

  /* ---------------------------------------------------------------- state */
  const STORAGE_KEY = "study-companion.session";
  const TABS = [
    ["materials", "Materials"],
    ["topics", "Topic map"],
    ["plan", "Plan"],
    ["coach", "Coach"],
    ["progress", "Progress"],
  ];

  const state = {
    token: null,
    user: null,
    courses: [],
    tab: "materials",
    course: null,
    topics: [],
    tasks: [],
    documents: [],
    progress: null,
    chat: { sessionId: null, topicId: null, messages: [], hintLevel: 1, sending: false },
    loading: false,
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const view = () => $("#view");

  /* -------------------------------------------------------------- helpers */
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

  const fmtMinutes = (mins) => {
    const total = Math.max(0, Math.round(Number(mins) || 0));
    if (total < 60) return `${total}m`;
    const h = Math.floor(total / 60);
    const m = total % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  };

  const initials = (value) =>
    String(value || "Student")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0] || "")
      .join("")
      .toUpperCase();

  const parseDay = (iso) => {
    if (!iso) return null;
    const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  };

  const startOfToday = () => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  };

  const fmtDayLabel = (iso) => {
    const day = parseDay(iso);
    if (!day) return "No date";
    const today = startOfToday();
    const diff = Math.round((day - today) / 86400000);
    if (diff === 0) return "Today";
    if (diff === 1) return "Tomorrow";
    if (diff === -1) return "Yesterday";
    if (diff < -1) return `${Math.abs(diff)} days overdue`;
    return day.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  };

  const fmtBytes = (bytes) => {
    const size = Number(bytes) || 0;
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  };

  const pct = (value, max) => {
    if (!max) return 0;
    return Math.max(0, Math.min(100, Math.round((value / max) * 100)));
  };

  const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

  /* ------------------------------------------------------------------ api */
  async function api(path, options = {}) {
    const { method = "GET", body, form, auth = true } = options;
    const headers = {};
    if (auth && state.token) headers.Authorization = `Bearer ${state.token}`;

    let payload;
    if (form) {
      payload = form;
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }

    let response;
    try {
      response = await fetch(path, { method, headers, body: payload });
    } catch {
      throw new Error("Can't reach the server. Check your connection.");
    }

    if (response.status === 401 && auth) {
      signOut("Your session expired. Please sign in again.");
      throw new Error("Session expired.");
    }

    if (response.status === 204) return null;

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
      if (Array.isArray(detail)) detail = detail.map((item) => item.msg || item.message || "").join(", ");
      if (!detail) detail = `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return data;
  }

  /* --------------------------------------------------------------- toasts */
  function toast(message, kind = "info") {
    const root = $("#toasts");
    const node = document.createElement("div");
    node.className = `toast ${kind}`;
    const glyph = kind === "success" ? "check" : kind === "error" ? "alert" : "spark";
    node.innerHTML = `${icon(glyph)}<div>${esc(message)}</div>`;
    root.appendChild(node);
    setTimeout(() => {
      node.style.opacity = "0";
      node.style.transform = "translateY(6px)";
      setTimeout(() => node.remove(), 220);
    }, 4200);
  }

  /* --------------------------------------------------------------- modals */
  let activeModal = null;

  function openModal(html) {
    closeModal();
    const root = $("#modal-root");
    root.innerHTML = `<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true">${html}</div></div>`;
    const backdrop = $(".modal-backdrop", root);
    const close = () => closeModal();
    backdrop.addEventListener("mousedown", (event) => {
      if (event.target === backdrop) close();
    });
    $(".modal [data-close]", root)?.addEventListener("click", close);
    activeModal = { close };
    setTimeout(() => $(".modal input, .modal textarea, .modal select", root)?.focus(), 40);
    return { root, close };
  }

  function closeModal() {
    $("#modal-root").innerHTML = "";
    activeModal = null;
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activeModal) activeModal.close();
  });

  function openFeedback() {
    openModal(`
      <div class="modal-head">
        <h2>Send feedback</h2>
        <button class="icon-btn" data-close aria-label="Close">${icon("x")}</button>
      </div>
      <form id="feedback-form" class="form">
        <div class="field">
          <label for="feedback-rating">Rating (optional)</label>
          <select id="feedback-rating">
            <option value="">No rating</option>
            <option value="5">5 - Excellent</option>
            <option value="4">4 - Good</option>
            <option value="3">3 - Okay</option>
            <option value="2">2 - Needs work</option>
            <option value="1">1 - Poor</option>
          </select>
        </div>
        <div class="field">
          <label for="feedback-category">Category</label>
          <select id="feedback-category">
            <option value="general">General</option>
            <option value="bug">Bug</option>
            <option value="feature">Feature request</option>
            <option value="content">Course content</option>
          </select>
        </div>
        <div class="field">
          <label for="feedback-message">Message</label>
          <textarea id="feedback-message" rows="5" required placeholder="What worked, what did not, or what you would like next."></textarea>
        </div>
        <div class="modal-actions">
          <button type="button" class="btn btn-ghost" data-close>Cancel</button>
          <button type="submit" class="btn btn-primary">Send feedback</button>
        </div>
      </form>
    `);
    const form = $("#feedback-form");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = $("#feedback-message").value.trim();
      if (!message) return toast("Please enter a message.", "error");
      const ratingValue = $("#feedback-rating").value;
      const payload = {
        message,
        rating: ratingValue ? Number(ratingValue) : null,
        category: $("#feedback-category").value,
        course_id: state.course?.id || null,
        page: window.location.hash || null,
      };
      const submit = form.querySelector('button[type="submit"]');
      submit.disabled = true;
      submit.textContent = "Sending...";
      try {
        await api("/feedback", { method: "POST", body: payload });
        closeModal();
        toast("Thanks for your feedback!", "success");
      } catch (error) {
        toast(error.message || "Could not send feedback.", "error");
        submit.disabled = false;
        submit.textContent = "Send feedback";
      }
    });
  }

  /* -------------------------------------------------------- session state */
  function persist() {
    if (!state.token) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: state.token, user: state.user }));
  }

  function loadSession() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    } catch {
      return null;
    }
  }

  function signOut(message) {
    state.token = null;
    state.user = null;
    state.courses = [];
    state.course = null;
    state.chat = { sessionId: null, topicId: null, messages: [], hintLevel: 1, sending: false };
    persist();
    closeModal();
    window.location.hash = "";
    showAuth(message);
  }

  /* ------------------------------------------------------------- chrome */
  function closeNav() {
    $("#sidebar").classList.remove("open");
    document.body.classList.remove("nav-open");
    $("#menu-btn").setAttribute("aria-expanded", "false");
  }

  function showAuth(message) {
    $("#auth-view").hidden = false;
    $("#shell").hidden = true;
    document.title = "Study Companion";
    if (message) setAuthError(message);
  }

  function showShell() {
    $("#auth-view").hidden = true;
    $("#shell").hidden = false;
    renderChrome();
  }

  function renderChrome() {
    const user = state.user;
    if (!user) return;

    const current = parseRoute();
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.toggle("active", item.dataset.route === current.name);
    });

    const nav = $("#course-nav");
    nav.innerHTML = state.courses.length
      ? state.courses
          .map(
            (course) => `
        <button class="course-nav-item ${state.course && state.course.id === course.id ? "active" : ""}" data-action="open-course" data-id="${esc(course.id)}" title="${esc(course.title)}">
          <span class="course-initials">${esc(initials(course.code || course.title))}</span>
          <span class="course-nav-name">${esc(course.title)}</span>
        </button>`
          )
          .join("")
      : `<p class="small muted" style="padding:6px 10px;">No courses yet.</p>`;

    $("#user-chip").innerHTML = `
      <span class="avatar">${esc(initials(user.name))}</span>
      <span class="user-chip-text">
        <span class="user-chip-name">${esc(user.name)}</span>
        <span class="user-chip-role">${user.is_anonymous ? "Guest session" : esc(user.email || "Student")}</span>
      </span>`;
  }

  /* ------------------------------------------------------------ auth view */
  let authMode = "register";

  function setAuthError(message) {
    const node = $("#auth-error");
    if (!message) {
      node.hidden = true;
      node.textContent = "";
      return;
    }
    node.hidden = false;
    node.textContent = message;
  }

  function setAuthMode(mode) {
    authMode = mode;
    const register = mode === "register";
    $("#auth-name-field").hidden = !register;
    $("#auth-invite-field").hidden = !register;
    $("#auth-submit").textContent = register ? "Create account" : "Log in";
    $("#auth-toggle").textContent = register ? "Already have an account? Log in" : "New here? Create an account";
    $("#auth-password").setAttribute("autocomplete", register ? "new-password" : "current-password");
    setAuthError("");
  }

  async function startSession(data, onboarding = false) {
    state.token = data.access_token;
    state.user = data.user;
    persist();
    showShell();
    await loadCourses();
    if (onboarding && !(data.user && data.user.assessment_completed_at)) {
      window.location.hash = "#/assessment";
      return;
    }
    if (!location.hash) window.location.hash = "#/dashboard";
    else render();
  }

  $("#auth-toggle").addEventListener("click", () => setAuthMode(authMode === "register" ? "login" : "register"));

  $("#auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = $("#auth-submit");
    const email = $("#auth-email").value.trim();
    const password = $("#auth-password").value;
    const name = $("#auth-name").value.trim();

    if (!email || !password) return setAuthError("Email and password are required.");
    if (authMode === "register" && password.length < 8) return setAuthError("Use at least 8 characters for your password.");

    submit.disabled = true;
    submit.textContent = authMode === "register" ? "Creating account..." : "Logging in...";
    setAuthError("");
    try {
      const inviteCode = $("#auth-invite-code").value.trim();
    const payload =
      authMode === "register"
        ? { email, password, name: name || "Student", invite_code: inviteCode || undefined }
        : { email, password };
      const data = await api(`/auth/${authMode}`, { method: "POST", body: payload, auth: false });
      await startSession(data, authMode === "register");
    } catch (error) {
      setAuthError(error.message);
    } finally {
      submit.disabled = false;
      submit.textContent = authMode === "register" ? "Create account" : "Log in";
    }
  });

  $("#guest-btn").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Starting...";
    try {
      const data = await api("/auth/anonymous-session", { method: "POST", body: {}, auth: false });
      await startSession(data);
    } catch (error) {
      setAuthError(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Continue as a guest";
    }
  });

  /* ---------------------------------------------------------------- routes */
  function parseRoute() {
    const raw = location.hash.replace(/^#\/?/, "");
    const [name, id, tab] = raw.split("/");
    if (name === "course" && id) return { name: "course", id, tab: tab || "materials" };
    if (name === "settings") return { name: "settings" };
    if (name === "assessment") return { name: "assessment" };
    if (name === "toolbox") return { name: "toolbox", tab: id || "" };
    if (name === "resources") return { name: "resources", tab: id || "" };
    return { name: "dashboard" };
  }

  function navigate(hash) {
    if (location.hash === hash) render();
    else window.location.hash = hash;
  }

  window.addEventListener("hashchange", () => {
    if (!state.user) return;
    render();
  });

  async function loadCourses() {
    try {
      state.courses = await api("/documents/courses");
    } catch (error) {
      state.courses = [];
      toast(error.message, "error");
    }
    renderChrome();
  }

  /* ------------------------------------------------------------------ view */
  let renderToken = 0;

  async function render() {
    if (!state.user) return;
    const route = parseRoute();
    const token = ++renderToken;
    closeNav();

    try {
      if (route.name === "course") {
        await renderCourse(route, token);
      } else if (route.name === "settings") {
        state.course = null;
        state.tab = "materials";
        renderChrome();
        renderSettings();
      } else if (route.name === "assessment") {
        state.course = null;
        state.tab = "materials";
        renderChrome();
        renderAssessment();
      } else if (route.name === "toolbox") {
        state.course = null;
        state.tab = "materials";
        renderChrome();
        renderToolbox(route);
      } else if (route.name === "resources") {
        state.course = null;
        state.tab = "materials";
        renderChrome();
        renderResources(route);
      } else {
        state.course = null;
        state.tab = "materials";
        renderChrome();
        await renderDashboard(token);
      }
    } catch (error) {
      if (token !== renderToken) return;
      view().innerHTML = `
        <div class="empty">
          <div class="empty-icon">${icon("alert")}</div>
          <h3>Something went wrong</h3>
          <p>${esc(error.message)}</p>
          <button class="btn btn-ghost" data-action="reload">Try again</button>
        </div>`;
    }
  }

  /* -------------------------------------------------------------- dashboard */
  async function renderDashboard(token) {
    setTopbar("Today", `${icon("plus")} New course`, "new-course");
    view().innerHTML = skeletonPage();

    const [summary, todayTasks] = await Promise.all([
      api("/progress/summary").catch(() => null),
      api("/tasks/today?include_upcoming=true").catch(() => []),
    ]);
    if (token !== renderToken) return;

    const open = (todayTasks || []).filter((task) => task.status !== "done").slice(0, 6);
    const dueToday = open.filter((task) => {
      const day = parseDay(task.due_date);
      return day && day <= startOfToday();
    });
    const goal = summary ? summary.daily_goal_minutes : 60;
    const minutesToday = summary ? summary.minutes_today : 0;
    const readiness = summary && summary.courses.length
      ? Math.round(summary.courses.reduce((acc, c) => acc + c.readiness_score, 0) / summary.courses.length)
      : 0;

    const greeting = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening";
    const firstName = (state.user.name || "there").split(" ")[0];

    view().innerHTML = `
      <div class="page-head">
        <div>
          <h1>${esc(greeting)}, ${esc(firstName)}.</h1>
          <p class="sub">${summary && summary.courses.length ? "Pick up where you left off - short sessions beat long ones." : "Start by adding a course and uploading your first set of notes."}</p>
        </div>
      </div>

      <div class="stat-grid">
        ${statCard("Study time today", fmtMinutes(minutesToday), `Goal ${fmtMinutes(goal)}`, meter(minutesToday, goal), "clock")}
        ${statCard("Open tasks", String(summary ? summary.tasks_open : 0), `${summary ? summary.tasks_completed : 0} completed`, "", "list")}
        ${statCard("Streak", `${summary ? summary.streak_days : 0}<span>${(summary ? summary.streak_days : 0) === 1 ? "day" : "days"}</span>`, "Study on consecutive days", "", "flame")}
        ${statCard("Exam readiness", `${readiness}<span>%</span>`, summary && summary.courses.length ? `Across ${plural(summary.courses.length, "course")}` : "No material yet", meter(readiness, 100, "emerald"), "target")}
      </div>

      <div class="grid-2">
        <section class="card">
          <div class="card-head">
            <div>
              <h2>${dueToday.length || !open.length ? "Today's focus" : "Up next"}</h2>
              <p class="card-sub">${
                dueToday.length
                  ? `${plural(dueToday.length, "task")} due today or overdue`
                  : open.length
                    ? "Nothing due today - here is what's coming up"
                    : "Generate a plan for a course to fill this up."
              }</p>
            </div>
            <div class="card-head-actions">
              <button class="btn btn-quiet btn-sm" data-action="reload" title="Refresh">${icon("refresh")}</button>
            </div>
          </div>
          ${open.length ? `<div class="task-list">${open.map((task) => taskRow(task, { showCourse: true })).join("")}</div>` : emptyBlock("list", "No tasks yet", "Open a course, add material, then generate a study plan.")}
        </section>

        <section class="card">
          <div class="card-head">
            <div>
              <h2>Your courses</h2>
              <p class="card-sub">${state.courses.length ? plural(state.courses.length, "course") : "None yet"}</p>
            </div>
          </div>
          ${state.courses.length ? `<div class="stack">${state.courses.map((course) => courseMini(course)).join("")}</div>` : emptyBlock("book", "Add your first course", "A course groups your documents, topics and plan.", `<button class="btn btn-primary btn-sm" data-action="new-course">${icon("plus")} New course</button>`)}
        </section>
      </div>

      ${resourcesCard()}`;
  }

  /* --------------------------------------------------------------- toolbox */

  function renderAssessment() {
    setTopbar("Thinking check", "", "");
    const host = view();
    host.innerHTML = `<div id="assessment-host"></div>`;
    if (window.Assessment && typeof window.Assessment.mount === "function") {
      window.Assessment.mount($("#assessment-host"), {
        onComplete: async () => {
          try { state.user = await api("/auth/me"); } catch (e) { /* ignore */ }
          persist();
          renderChrome();
        },
      });
    } else {
      host.innerHTML = `<div class="empty"><h3>Assessment not loaded</h3></div>`;
    }
  }

  function renderToolbox(route) {
    setTopbar("Toolbox");
    view().innerHTML = `<div id="tb-host"></div>`;

    if (!window.Toolbox) {
      view().innerHTML = `
        <div class="empty">
          <div class="empty-icon">${icon("alert")}</div>
          <h3>The toolbox did not load</h3>
          <p>Reload the page to try again.</p>
          <button class="btn btn-ghost" data-action="reload">Reload</button>
        </div>`;
      return;
    }

    window.Toolbox.mount($("#tb-host"), { tab: route.tab, user: state.user });
  }

  /* ------------------------------------------------------------- resources */

  function renderResources(route) {
    setTopbar("Student Resources Centre");
    view().innerHTML = `<div id="rc-host"></div>`;

    if (!window.ResourcesCentre) {
      view().innerHTML = `
        <div class="empty">
          <div class="empty-icon">${icon("alert")}</div>
          <h3>The resources centre did not load</h3>
          <p>Reload the page to try again.</p>
          <button class="btn btn-ghost" data-action="reload">Reload</button>
        </div>`;
      return;
    }

    window.ResourcesCentre.mount($("#rc-host"), { tab: route.tab });
  }

  function resourcesCard() {
    const entries = [
      ["scholarships", "Scholarships", "Funding for tuition, living costs and tests."],
      ["thesis", "Thesis guide", "Ten stages from a blank page to a defended thesis."],
      ["path", "My career path", "Opportunities narrowed to your field and country."],
      ["library", "Library", "Guides and practice papers to read or download."],
    ];

    return `
      <section class="card">
        <div class="card-head">
          <div>
            <h2>Student Resources Centre</h2>
            <p class="card-sub">Scholarships, research routes, careers, jobs and a thesis-writing guide - all in the app.</p>
          </div>
          <div class="card-head-actions">
            <button class="btn btn-ghost btn-sm" data-action="open-resources">Open ${icon("arrow")}</button>
          </div>
        </div>
        <div class="stack">
          ${entries
            .map(
              (entry) => `<button class="course-nav-item" data-action="open-resources" data-tab="${entry[0]}" style="padding:10px 12px;">
                <span class="course-initials">${icon("book")}</span>
                <span class="user-chip-text">
                  <span class="user-chip-name">${esc(entry[1])}</span>
                  <span class="user-chip-role">${esc(entry[2])}</span>
                </span>
                <span class="spacer"></span>
                <span class="chip">Open</span>
              </button>`
            )
            .join("")}
        </div>
      </section>`;
  }

  function statCard(label, value, foot, meterHtml, glyph) {
    return `
      <div class="stat">
        <div class="stat-top">
          <span class="stat-label">${esc(label)}</span>
          <span class="stat-icon">${icon(glyph)}</span>
        </div>
        <div class="stat-value mono">${value}</div>
        <div class="stat-foot">${esc(foot)}</div>
        ${meterHtml ? `<div style="margin-top:8px;">${meterHtml}</div>` : ""}
      </div>`;
  }

  function meter(value, max, tone = "") {
    return `<div class="meter ${tone}"><span style="width:${pct(value, max)}%"></span></div>`;
  }

  function ring(value, size = "sm", tone = "linear-gradient(90deg,#8b7bff,#22d3ee)") {
    const radius = size === "lg" ? 46 : 28;
    const dim = size === "lg" ? 104 : 66;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference * (1 - Math.max(0, Math.min(100, value)) / 100);
    const stroke = size === "lg" ? 8 : 6;
    return `
      <div class="ring ${size === "lg" ? "ring-lg" : ""}">
        <svg width="${dim}" height="${dim}" viewBox="0 0 ${dim} ${dim}">
          <defs><linearGradient id="ring-${size}-${Math.round(value)}" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#8b7bff"/><stop offset="1" stop-color="#22d3ee"/>
          </linearGradient></defs>
          <circle cx="${dim / 2}" cy="${dim / 2}" r="${radius}" fill="none" stroke="rgba(148,163,184,0.18)" stroke-width="${stroke}"/>
          <circle cx="${dim / 2}" cy="${dim / 2}" r="${radius}" fill="none" stroke="url(#ring-${size}-${Math.round(value)})" stroke-width="${stroke}"
            stroke-linecap="round" stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"/>
        </svg>
        <div class="ring-label">${Math.round(value)}%</div>
      </div>`;
  }

  function courseMini(course) {
    return `
      <button class="course-nav-item" data-action="open-course" data-id="${esc(course.id)}" style="padding:10px 12px;">
        <span class="course-initials">${esc(initials(course.code || course.title))}</span>
        <span class="user-chip-text">
          <span class="user-chip-name">${esc(course.title)}</span>
          <span class="user-chip-role">${plural(course.topic_count, "topic")} · ${plural(course.completed_task_count, "task")} done</span>
        </span>
        <span class="spacer"></span>
        <span class="chip">${course.readiness_score}%</span>
      </button>`;
  }

  function emptyBlock(glyph, title, text, extra = "") {
    return `
      <div class="empty">
        <div class="empty-icon">${icon(glyph)}</div>
        <h3>${esc(title)}</h3>
        <p>${esc(text)}</p>
        ${extra}
      </div>`;
  }

  function skeletonPage() {
    return `
      <div class="skeleton skeleton-line" style="width:38%;height:26px;margin-bottom:22px;"></div>
      <div class="stat-grid">${Array.from({ length: 4 }, () => '<div class="stat"><div class="skeleton skeleton-line" style="width:60%"></div><div class="skeleton skeleton-line" style="width:35%;height:24px"></div><div class="skeleton skeleton-line" style="width:75%"></div></div>').join("")}</div>
      <div class="grid-2">
        <div class="card"><div class="skeleton skeleton-line" style="width:40%"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line" style="width:70%"></div></div>
        <div class="card"><div class="skeleton skeleton-line" style="width:40%"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line" style="width:80%"></div></div>
      </div>`;
  }

  /* ----------------------------------------------------------------- course */
  async function renderCourse(route, token) {
    if (!state.course || state.course.id !== route.id) {
      state.course = await api(`/documents/courses/${route.id}`);
      state.chat = { sessionId: null, topicId: null, messages: [], hintLevel: 1, sending: false };
      state.topics = [];
      state.tasks = [];
      state.documents = [];
      state.progress = null;
    }
    if (TABS.some(([key]) => key === route.tab)) state.tab = route.tab;
    if (token !== renderToken) return;
    renderChrome();

    const course = state.course;
    const [topics, documents] = await Promise.all([
      api(`/documents/courses/${course.id}/topics`).catch(() => []),
      api(`/documents/courses/${course.id}/documents`).catch(() => []),
    ]);
    if (token !== renderToken) return;
    state.topics = topics || [];
    state.documents = documents || [];

    let tasks = [];
    if (["plan", "coach", "progress", "materials"].includes(state.tab)) {
      tasks = await api(`/tasks/courses/${course.id}`).catch(() => []);
      if (token !== renderToken) return;
      state.tasks = tasks || [];
    }

    setTopbar(
      `<button class="link" data-action="go-dashboard" style="color:var(--muted)">Today</button> <span aria-hidden="true">/</span> <strong>${esc(course.title)}</strong>`,
      `${icon("upload")} Add material`,
      "add-material"
    );

    const openTasks = state.tasks.filter((task) => task.status !== "done").length;
    const examChip = course.exam_date
      ? course.days_until_exam >= 0
        ? `<span class="chip ${course.days_until_exam <= 14 ? "chip-amber" : ""}">${icon("clock")} ${course.days_until_exam === 0 ? "Exam today" : `Exam in ${course.days_until_exam} days`}</span>`
        : `<span class="chip chip-rose">${icon("clock")} Exam passed</span>`
      : "";

    view().innerHTML = `
      <div class="page-head">
        <div>
          <div class="row" style="gap:8px;margin-bottom:6px;">
            <span class="chip chip-violet">${icon("book")} ${esc(course.code || "Course")}</span>
            ${examChip}
            ${openTasks ? `<span class="chip">${openTasks} open</span>` : ""}
          </div>
          <h1>${esc(course.title)}</h1>
          <p class="sub">${esc(course.subject || "Add material and the coach will map your topics.")}</p>
        </div>
        <div class="page-head-actions">
          ${ring(course.readiness_score)}
          <button class="icon-btn" data-action="edit-course" title="Edit or delete this course" aria-label="Edit or delete this course">${icon("settings")}</button>
          <button class="btn btn-ghost" data-action="gen-plan">${icon("spark")} Generate plan</button>
          <button class="btn btn-primary" data-action="add-material">${icon("upload")} Add material</button>
        </div>
      </div>

      <div class="tabs" role="tablist">
        ${TABS.map(([key, label]) => {
          const count = key === "plan" ? (state.tasks.length ? ` (${state.tasks.length})` : "") : key === "topics" ? (state.topics.length ? ` (${state.topics.length})` : "") : key === "materials" ? (state.documents.length ? ` (${state.documents.length})` : "") : "";
          return `<button class="tab ${state.tab === key ? "active" : ""}" role="tab" data-action="tab" data-tab="${key}">${label}${count}</button>`;
        }).join("")}
      </div>

      <div id="tab-panel">${tabContent()}</div>`;

    // Keep the active tab visible when the bar overflows on a phone. Scroll the
    // minimum needed: centring it left the neighbouring tab half cut off.
    const activeTab = view().querySelector(".tab.active");
    if (activeTab) {
      const bar = activeTab.parentElement;
      const barRect = bar.getBoundingClientRect();
      const tabRect = activeTab.getBoundingClientRect();
      if (tabRect.right > barRect.right || tabRect.left < barRect.left) {
        bar.scrollLeft += tabRect.left - barRect.left - 8;
      }
    }

    if (state.tab === "coach") await initChat(token);
    if (state.tab === "progress") await loadProgress(token);
  }

  function tabContent() {
    switch (state.tab) {
      case "topics":
        return topicsPanel();
      case "plan":
        return planPanel();
      case "coach":
        return coachPanel();
      case "progress":
        return progressPanel();
      default:
        return materialsPanel();
    }
  }

  /* -------------------------------------------------------------- materials */
  function materialsPanel() {
    const course = state.course;
    return `
      <div class="grid-2">
        <section class="card">
          <div class="card-head">
            <div>
              <h2>Add study material</h2>
              <p class="card-sub">PDF, DOCX, PPTX, TXT, Markdown, HTML or images. Up to 50 MB.</p>
            </div>
          </div>
          <div class="dropzone" data-action="pick-file">
            ${icon("upload")}
            <div class="dropzone-title">Drop a file here or click to browse</div>
            <div class="dropzone-sub">Lecture slides, readings, your own notes</div>
            <input type="file" id="file-input" accept=".pdf,.docx,.pptx,.txt,.md,.markdown,.csv,.html,.htm,.png,.jpg,.jpeg,.webp" />
          </div>
          <div class="row" style="margin-top:12px;">
            <span class="small muted">No file handy?</span>
            <button class="btn btn-ghost btn-sm" data-action="paste-notes">Paste notes instead</button>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <div>
              <h2>What happens next</h2>
              <p class="card-sub">Everything is derived from your own material.</p>
            </div>
          </div>
          <ol class="auth-points" style="margin:0;gap:14px;">
            <li><strong>Text is extracted and chunked</strong><span>So the coach can quote the right passage.</span></li>
            <li><strong>Topics are mapped</strong><span>${state.topics.length ? `${plural(state.topics.length, "topic")} found in this course.` : "Headings first, then keywords."}</span></li>
            <li><strong>You get a plan</strong><span>Spread across days around your study goal.</span></li>
          </ol>
        </section>
      </div>

      <section class="card" style="margin-top:18px;">
        <div class="card-head">
          <div>
            <h2>Documents</h2>
            <p class="card-sub">${state.documents.length ? plural(state.documents.length, "document") : "Nothing uploaded yet"}</p>
          </div>
          <div class="card-head-actions">
            <button class="btn btn-quiet btn-sm" data-action="rebuild-topics" title="Recompute the topic map">${icon("refresh")} Rebuild topics</button>
          </div>
        </div>
        ${
          state.documents.length
            ? `<div class="doc-list">${state.documents.map(documentRow).join("")}</div>`
            : emptyBlock("doc", "No documents yet", `Upload a lecture or paste your notes to build the topic map for ${course.title}.`)
        }
      </section>`;
  }

  function documentRow(document) {
    const failed = document.status === "failed";
    const warnings = (document.extraction_warnings || []).join(" ");
    return `
      <div class="doc-row">
        <span class="doc-icon">${icon("doc")}</span>
        <div class="doc-body">
          <span class="doc-name" title="${esc(document.filename)}">${esc(document.filename)}</span>
          <span class="doc-meta">
            ${failed ? `<span class="badge-failed">Failed</span>` : `<span>${plural(document.word_count, "word")}</span>`}
            ${document.page_count ? `<span>${plural(document.page_count, "page")}</span>` : ""}
            <span>${fmtBytes(document.size_bytes)}</span>
          </span>
          ${failed && document.error_message ? `<div class="doc-warning">${esc(document.error_message)}</div>` : ""}
          ${!failed && warnings ? `<div class="doc-warning">${esc(warnings)}</div>` : ""}
        </div>
        <button class="icon-btn small" data-action="delete-document" data-id="${esc(document.id)}" title="Remove document">${icon("trash")}</button>
      </div>`;
  }

  /* ----------------------------------------------------------------- topics */
  function topicsPanel() {
    if (!state.topics.length) {
      return emptyBlock(
        "map",
        "No topic map yet",
        "Add a document and Study Companion will pull out the topics, key terms and difficulty.",
        `<button class="btn btn-primary btn-sm" data-action="add-material">${icon("upload")} Add material</button>`
      );
    }
    const totalWeight = state.topics.reduce((acc, topic) => acc + (topic.weight || 0), 0) || 1;
    return `
      <div class="row" style="margin-bottom:16px;">
        <p class="small muted">${plural(state.topics.length, "topic")} mapped from ${plural(state.documents.length, "document")}. Ask the coach about any of them.</p>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" data-action="gen-plan">${icon("spark")} Turn into a plan</button>
      </div>
      <div class="topic-grid">
        ${state.topics
          .map(
            (topic) => `
          <article class="topic-card">
            <div class="topic-card-top">
              <div style="flex:1;min-width:0;">
                <h3>${esc(topic.title)}</h3>
                <div class="difficulty" title="Difficulty ${topic.difficulty}/5">
                  ${[1, 2, 3, 4, 5].map((level) => `<i class="${level <= topic.difficulty ? `on ${topic.difficulty >= 4 ? "high" : ""}` : ""}"></i>`).join("")}
                  <span class="tiny muted" style="margin-left:6px;">${Math.round(((topic.weight || 0) / totalWeight) * 100)}% of material</span>
                </div>
              </div>
            </div>
            <p class="topic-summary">${esc(topic.summary || "No summary extracted - open the source document.")}</p>
            ${topic.keywords.length ? `<div class="keywords">${topic.keywords.slice(0, 6).map((word) => `<span class="keyword">${esc(word)}</span>`).join("")}</div>` : ""}
            <div class="topic-foot">
              <span class="confidence" title="Confidence ${topic.confidence}/5">${[1, 2, 3, 4, 5].map((level) => `<i class="${level <= topic.confidence ? "on" : ""}"></i>`).join("")}</span>
              <span class="tiny">${topic.chunk_count ? plural(topic.chunk_count, "passage") : "No passages"}</span>
              <span class="spacer"></span>
              <button class="btn btn-quiet btn-sm" data-action="ask-topic" data-id="${esc(topic.id)}">Ask coach ${icon("arrow")}</button>
            </div>
          </article>`
          )
          .join("")}
      </div>`;
  }

  /* ------------------------------------------------------------------- plan */
  function planPanel() {
    if (!state.tasks.length) {
      return emptyBlock(
        "list",
        "No study plan yet",
        "Generate a plan and it spreads reading, practice and self-testing across the days before your exam.",
        `<button class="btn btn-primary btn-sm" data-action="gen-plan">${icon("spark")} Generate plan</button>`
      );
    }

    const groups = new Map();
    state.tasks.forEach((task) => {
      const key = task.due_date || "none";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(task);
    });
    const keys = [...groups.keys()].sort((a, b) => {
      if (a === "none") return 1;
      if (b === "none") return -1;
      return a.localeCompare(b);
    });

    const open = state.tasks.filter((task) => task.status !== "done");
    const done = state.tasks.length - open.length;
    const totalMinutes = open.reduce((acc, task) => acc + task.estimated_minutes, 0);

    return `
      <div class="stat-grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));">
        ${statCard("Plan progress", `${pct(done, state.tasks.length)}<span>%</span>`, `${done} of ${plural(state.tasks.length, "task")} done`, meter(done, state.tasks.length, "emerald"), "check")}
        ${statCard("Remaining", fmtMinutes(totalMinutes), "Estimated work left", "", "clock")}
        ${statCard("Daily goal", fmtMinutes(state.user.daily_study_minutes), "Adjust in settings", "", "target")}
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <h2>Your plan</h2>
            <p class="card-sub">Check off what you finish - that is what drives your readiness score.</p>
          </div>
          <div class="card-head-actions">
            <button class="btn btn-ghost btn-sm" data-action="gen-plan">${icon("spark")} Regenerate</button>
          </div>
        </div>
        ${keys
          .map((key) => {
            const tasks = groups.get(key);
            const isOverdue = key !== "none" && parseDay(key) && parseDay(key) < startOfToday() && tasks.some((task) => task.status !== "done");
            return `
              <div class="day-group">
                <div class="day-head">
                  <strong>${key === "none" ? "No date" : fmtDayLabel(key)}</strong>
                  <span>${plural(tasks.length, "task")}</span>
                  ${isOverdue ? `<span class="chip chip-rose">overdue</span>` : ""}
                </div>
                <div class="task-list">${tasks.map((task) => taskRow(task, { showCourse: false })).join("")}</div>
              </div>`;
          })
          .join("")}
      </div>`;
  }

  function taskRow(task, options = {}) {
    const course = state.courses.find((item) => item.id === task.course_id);
    return `
      <div class="task ${task.status === "done" ? "is-done" : ""}" data-task-id="${esc(task.id)}">
        <button class="task-check" data-action="toggle-task" data-id="${esc(task.id)}" title="${task.status === "done" ? "Mark as not done" : "Mark as done"}">${icon("check")}</button>
        <div class="task-body">
          <button class="task-title" data-action="open-task" data-id="${esc(task.id)}" style="background:none;border:0;color:inherit;text-align:left;padding:0;cursor:pointer;">${esc(task.title)}</button>
          <div class="task-meta">
            <span class="task-type ${esc(task.task_type)}">${esc(task.task_type)}</span>
            <span>${icon("clock")} ${fmtMinutes(task.estimated_minutes)}</span>
            ${options.showCourse && course ? `<span>${esc(course.title)}</span>` : ""}
            ${task.due_date ? `<span>${esc(fmtDayLabel(task.due_date))}</span>` : ""}
          </div>
        </div>
        <div class="task-actions">
          <button class="icon-btn small" data-action="delete-task" data-id="${esc(task.id)}" title="Remove task">${icon("trash")}</button>
        </div>
      </div>`;
  }

  /* ------------------------------------------------------------------ coach */
  function coachPanel() {
    const hints = [
      [1, "Nudge"],
      [2, "Clue"],
      [3, "Walk through"],
    ];
    return `
      <div class="card">
        <div class="card-head">
          <div>
            <h2>Study coach</h2>
            <p class="card-sub">Grounded in your material${state.topics.length ? ` · ${plural(state.topics.length, "topic")} in scope` : ""}</p>
          </div>
          <div class="card-head-actions">
            <button class="btn btn-quiet btn-sm" data-action="new-chat" title="Start a new conversation">${icon("refresh")} New chat</button>
          </div>
        </div>

        <div class="chat-shell">
          <div class="chat-thread" id="chat-thread"></div>
          <div class="composer">
            <div class="row" style="gap:10px;">
              <span class="small muted">How much help?</span>
              <div class="segmented" id="hint-picker">
                ${hints.map(([level, label]) => `<button data-action="hint-level" data-level="${level}" class="${state.chat.hintLevel === level ? "active" : ""}">${label}</button>`).join("")}
              </div>
              <span class="spacer"></span>
              <span class="tiny muted">${state.chat.hintLevel === 1 ? "Questions only" : state.chat.hintLevel === 2 ? "Clue + passage" : "Full walkthrough"}</span>
            </div>
            <div class="suggestions" id="chat-suggestions">
              ${["Explain this topic", "Quiz me on this", "What should I study today?", "Summarise the material"]
                .map((text) => `<button class="suggestion" data-action="suggestion" data-prompt="${esc(text)}">${esc(text)}</button>`)
                .join("")}
            </div>
            <form class="composer-row" id="chat-form">
              <textarea id="chat-input" rows="1" placeholder="Ask about your material, or ask to be quizzed..."></textarea>
              <button class="btn btn-primary" type="submit" id="chat-send" title="Send">${icon("arrow")}</button>
            </form>
          </div>
        </div>
      </div>`;
  }

  function messageNode(message) {
    const isUser = message.role === "user";
    const meta = message.meta || {};
    const citations = (meta.citations || []).slice(0, 3);
    return `
      <div class="msg ${isUser ? "msg-user" : "msg-assistant"}">
        <span class="msg-avatar">${isUser ? esc(initials(state.user.name)) : "SC"}</span>
        <div>
          <div class="bubble">${md(message.content)}</div>
          ${
            !isUser && (citations.length || meta.source)
              ? `<div class="msg-meta">${citations.map((cite) => `<span class="citation">${esc(cite)}</span>`).join("")}${
                  meta.source === "rules" ? `<span class="tiny muted">offline coach</span>` : ""
                }</div>`
              : ""
          }
        </div>
      </div>`;
  }

  async function initChat(token) {
    const thread = $("#chat-thread");
    if (!thread) return;

    if (!state.chat.sessionId) {
      try {
        const existing = await api(`/chat/courses/${state.course.id}/sessions`);
        if (token !== renderToken) return;
        if (existing && existing.length) {
          state.chat.sessionId = existing[0].id;
        } else {
          const created = await api(`/chat/courses/${state.course.id}/sessions`, {
            method: "POST",
            body: state.chat.topicId ? { topic_id: state.chat.topicId } : {},
          });
          if (token !== renderToken) return;
          state.chat.sessionId = created.id;
        }
      } catch (error) {
        thread.innerHTML = `<p class="small muted">${esc(error.message)}</p>`;
        return;
      }
    }

    try {
      const detail = await api(`/chat/sessions/${state.chat.sessionId}`);
      if (token !== renderToken) return;
      state.chat.messages = detail.messages || [];
    } catch {
      state.chat.messages = [];
    }
    paintThread();
  }

  function paintThread() {
    const thread = $("#chat-thread");
    if (!thread) return;
    const messages = state.chat.messages;
    if (!messages.length && !state.chat.sending) {
      thread.innerHTML = `
        <div class="empty" style="border:0;background:none;padding:26px 12px;">
          <div class="empty-icon">${icon("chat")}</div>
          <h3>Ask me about your material</h3>
          <p>I quote your own documents and only give as much help as you ask for. Pick a hint level, then ask.</p>
        </div>`;
      return;
    }
    thread.innerHTML =
      messages.map(messageNode).join("") +
      (state.chat.sending
        ? `<div class="msg msg-assistant"><span class="msg-avatar">SC</span><div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div></div>`
        : "");
    scrollThreadToLatest(thread);
  }

  function scrollThreadToLatest(thread) {
    // Desktop keeps the thread as its own scroll area; on a phone the thread
    // grows with the page, so bring the newest message and the input into view
    // instead of setting a scrollTop that has nothing to scroll.
    if (thread.scrollHeight > thread.clientHeight + 8) {
      thread.scrollTop = thread.scrollHeight;
      return;
    }
    if (!window.matchMedia("(max-width: 900px)").matches) return;
    const composer = $("#chat-form");
    if (composer) composer.scrollIntoView({ block: "nearest" });
  }

  async function sendChat(prompt) {
    const input = $("#chat-input");
    const text = (prompt ?? input?.value ?? "").trim();
    if (!text || state.chat.sending || !state.chat.sessionId) return;
    if (input && prompt === undefined) input.value = "";

    state.chat.sending = true;
    state.chat.messages.push({ role: "user", content: text, hint_level: state.chat.hintLevel });
    paintThread();

    try {
      const result = await api(`/chat/sessions/${state.chat.sessionId}/messages`, {
        method: "POST",
        body: { message: text, hint_level: state.chat.hintLevel },
      });
      state.chat.messages[state.chat.messages.length - 1] = result.user_message;
      state.chat.messages.push({ ...result.reply, meta: { source: result.source, citations: result.citations } });
    } catch (error) {
      toast(error.message, "error");
      state.chat.messages.pop();
    } finally {
      state.chat.sending = false;
      paintThread();
    }
    void state.course;
  }

  /* --------------------------------------------------------------- progress */
  async function loadProgress(token) {
    const panel = $("#tab-panel");
    if (!panel) return;
    panel.innerHTML = `<div class="card"><div class="skeleton skeleton-line" style="width:35%"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line" style="width:70%"></div></div>`;
    try {
      const progress = await api(`/progress/courses/${state.course.id}`);
      if (token !== renderToken) return;
      state.progress = progress;
      panel.innerHTML = progressPanel();
    } catch (error) {
      panel.innerHTML = `<div class="card"><p class="small muted">${esc(error.message)}</p></div>`;
    }
  }

  function progressPanel() {
    const progress = state.progress;
    if (!progress) {
      return `<div class="card">${emptyBlock("chart", "Loading progress", "Crunching your study log.")}</div>`;
    }
    const topics = [...(progress.topics || [])].sort((a, b) => b.confidence - a.confidence || a.difficulty - b.difficulty);
    return `
      <div class="grid-2">
        <section class="card">
          <div class="card-head"><div><h2>Exam readiness</h2><p class="card-sub">Coverage of topics × completed tasks</p></div></div>
          <div class="row" style="gap:22px;">
            ${ring(progress.readiness_score, "lg")}
            <div class="stack" style="gap:10px;flex:1;">
              <div>
                <div class="row" style="justify-content:space-between;"><span class="small dim">Tasks completed</span><span class="small mono">${progress.completed_tasks}/${progress.total_tasks}</span></div>
                ${meter(progress.completed_tasks, progress.total_tasks || 1, "emerald")}
              </div>
              <div>
                <div class="row" style="justify-content:space-between;"><span class="small dim">Topics with practice</span><span class="small mono">${topics.filter((topic) => topic.confidence > 0).length}/${topics.length}</span></div>
                ${meter(topics.filter((topic) => topic.confidence > 0).length, topics.length || 1)}
              </div>
              <div class="row" style="gap:16px;">
                <span class="chip">${icon("clock")} ${fmtMinutes(progress.minutes_studied)} studied</span>
                <span class="chip">${icon("flame")} ${plural(progress.streak_days, "day")} streak</span>
              </div>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-head"><div><h2>How to raise it</h2><p class="card-sub">Readiness moves when you complete tasks per topic.</p></div></div>
          <ol class="auth-points" style="margin:0;gap:12px;">
            <li><strong>Finish one task per topic</strong><span>Every topic needs at least one completed task to count as covered.</span></li>
            <li><strong>Use the quiz tasks</strong><span>Retrieval practice is weighted the same as reading, but it sticks better.</span></li>
            <li><strong>Spread it out</strong><span>Short sessions on consecutive days build your streak.</span></li>
          </ol>
        </section>
      </div>

      <section class="card" style="margin-top:18px;">
        <div class="card-head"><div><h2>Topic mastery</h2><p class="card-sub">Confidence grows each time you complete a task on a topic</p></div></div>
        ${
          topics.length
            ? `<div class="doc-list">${topics
                .map(
                  (topic) => `
              <div class="doc-row">
                <span class="doc-icon">${icon("map")}</span>
                <div class="doc-body">
                  <span class="doc-name">${esc(topic.title)}</span>
                  <span class="doc-meta">${plural(topic.completed_task_count, "task")} of ${topic.task_count} done · difficulty ${topic.difficulty}/5</span>
                </div>
                <span class="confidence" title="Confidence ${topic.confidence}/5" style="margin-right:8px;">${[1, 2, 3, 4, 5].map((level) => `<i class="${level <= topic.confidence ? "on" : ""}"></i>`).join("")}</span>
              </div>`
                )
                .join("")}</div>`
            : emptyBlock("map", "No topics yet", "Add a document to see per-topic mastery.")
        }
      </section>`;
  }

  /* --------------------------------------------------------------- settings */
  function renderSettings() {
    setTopbar("Settings", "", null);
    const user = state.user;
    view().innerHTML = `
      <div class="page-head">
        <div>
          <h1>Settings</h1>
          <p class="sub">Your study goal shapes the plans Study Companion builds.</p>
        </div>
      </div>

      <div class="grid-2">
        <section class="card">
          <div class="card-head"><div><h2>Profile</h2><p class="card-sub">${user.is_anonymous ? "Guest session - no account attached" : esc(user.email)}</p></div></div>
          <form id="profile-form" class="auth-form">
            <div class="field">
              <label for="profile-name">Name</label>
              <input id="profile-name" type="text" value="${esc(user.name)}" maxlength="120" />
            </div>
            <div class="field">
              <label for="profile-university">University</label>
              <input id="profile-university" type="text" value="${esc(user.university || "")}" placeholder="Optional" maxlength="200" />
            </div>
            <div class="field">
              <label for="profile-profession">Profession or field of study</label>
              <input id="profile-profession" type="text" value="${esc(user.profession || "")}" placeholder="e.g. Software Engineer" maxlength="120" />
              <span class="small muted">The Toolbox agents tailor CVs and letters to this.</span>
            </div>
            <div class="field">
              <label for="profile-minutes">Daily study goal (minutes)</label>
              <input id="profile-minutes" type="number" min="15" max="480" step="5" value="${user.daily_study_minutes}" />
            </div>
            <button class="btn btn-primary" type="submit" id="profile-save">Save changes</button>
          </form>
        </section>

        <section class="card">
          <div class="card-head"><div><h2>Account</h2><p class="card-sub">${user.is_anonymous ? "Guest" : "Signed in"} · ${esc(user.subscription_tier)} plan</p></div></div>
          <div class="stack" style="gap:12px;">
            <div class="doc-row" style="border:0;background:none;padding:0;">
              <span class="avatar" style="width:38px;height:38px;">${esc(initials(user.name))}</span>
              <div class="doc-body">
                <span class="doc-name">${esc(user.name)}</span>
                <span class="doc-meta">${user.is_anonymous ? "Guest session - stored in this browser" : esc(user.email)}</span>
              </div>
            </div>
            <p class="small muted">${
              user.is_anonymous
                ? "You are studying as a guest. Create an account from the sign-out screen to keep work across devices."
                : "Your courses, documents and progress are tied to this account."
            }</p>
            <button class="btn btn-danger" data-action="signout">${icon("logout")} Sign out</button>
          </div>
        </section>
      </div>

      <section class="card" style="margin-top:16px;">
        <div class="card-head"><div><h2>Thinking check</h2><p class="card-sub">Helps the coach fit how it explains things to you.</p></div></div>
        <div class="stack" style="gap:10px;">
          ${user.thinking_level ? `
            <p class="small">Your result: <strong>${esc((user.thinking_scores && user.thinking_scores.level_label) || user.thinking_level)}</strong></p>
            <p class="small muted">${esc((user.thinking_scores && (user.thinking_scores.summary || []).join(" ")) || "")}</p>
          ` : `<p class="small muted">You have not taken the check yet.</p>`}
          <button class="btn btn-ghost btn-sm" data-action="retake-assessment">${icon("refresh")} ${user.thinking_level ? "Retake the check" : "Take the check"}</button>
        </div>
      </section>`;

    $("#profile-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = $("#profile-save");
      button.disabled = true;
      try {
        const updated = await api("/auth/me", {
          method: "PATCH",
          body: {
            name: $("#profile-name").value.trim() || "Student",
            university: $("#profile-university").value.trim(),
            profession: $("#profile-profession").value.trim(),
            daily_study_minutes: Number($("#profile-minutes").value) || 60,
          },
        });
        state.user = updated;
        persist();
        renderChrome();
        toast("Profile updated.", "success");
      } catch (error) {
        toast(error.message, "error");
      } finally {
        button.disabled = false;
      }
    });
  }

  /* ----------------------------------------------------------------- modals */
  function setTopbar(titleHtml, actionHtml, action) {
    $("#topbar-title").innerHTML = titleHtml;
    const actions = $("#topbar-actions");
    if (actionHtml && action) {
      actions.innerHTML = `<button class="btn btn-primary btn-sm" data-action="${action}">${actionHtml}</button>`;
    } else {
      actions.innerHTML = "";
    }
  }

  function openNewCourse() {
    openModal(`
      <h2>New course</h2>
      <p class="modal-sub">Group the documents that belong to one subject or module.</p>
      <form id="course-form">
        <div class="modal-body">
          <div class="field">
            <label for="course-title">Course title</label>
            <input id="course-title" required placeholder="e.g. Cell Biology" maxlength="200" />
          </div>
          <div class="form-row">
            <div class="field"><label for="course-code">Code</label><input id="course-code" placeholder="BIO101" maxlength="60" /></div>
            <div class="field"><label for="course-exam">Exam date</label><input id="course-exam" type="date" /></div>
          </div>
          <div class="field"><label for="course-subject">Subject</label><input id="course-subject" placeholder="Biology" maxlength="120" /></div>
          <p class="form-error" id="course-error" hidden></p>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" data-close>Cancel</button>
          <button type="submit" class="btn btn-primary" id="course-submit">Create course</button>
        </div>
      </form>`);

    $("#course-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const title = $("#course-title").value.trim();
      if (title.length < 2) {
        const error = $("#course-error");
        error.hidden = false;
        error.textContent = "Give the course a title.";
        return;
      }
      const button = $("#course-submit");
      button.disabled = true;
      button.textContent = "Creating...";
      try {
        const course = await api("/documents/courses", {
          method: "POST",
          body: {
            title,
            code: $("#course-code").value.trim() || null,
            subject: $("#course-subject").value.trim() || null,
            exam_date: $("#course-exam").value || null,
          },
        });
        closeModal();
        await loadCourses();
        navigate(`#/course/${course.id}`);
        toast("Course created. Add your first document.", "success");
      } catch (error) {
        const errorNode = $("#course-error");
        errorNode.hidden = false;
        errorNode.textContent = error.message;
        button.disabled = false;
        button.textContent = "Create course";
      }
    });
  }

  function openEditCourse() {
    const course = state.course;
    if (!course) return;
    openModal(`
      <h2>Edit course</h2>
      <p class="modal-sub">Rename the course, fix the code or change the exam date.</p>
      <form id="course-edit-form">
        <div class="modal-body">
          <div class="field">
            <label for="edit-title">Course title</label>
            <input id="edit-title" required maxlength="200" value="${esc(course.title)}" />
          </div>
          <div class="form-row">
            <div class="field"><label for="edit-code">Code</label><input id="edit-code" maxlength="60" value="${esc(course.code || "")}" placeholder="BIO101" /></div>
            <div class="field"><label for="edit-exam">Exam date</label><input id="edit-exam" type="date" value="${course.exam_date || ""}" /></div>
          </div>
          <div class="field"><label for="edit-subject">Subject</label><input id="edit-subject" maxlength="120" value="${esc(course.subject || "")}" placeholder="Biology" /></div>
          <div class="field"><label for="edit-description">Notes</label><textarea id="edit-description" maxlength="4000" style="min-height:80px;" placeholder="What this course covers, or how you want to study it">${esc(course.description || "")}</textarea></div>
          <p class="form-error" id="edit-error" hidden></p>
        </div>
        <div class="modal-foot" style="justify-content:space-between;">
          <button type="button" class="btn btn-danger" data-action="delete-course">${icon("trash")} Delete course</button>
          <div class="row" style="gap:8px;">
            <button type="button" class="btn btn-ghost" data-close>Cancel</button>
            <button type="submit" class="btn btn-primary" id="edit-submit">Save changes</button>
          </div>
        </div>
      </form>`);

    $("#course-edit-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const title = $("#edit-title").value.trim();
      if (title.length < 2) {
        const error = $("#edit-error");
        error.hidden = false;
        error.textContent = "Give the course a title.";
        return;
      }
      const button = $("#edit-submit");
      button.disabled = true;
      button.textContent = "Saving...";
      try {
        const updated = await api(`/documents/courses/${course.id}`, {
          method: "PATCH",
          body: {
            title,
            code: $("#edit-code").value.trim() || null,
            subject: $("#edit-subject").value.trim() || null,
            description: $("#edit-description").value.trim() || null,
            exam_date: $("#edit-exam").value || null,
          },
        });
        state.course = updated;
        closeModal();
        await loadCourses();
        render();
        toast("Course updated.", "success");
      } catch (error) {
        const errorNode = $("#edit-error");
        errorNode.hidden = false;
        errorNode.textContent = error.message;
        button.disabled = false;
        button.textContent = "Save changes";
      }
    });
  }

  function deleteCourse() {
    const course = state.course;
    if (!course) return;
    confirmDialog(
      `Delete "${course.title}"?`,
      "This removes the course, its documents, topic map, plan and chat history. This cannot be undone.",
      "Delete course",
      async () => {
        try {
          await api(`/documents/courses/${course.id}`, { method: "DELETE" });
          state.course = null;
          state.topics = [];
          state.tasks = [];
          state.documents = [];
          await loadCourses();
          navigate("#/dashboard");
          toast("Course deleted.", "info");
        } catch (error) {
          toast(error.message, "error");
        }
      },
      true
    );
  }

  function openAddMaterial() {
    if (!state.course) {
      toast("Open a course first, then add material.", "error");
      return;
    }
    openModal(`
      <h2>Add material</h2>
      <p class="modal-sub">${esc(state.course.title)} - text is extracted locally and never leaves your account.</p>
      <form id="material-form">
        <div class="modal-body">
          <div class="dropzone" id="modal-dropzone">
            ${icon("upload")}
            <div class="dropzone-title" id="modal-drop-title">Drop a file or click to browse</div>
            <div class="dropzone-sub">PDF, DOCX, PPTX, TXT, MD, CSV, HTML or image</div>
            <input type="file" id="modal-file" accept=".pdf,.docx,.pptx,.txt,.md,.markdown,.csv,.html,.htm,.png,.jpg,.jpeg,.webp" />
          </div>
          <div class="auth-divider"><span>or paste notes</span></div>
          <div class="field">
            <textarea id="modal-notes" placeholder="Paste lecture notes, a summary or a set of definitions (at least 20 words)..." style="min-height:110px;"></textarea>
          </div>
          <p class="form-error" id="material-error" hidden></p>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" data-close>Cancel</button>
          <button type="submit" class="btn btn-primary" id="material-submit">${icon("upload")} Upload</button>
        </div>
      </form>`);

    const fileInput = $("#modal-file");
    const dropzone = $("#modal-dropzone");

    // The real input is visually hidden, so the whole dropzone opens the picker.
    dropzone.tabIndex = 0;
    dropzone.setAttribute("role", "button");
    dropzone.addEventListener("click", (event) => {
      if (event.target === fileInput) return;
      event.preventDefault();
      fileInput.click();
    });
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });

    const showFile = () => {
      const file = fileInput.files[0];
      $("#modal-drop-title").textContent = file ? file.name : "Drop a file or click to browse";
    };
    fileInput.addEventListener("change", showFile);

    // Depth counter: dragleave fires for child nodes too, which would flicker.
    let dragDepth = 0;
    dropzone.addEventListener("dragenter", (event) => {
      event.preventDefault();
      dragDepth += 1;
      dropzone.classList.add("dragging");
    });
    dropzone.addEventListener("dragover", (event) => event.preventDefault());
    dropzone.addEventListener("dragleave", (event) => {
      event.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) dropzone.classList.remove("dragging");
    });
    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dragDepth = 0;
      dropzone.classList.remove("dragging");
      const files = event.dataTransfer && event.dataTransfer.files;
      if (files && files.length) {
        fileInput.files = files;
        showFile();
      }
    });

    $("#material-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = $("#material-submit");
      const errorNode = $("#material-error");
      const file = fileInput.files[0];
      const notes = $("#modal-notes").value.trim();
      errorNode.hidden = true;

      if (!file && notes.split(/\s+/).filter(Boolean).length < 20) {
        errorNode.hidden = false;
        errorNode.textContent = file ? "" : "Choose a file or paste at least 20 words of notes.";
        return;
      }

      button.disabled = true;
      const original = button.innerHTML;
      button.innerHTML = "Uploading...";
      try {
        if (file) {
          const form = new FormData();
          form.append("file", file);
          const result = await api(`/documents/courses/${state.course.id}/documents`, {
            method: "POST",
            form,
          });
          // Extraction/OCR runs server-side; the card below follows live progress.
          closeModal();
          await trackUpload(result.document);
          return;
        }
        const result = await api(`/documents/courses/${state.course.id}/documents/paste`, {
          method: "POST",
          body: { text: notes },
        });
        closeModal();
        await refreshCourse();
        toast(result.message || "Notes added.", "success");
        if (state.tab === "materials") navigate(`#/course/${state.course.id}/topics`);
        return;
      } catch (error) {
        errorNode.hidden = false;
        errorNode.textContent = error.message;
      }
      button.disabled = false;
      button.innerHTML = original;
    });
  }

  function openPasteNotes() {
    openAddMaterial();
    setTimeout(() => $("#modal-notes")?.focus(), 60);
  }

  function openGeneratePlan() {
    const course = state.course;
    openModal(`
      <h2>Generate a study plan</h2>
      <p class="modal-sub">Built from ${course && course.topic_count ? plural(course.topic_count, "topic") : "your material"}${course && course.exam_date && course.days_until_exam >= 0 ? ` · exam in ${course.days_until_exam} days` : ""}.</p>
      <form id="plan-form">
        <div class="modal-body">
          <div class="form-row">
            <div class="field">
              <label for="plan-count">Tasks</label>
              <select id="plan-count">
                ${[3, 5, 8, 10, 12].map((n) => `<option value="${n}" ${n === 8 ? "selected" : ""}>${n} tasks</option>`).join("")}
              </select>
            </div>
            <div class="field">
              <label for="plan-minutes">Minutes per day</label>
              <input id="plan-minutes" type="number" min="15" max="480" step="5" value="${state.user.daily_study_minutes}" />
            </div>
          </div>
          <div class="field">
            <label for="plan-focus">Focus (optional)</label>
            <input id="plan-focus" placeholder="e.g. enzyme kinetics, everything before week 4" maxlength="300" />
          </div>
          <div class="field">
            <label for="plan-difficulty">Difficulty</label>
            <select id="plan-difficulty">
              <option value="">Match my material</option>
              ${[1, 2, 3, 4, 5].map((level) => `<option value="${level}">Level ${level}</option>`).join("")}
            </select>
          </div>
          <label class="row small dim" style="gap:8px;cursor:pointer;">
            <input type="checkbox" id="plan-replace" style="width:auto;" />
            Replace my open tasks
          </label>
          <p class="form-error" id="plan-error" hidden></p>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" data-close>Cancel</button>
          <button type="submit" class="btn btn-primary" id="plan-submit">${icon("spark")} Build plan</button>
        </div>
      </form>`);

    $("#plan-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = $("#plan-submit");
      const original = button.innerHTML;
      button.disabled = true;
      button.innerHTML = "Building...";
      try {
        const difficulty = $("#plan-difficulty").value;
        const result = await api(`/tasks/courses/${state.course.id}/generate`, {
          method: "POST",
          body: {
            count: Number($("#plan-count").value),
            focus: $("#plan-focus").value.trim() || null,
            minutes_per_day: Number($("#plan-minutes").value) || state.user.daily_study_minutes,
            difficulty: difficulty ? Number(difficulty) : null,
            replace_existing: $("#plan-replace").checked,
          },
        });
        closeModal();
        await refreshCourse();
        toast(result.plan_note || "Plan created.", "success");
        navigate(`#/course/${state.course.id}/plan`);
      } catch (error) {
        const errorNode = $("#plan-error");
        errorNode.hidden = false;
        errorNode.textContent = error.message;
        button.disabled = false;
        button.innerHTML = original;
      }
    });
  }

  function openTaskDetail(taskId) {
    const task = state.tasks.find((item) => item.id === taskId);
    if (!task) return;
    openModal(`
      <div class="row" style="gap:8px;margin-bottom:6px;">
        <span class="task-type ${esc(task.task_type)}">${esc(task.task_type)}</span>
        <span class="chip">${icon("clock")} ${fmtMinutes(task.estimated_minutes)}</span>
        <span class="chip">Difficulty ${task.difficulty}/5</span>
      </div>
      <h2>${esc(task.title)}</h2>
      <p class="modal-sub">${task.topic_title ? esc(task.topic_title) : "No topic linked"}${task.due_date ? ` · ${esc(fmtDayLabel(task.due_date))}` : ""}</p>
      <div class="modal-body">
        ${task.description ? `<p class="small dim" style="white-space:pre-line;">${esc(task.description)}</p>` : `<p class="small muted">No description.</p>`}
        ${task.hint ? `<div class="task-hint">${esc(task.hint)}</div>` : ""}
      </div>
      <div class="modal-foot">
        <button class="btn btn-danger" data-action="delete-task" data-id="${esc(task.id)}">${icon("trash")} Remove</button>
        <button class="btn btn-ghost" data-close>Close</button>
        <button class="btn btn-primary" data-action="toggle-task" data-id="${esc(task.id)}">${task.status === "done" ? "Mark not done" : `${icon("check")} Mark done`}</button>
      </div>`);
  }

  function confirmDialog(title, message, confirmLabel, onConfirm, danger = true) {
    openModal(`
      <h2>${esc(title)}</h2>
      <p class="modal-sub">${esc(message)}</p>
      <div class="modal-foot">
        <button class="btn btn-ghost" data-close>Cancel</button>
        <button class="btn ${danger ? "btn-danger" : "btn-primary"}" id="confirm-yes">${esc(confirmLabel)}</button>
      </div>`);
    $("#confirm-yes").addEventListener("click", async () => {
      closeModal();
      await onConfirm();
    });
  }

  /* ---------------------------------------------------------------- actions */
  async function refreshCourse() {
    if (!state.course) return;
    state.course = await api(`/documents/courses/${state.course.id}`);
    state.topics = await api(`/documents/courses/${state.course.id}/topics`).catch(() => []);
    state.tasks = await api(`/tasks/courses/${state.course.id}`).catch(() => []);
    state.documents = await api(`/documents/courses/${state.course.id}/documents`).catch(() => []);
    await loadCourses();
    render();
  }

  async function toggleTask(taskId) {
    const task = state.tasks.find((item) => item.id === taskId);
    if (!task) return;
    const nextStatus = task.status === "done" ? "todo" : "done";
    const wasDone = task.status === "done";
    task.status = nextStatus;
    closeModal();
    renderTabPanel();
    renderChrome();

    try {
      await api(`/tasks/${taskId}`, { method: "PATCH", body: { status: nextStatus } });
      if (!wasDone) {
        const minutes = task.estimated_minutes;
        toast(`Nice - ${fmtMinutes(minutes)} logged. Readiness updated.`, "success");
      }
      await refreshCourse();
    } catch (error) {
      task.status = wasDone ? "done" : "todo";
      renderTabPanel();
      toast(error.message, "error");
    }
  }

  function renderTabPanel() {
    const panel = $("#tab-panel");
    if (!panel) return;
    panel.innerHTML = tabContent();
    if (state.tab === "coach") paintThread();
  }

  async function deleteTask(taskId) {
    confirmDialog("Remove this task?", "It disappears from your plan, but study minutes you already logged stay counted.", "Remove", async () => {
      try {
        await api(`/tasks/${taskId}`, { method: "DELETE" });
        await refreshCourse();
        toast("Task removed.", "info");
      } catch (error) {
        toast(error.message, "error");
      }
    });
  }

  async function deleteDocument(documentId) {
    confirmDialog("Remove this document?", "Its text and passages are deleted, and the topic map is rebuilt from what is left.", "Remove", async () => {
      try {
        await api(`/documents/courses/${state.course.id}/documents/${documentId}`, { method: "DELETE" });
        await refreshCourse();
        toast("Document removed and topics rebuilt.", "info");
      } catch (error) {
        toast(error.message, "error");
      }
    });
  }

  /* --------------------------------------------------------- event plumbing */
  const UPLOAD_STAGE_LABELS = {
    queued: "Waiting to start",
    reading: "Reading the file",
    ocr: "Reading pages with OCR",
    indexing: "Building chunks and topics",
  };

  function uploadCardMarkup(doc) {
    return `
      <div class="upload-head">
        <span class="upload-spinner" aria-hidden="true"></span>
        <span class="upload-title">${esc(doc.filename)}</span>
      </div>
      <div class="upload-stage" data-stage>Waiting to start</div>
      <div class="meter"><span data-bar style="width:6%"></span></div>`;
  }

  function paintUploadCard(card, doc) {
    const stage = doc.progress_stage || "queued";
    const current = doc.progress_current || 0;
    const total = doc.progress_total || 0;
    let label = UPLOAD_STAGE_LABELS[stage] || "Working";
    let percent = 10;
    if (stage === "reading") {
      percent = 25;
    } else if (stage === "ocr") {
      if (total) {
        label = current
          ? `Reading page ${current} of ${total} with OCR`
          : `Starting OCR - ${plural(total, "page")}`;
        percent = current ? Math.round((current / total) * 100) : 8;
      } else {
        label = current ? `Reading page ${current} with OCR` : "Starting OCR";
        percent = 12;
      }
    } else if (stage === "indexing") {
      percent = 92;
    }
    card.querySelector("[data-stage]").textContent = label;
    card.querySelector("[data-bar]").style.width = `${Math.min(97, Math.max(6, percent))}%`;
  }

  async function trackUpload(doc) {
    if (!doc) return null;
    const courseId = state.course.id;
    let card = $("#upload-progress");
    if (!card) {
      card = document.createElement("div");
      card.id = "upload-progress";
      card.className = "upload-progress";
      card.setAttribute("role", "status");
      card.setAttribute("aria-live", "polite");
      $("#toasts").appendChild(card);
    }
    card.innerHTML = uploadCardMarkup(doc);
    paintUploadCard(card, doc);

    const deadline = Date.now() + 10 * 60 * 1000;
    let latest = doc;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      try {
        latest = await api(`/documents/courses/${courseId}/documents/${doc.id}`);
      } catch (error) {
        card.remove();
        toast(error.message || "Lost track of the upload.", "error");
        return null;
      }
      if (latest.status === "processing") {
        paintUploadCard(card, latest);
        continue;
      }
      card.remove();
      await refreshCourse();
      if (latest.status === "failed") {
        toast(latest.error_message || "That file could not be read.", "error");
        return latest;
      }
      const warnings = (latest.extraction_warnings || []).join(" ");
      toast(
        `${plural(latest.word_count, "word")} from ${latest.filename} - ${plural(
          state.topics.length,
          "topic"
        )} in this course.${warnings ? ` ${warnings}` : ""}`,
        "success"
      );
      if (state.tab === "materials") navigate(`#/course/${state.course.id}/topics`);
      return latest;
    }
    card.remove();
    toast("Still processing - check this course again in a minute.", "info");
    return null;
  }

  async function uploadMaterialFile(file) {
    if (!file || !state.course) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await api(`/documents/courses/${state.course.id}/documents`, {
        method: "POST",
        form,
      });
      await trackUpload(result.document);
    } catch (error) {
      toast(error.message || "Upload failed.", "error");
    }
  }

  document.addEventListener("change", (event) => {
    if (event.target && event.target.id === "file-input" && event.target.files && event.target.files[0]) {
      const file = event.target.files[0];
      event.target.value = "";
      uploadMaterialFile(file);
    }
  });

  // Drag-and-drop on the materials panel dropzone (delegated, survives re-renders).
  ["dragenter", "dragover"].forEach((type) => {
    document.addEventListener(type, (event) => {
      const dz = event.target.closest(".dropzone[data-action='pick-file']");
      if (dz) { event.preventDefault(); dz.classList.add("dragging"); }
    });
  });
  ["dragleave", "drop"].forEach((type) => {
    document.addEventListener(type, (event) => {
      const dz = event.target.closest(".dropzone[data-action='pick-file']");
      if (dz) { event.preventDefault(); dz.classList.remove("dragging"); }
    });
  });
  document.addEventListener("drop", (event) => {
    const dz = event.target.closest(".dropzone[data-action='pick-file']");
    if (dz && event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0]) {
      uploadMaterialFile(event.dataTransfer.files[0]);
    }
  });

  document.addEventListener("click", async (event) => {
    const target = event.target.closest("[data-action]");
    if (!target || !document.body.contains(target)) return;
    const action = target.dataset.action;

    switch (action) {
      case "new-course":
        event.preventDefault();
        openNewCourse();
        return;
      case "add-material":
        event.preventDefault();
        openAddMaterial();
        return;
      case "edit-course":
        event.preventDefault();
        openEditCourse();
        return;
      case "delete-course":
        event.preventDefault();
        deleteCourse();
        return;
      case "paste-notes":
        event.preventDefault();
        openPasteNotes();
        return;
      case "pick-file":
        event.preventDefault();
        if (event.target.tagName === "INPUT") return;
        $("#file-input")?.click();
        return;
      case "gen-plan":
        event.preventDefault();
        openGeneratePlan();
        return;
      case "open-course":
        state.course = null;
        navigate(`#/course/${target.dataset.id}`);
        return;
      case "go-dashboard":
        state.course = null;
        navigate("#/dashboard");
        return;
      case "retake-assessment":
        event.preventDefault();
        navigate("#/assessment");
        return;
      case "signout":
        confirmDialog(
          "Sign out?",
          state.user && state.user.is_anonymous
            ? "This is a guest session. Once you sign out you cannot get back into it."
            : "You can sign back in with your email and password.",
          "Sign out",
          () => signOut(),
          true
        );
        return;
      case "reload":
        event.preventDefault();
        state.course = null;
        await loadCourses();
        render();
        return;
      case "open-resources":
        event.preventDefault();
        navigate(target.dataset.tab ? `#/resources/${target.dataset.tab}` : "#/resources");
        return;
      case "tab":
        event.preventDefault();
        state.tab = target.dataset.tab;
        navigate(`#/course/${state.course.id}/${state.tab}`);
        return;
      case "toggle-task":
        event.preventDefault();
        await toggleTask(target.dataset.id);
        return;
      case "delete-task":
        event.preventDefault();
        await deleteTask(target.dataset.id);
        return;
      case "open-task":
        event.preventDefault();
        openTaskDetail(target.dataset.id);
        return;
      case "delete-document":
        event.preventDefault();
        await deleteDocument(target.dataset.id);
        return;
      case "rebuild-topics": {
        event.preventDefault();
        target.disabled = true;
        try {
          const topics = await api(`/documents/courses/${state.course.id}/topics/rebuild`, { method: "POST" });
          state.topics = topics || [];
          await refreshCourse();
          toast(`Topic map rebuilt: ${plural(state.topics.length, "topic")}.`, "success");
        } catch (error) {
          toast(error.message, "error");
        } finally {
          target.disabled = false;
        }
        return;
      }
      case "ask-topic": {
        event.preventDefault();
        const topic = state.topics.find((item) => item.id === target.dataset.id);
        state.chat.sessionId = null;
        state.chat.topicId = target.dataset.id;
        state.chat.messages = [];
        navigate(`#/course/${state.course.id}/coach`);
        setTimeout(() => {
          const input = $("#chat-input");
          if (input && topic) {
            input.value = `Explain ${topic.title.toLowerCase()}`;
            input.focus();
          }
        }, 260);
        return;
      }
      case "hint-level":
        event.preventDefault();
        state.chat.hintLevel = Number(target.dataset.level);
        document.querySelectorAll("#hint-picker button").forEach((button) => {
          button.classList.toggle("active", Number(button.dataset.level) === state.chat.hintLevel);
        });
        return;
      case "suggestion":
        event.preventDefault();
        sendChat(target.dataset.prompt);
        return;
      case "new-chat": {
        event.preventDefault();
        try {
          const session = await api(`/chat/courses/${state.course.id}/sessions`, { method: "POST", body: {} });
          state.chat = { sessionId: session.id, topicId: null, messages: [], hintLevel: state.chat.hintLevel, sending: false };
          paintThread();
          toast("Started a new conversation.", "info");
        } catch (error) {
          toast(error.message, "error");
        }
        return;
      }
      default:
        return;
    }
  });

  document.addEventListener("submit", (event) => {
    if (event.target.id === "chat-form") {
      event.preventDefault();
      sendChat();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.target.id === "chat-input" && event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChat();
    }
  });

  $("#menu-btn").addEventListener("click", () => {
    const open = $("#sidebar").classList.toggle("open");
    document.body.classList.toggle("nav-open", open);
    $("#menu-btn").setAttribute("aria-expanded", String(open));
  });

  // Tapping the dimmed page, or Escape, closes the drawer. Without this the
  // only way out on a phone was to pick a menu item.
  document.addEventListener("click", (event) => {
    if (!document.body.classList.contains("nav-open")) return;
    if (event.target.closest("#sidebar") || event.target.closest("#menu-btn")) return;
    closeNav();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("nav-open")) closeNav();
  });

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      state.course = null;
      navigate(`#/${item.dataset.route}`);
    });
  });

  $("#user-chip").addEventListener("click", () => {
    state.course = null;
    navigate("#/settings");
  });

  $("#new-course-btn").addEventListener("click", openNewCourse);
  $("#new-course-btn-2").addEventListener("click", openNewCourse);
  $("#feedback-btn").addEventListener("click", openFeedback);

  /* --------------------------------------------------------- markdown-lite */
  function md(text) {
    const raw = String(text || "");
    const lines = raw.split(/\n/);
    const blocks = [];
    let list = null;

    const inline = (value) =>
      esc(value)
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");

    const flushList = () => {
      if (list) {
        blocks.push(`<${list.type}>${list.items.map((item) => `<li>${inline(item)}</li>`).join("")}</${list.type}>`);
        list = null;
      }
    };

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        flushList();
        continue;
      }
      const bullet = trimmed.match(/^[-*]\s+(.*)$/);
      const numbered = trimmed.match(/^\d+[.)]\s+(.*)$/);
      const quote = trimmed.match(/^>\s?(.*)$/);

      if (bullet) {
        if (!list || list.type !== "ul") {
          flushList();
          list = { type: "ul", items: [] };
        }
        list.items.push(bullet[1]);
      } else if (numbered) {
        if (!list || list.type !== "ol") {
          flushList();
          list = { type: "ol", items: [] };
        }
        list.items.push(numbered[1]);
      } else if (quote) {
        flushList();
        blocks.push(`<blockquote>${inline(quote[1])}</blockquote>`);
      } else {
        flushList();
        blocks.push(`<p>${inline(trimmed)}</p>`);
      }
    }
    flushList();
    return blocks.join("") || "<p></p>";
  }

  /* ------------------------------------------------------------------ boot */
  function hydrateIcons(root = document) {
    root.querySelectorAll("[data-icon]").forEach((node) => {
      if (node.dataset.iconDone === "1") return;
      node.innerHTML = icon(node.dataset.icon);
      node.dataset.iconDone = "1";
    });
  }

  async function boot() {
    hydrateIcons();
    setAuthMode("register");
    const saved = loadSession();
    if (!saved || !saved.token) {
      showAuth();
      return;
    }
    state.token = saved.token;
    state.user = saved.user || null;
    try {
      state.user = await api("/auth/me");
      persist();
      showShell();
      await loadCourses();
      render();
    } catch {
      signOut();
    }
  }

  boot();
})();
