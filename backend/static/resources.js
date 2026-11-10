/* Student Resources Centre - rendered inside the Study Companion shell.
 *
 * The centre used to be a separate site reached through an external link. It is
 * now a route in the app: this module paints its markup into the app's view and
 * loads the content from /api/resources, so the page, the data and the styling
 * all come from the same application.
 *
 * Everything here is client-side. The career-path choices, the business-plan
 * ticks and the thesis guide's progress live in localStorage.
 */
(() => {
  "use strict";

  const API = "/api/resources";
  const TABS = ["scholarships", "research", "thesis", "path", "career", "employment", "library"];
  const SECTION_IDS = {
    scholarships: "scholarships-body",
    research: "research-body",
    career: "career-body",
    employment: "employment-body",
    library: "library-body",
  };

  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function externalLink(url, label, className = "link") {
    return `<a class="${className}" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} <span aria-hidden="true">↗</span></a>`;
  }

  function chips(list, variant = "") {
    return list.map((item) => `<span class="chip${variant}">${esc(item)}</span>`).join("");
  }

  function errorBlock(message) {
    return `<div class="error">${esc(message)} Could not load this section. Reload the page to try again.</div>`;
  }

  const cache = {};
  let activeTab = "scholarships";
  let pathStarted = false;
  let documentBound = false;
  let agentLoading = null;

  async function getJSON(path) {
    const response = await fetch(API + path, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    return response.json();
  }

  /* ------------------------------------------------------------- markup shell */

  const SHELL = `
    <div class="rc rc-scope">
      <header class="hero">
        <div class="hero__inner">
          <p class="eyebrow">Study Companion</p>
          <h1>Student Resources Centre</h1>
          <p class="hero__intro" id="hero-intro">
            Scholarships, research placements, career guidance and live job routes,
            gathered in one place and organised by what you are trying to do next.
          </p>
          <ul class="stats" id="stats" aria-label="Resources available"></ul>
        </div>
      </header>

      <nav class="tabs" aria-label="Resource sections" role="tablist">
        <div class="tabs__inner" id="tabs">
          <button role="tab" id="tab-scholarships" aria-controls="panel-scholarships" aria-selected="true" data-tab="scholarships">Scholarships</button>
          <button role="tab" id="tab-research" aria-controls="panel-research" aria-selected="false" data-tab="research">Research</button>
          <button role="tab" id="tab-thesis" aria-controls="panel-thesis" aria-selected="false" data-tab="thesis">Thesis guide</button>
          <button role="tab" id="tab-path" aria-controls="panel-path" aria-selected="false" data-tab="path">My career path</button>
          <button role="tab" id="tab-career" aria-controls="panel-career" aria-selected="false" data-tab="career">Careers</button>
          <button role="tab" id="tab-employment" aria-controls="panel-employment" aria-selected="false" data-tab="employment">Jobs</button>
          <button role="tab" id="tab-library" aria-controls="panel-library" aria-selected="false" data-tab="library">Library</button>
        </div>
      </nav>

      <main id="panels" class="panels">
        <section class="panel" id="panel-scholarships" role="tabpanel" aria-labelledby="tab-scholarships">
          <div class="panel__head">
            <h2>Scholarship opportunities</h2>
            <p>Funding for tuition, living costs and the tests that get you there. Deadlines follow each funder's own cycle.</p>
          </div>
          <div id="scholarships-body" class="loading">Loading scholarships…</div>
        </section>

        <section class="panel" id="panel-research" role="tabpanel" aria-labelledby="tab-research" hidden>
          <div class="panel__head">
            <h2>Research opportunities</h2>
            <p>Summer placements, funded master's and PhD routes, and how to write to a supervisor.</p>
          </div>
          <div id="research-body" class="loading">Loading research routes…</div>
        </section>

        <section class="panel" id="panel-thesis" role="tabpanel" aria-labelledby="tab-thesis" hidden>
          <div class="panel__head">
            <h2>Your research and thesis guide</h2>
            <p>An agent that walks you from a blank page to a defended thesis: scope the topic, frame the question, search the literature, design the method, write the proposal, analyse, write up and submit. Tell it your deadline and it builds a week-by-week plan. Everything stays in this browser.</p>
          </div>

          <div class="agent" id="thesis-agent">
            <aside class="agent__side">
              <div class="agent__progress">
                <span class="agent__progress-label">Your progress</span>
                <div class="agent__bar"><span id="agent-bar"></span></div>
                <span id="agent-percent">0% complete</span>
              </div>
              <ol class="agent__roadmap" id="agent-roadmap"></ol>
              <button class="agent__reset" id="agent-reset" type="button">Start over</button>
            </aside>

            <div class="agent__main">
              <div class="agent__log" id="agent-log" role="log" aria-live="polite" aria-label="Thesis guide conversation"></div>
              <form class="agent__composer" id="agent-form">
                <label class="sr-only" for="agent-input">Ask the thesis guide</label>
                <input id="agent-input" type="text" autocomplete="off" placeholder="Ask: how do I narrow my topic?" />
                <button class="button" type="submit">Send</button>
              </form>
            </div>
          </div>
        </section>

        <section class="panel" id="panel-path" role="tabpanel" aria-labelledby="tab-path" hidden>
          <div class="panel__head">
            <h2>My career path</h2>
            <p>Choose your field of study and one or more locations. The centre then narrows every opportunity down to your field, at home and abroad.</p>
          </div>

          <form class="path-picker" id="path-picker">
            <div class="field">
              <label for="path-field">Field of study</label>
              <select id="path-field" name="field"></select>
            </div>
            <div class="field field--locations">
              <span class="field-label" id="path-locations-label">Where you are based</span>
              <div class="path-locations" id="path-region-options" role="group" aria-labelledby="path-locations-label"></div>
              <p class="path-picker__hint">Tick every location you care about — your country plus any destination — to see those opportunities together.</p>
            </div>
            <div class="field field--performance">
              <span class="field-label" id="path-performance-label">Your academic performance</span>
              <div class="path-performance" id="path-performance-options" role="radiogroup" aria-labelledby="path-performance-label"></div>
              <p class="path-picker__hint">Use your current average. The career agent changes its advice with your results — it is guidance, not an eligibility ruling.</p>
            </div>
            <p class="path-picker__note">Your choice is saved on this device, so this tab opens on your field next time. <button type="button" class="path-reset" id="path-reset">Clear my saved data</button></p>
          </form>

          <div id="path-body" class="loading">Loading your career path…</div>
        </section>

        <section class="panel" id="panel-career" role="tabpanel" aria-labelledby="tab-career" hidden>
          <div class="panel__head">
            <h2>Building your career</h2>
            <p>How to move from your degree into the work you actually want, by field of study.</p>
          </div>
          <div id="career-body" class="loading">Loading career guidance…</div>
        </section>

        <section class="panel" id="panel-employment" role="tabpanel" aria-labelledby="tab-employment" hidden>
          <div class="panel__head">
            <h2>Employment opportunities</h2>
            <p>Where graduate roles are advertised, which entry routes exist, and what to check before you apply.</p>
          </div>
          <div id="employment-body" class="loading">Loading job routes…</div>
        </section>

        <section class="panel" id="panel-library" role="tabpanel" aria-labelledby="tab-library" hidden>
          <div class="panel__head">
            <h2>Resource library</h2>
            <p>Guides and practice papers shared with the platform. Open a document to read it here, or download a copy.</p>
          </div>
          <div id="library-body" class="loading">Loading documents…</div>
        </section>
      </main>

      <footer class="footer">
        <p>Student Resources Centre · Study Companion</p>
        <p class="footer__note">Opportunity details are checked against each funder's official page. Always confirm dates and eligibility at the source before applying.</p>
      </footer>

      <dialog id="doc-dialog" class="dialog" aria-labelledby="doc-title">
        <div class="dialog__head">
          <div>
            <p class="eyebrow eyebrow--dark" id="doc-kind">Document</p>
            <h2 id="doc-title">Document</h2>
          </div>
          <button class="dialog__close" id="doc-close" aria-label="Close document">Close</button>
        </div>
        <div class="dialog__body" id="doc-body"></div>
        <div class="dialog__foot">
          <a id="doc-download" class="button" href="#" download>Download document</a>
          <p class="muted" id="doc-source"></p>
        </div>
      </dialog>
    </div>`;

  /* ------------------------------------------------------------------- tabs */

  function selectTab(name, { focus = false } = {}) {
    if (!TABS.includes(name)) return;
    activeTab = name;

    TABS.forEach((tab) => {
      const button = $(`tab-${tab}`);
      const panel = $(`panel-${tab}`);
      if (!button || !panel) return;
      const selected = tab === name;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
      panel.hidden = !selected;
    });

    // Keep the address bar in step so a refresh (or a shared link) reopens the
    // section the student was reading. replaceState, not pushState: switching
    // tabs should not fill up the back button.
    if (location.hash.startsWith("#/resources")) {
      history.replaceState(null, "", `#/resources/${name}`);
    }

    if (focus && $(`tab-${name}`)) $(`tab-${name}`).focus();
    if (name === "path" && !pathStarted) {
      pathStarted = true;
      initCareerPath();
    }
    if (name === "thesis") openThesisAgent();
  }

  function initTabs() {
    const buttons = TABS.map((tab) => $(`tab-${tab}`)).filter(Boolean);

    buttons.forEach((button) => {
      button.addEventListener("click", () => selectTab(button.dataset.tab));
      button.addEventListener("keydown", (event) => {
        const index = buttons.indexOf(button);
        let next = null;
        if (event.key === "ArrowRight") next = (index + 1) % buttons.length;
        if (event.key === "ArrowLeft") next = (index - 1 + buttons.length) % buttons.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = buttons.length - 1;
        if (next === null) return;
        event.preventDefault();
        selectTab(buttons[next].dataset.tab, { focus: true });
      });
    });
  }

  /* ------------------------------------------------------------- section data */

  function renderHero(overview) {
    if (overview.intro) $("hero-intro").textContent = overview.intro;
    $("stats").innerHTML = (overview.stats || [])
      .map((stat) => `<li><span class="value">${esc(stat.value)}</span><span class="label">${esc(stat.label)}</span></li>`)
      .join("");
  }

  function renderScholarships(data) {
    const advice = data.advice && data.advice.length
      ? `<div class="callout">
          <h3>Before you apply</h3>
          <ul>${data.advice.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
        </div>`
      : "";

    const cards = data.scholarships
      .map(
        (item) => `<article class="card">
          <div class="chips">${chips(item.levels)}<span class="chip chip--teal">${esc(item.fields)}</span></div>
          <h3>${esc(item.name)}</h3>
          <p class="provider">${esc(item.provider)}</p>
          <p class="body">${esc(item.summary)}</p>
          <dl class="facts">
            <div><dt>Funding</dt><dd>${esc(item.funding)}</dd></div>
            <div><dt>Application cycle</dt><dd>${esc(item.cycle)}</dd></div>
          </dl>
          ${externalLink(item.url, "Official page")}
        </article>`
      )
      .join("");

    const databases = (data.databases || [])
      .map(
        (item) => `<article class="board">
          <span class="scope">Database</span>
          <h4>${externalLink(item.url, item.name, "")}</h4>
          <p>${esc(item.note)}</p>
        </article>`
      )
      .join("");

    const body = $("scholarships-body");
    body.innerHTML = `
      ${advice}
      <div class="grid">${cards}</div>
      ${databases ? `<h2 class="section-title">Keep searching</h2><div class="boards">${databases}</div>` : ""}
    `;
    body.className = "";
  }

  function renderResearch(data) {
    const guide = (data.guide || [])
      .map((item) => `<li><strong>${esc(item.step)}</strong><p>${esc(item.detail)}</p></li>`)
      .join("");

    const routes = data.routes
      .map(
        (item) => `<article class="card">
          <div class="chips"><span class="chip">${esc(item.type)}</span><span class="chip chip--teal">${esc(item.where)}</span></div>
          <h3>${esc(item.name)}</h3>
          <p class="body">${esc(item.detail)}</p>
          <dl class="facts"><div><dt>Funding</dt><dd>${esc(item.funding)}</dd></div></dl>
          ${externalLink(item.url, "Programme page")}
        </article>`
      )
      .join("");

    const body = $("research-body");
    body.innerHTML = `
      <h2 class="section-title">How to get your first placement</h2>
      <ol class="steps">${guide}</ol>
      <h2 class="section-title">Routes worth applying to</h2>
      <div class="grid">${routes}</div>
      <h2 class="section-title">Email a supervisor</h2>
      <p>Short, specific and easy to answer. Replace the bracketed parts before sending, and attach a one-page CV.</p>
      <div class="code-block">
        <button class="copy" type="button" data-copy="supervisor-email">Copy</button>
        <pre class="code" id="supervisor-email">${esc(data.supervisor_email)}</pre>
      </div>
    `;
    body.className = "";
  }

  function renderCareer(data) {
    const steps = (data.steps || [])
      .map((item) => `<li><strong>${esc(item.title)}</strong><p>${esc(item.detail)}</p></li>`)
      .join("");

    const playbooks = (data.playbooks || [])
      .map(
        (item) => `<details class="playbook">
          <summary>${esc(item.field)}</summary>
          <div class="playbook__body">
            <div><span>First roles</span><p>${esc(item.first_roles)}</p></div>
            <div><span>Credentials that count</span><p>${esc(item.credentials)}</p></div>
            <div><span>Proof of skill</span><p>${esc(item.proof)}</p></div>
            <div><span>Professional bodies</span><p>${esc(item.bodies)}</p></div>
          </div>
        </details>`
      )
      .join("");

    const networking = (data.networking || []).map((item) => `<li>${esc(item)}</li>`).join("");

    const body = $("career-body");
    body.innerHTML = `
      <h2 class="section-title">Six moves that matter</h2>
      <ol class="steps">${steps}</ol>
      <h2 class="section-title">Your field of study</h2>
      <div class="playbooks">${playbooks}</div>
      <h2 class="section-title">Build a network without asking for a job</h2>
      <div class="callout"><ul>${networking}</ul></div>
    `;
    body.className = "";
  }

  function renderEmployment(data) {
    const routes = (data.routes || [])
      .map(
        (item) => `<article class="card">
          <h3 style="margin-top:0">${esc(item.route)}</h3>
          <p class="body">${esc(item.detail)}</p>
        </article>`
      )
      .join("");

    const boards = (data.boards || [])
      .map(
        (item) => `<article class="board">
          <span class="scope">${esc(item.scope)}</span>
          <h4>${externalLink(item.url, item.name, "")}</h4>
          <p>${esc(item.note)}</p>
        </article>`
      )
      .join("");

    const checklist = (data.checklist || []).map((item) => `<li>${esc(item)}</li>`).join("");

    const body = $("employment-body");
    body.innerHTML = `
      <h2 class="section-title">Entry routes</h2>
      <div class="grid">${routes}</div>
      <h2 class="section-title">Where the jobs are advertised</h2>
      <div class="boards">${boards}</div>
      <h2 class="section-title">Before you press send</h2>
      <ul class="checklist">${checklist}</ul>
    `;
    body.className = "";
  }

  /* ----------------------------------------------------------- my career path */

  const PATH_STORAGE_KEY = "studyCompanion.careerPath";
  const BUSINESS_STORAGE_KEY = "studyCompanion.businessSteps";
  const BUSINESS_NOTE_KEY = "studyCompanion.businessNote";
  const BUSINESS_NOTE_LIMIT = 200;
  const ADVISOR_VIEW_KEY = "studyCompanion.advisorView";
  const noteFallback = {};
  let advisorView = readAdvisorView();

  function readAdvisorView() {
    try {
      return localStorage.getItem(ADVISOR_VIEW_KEY) === "business" ? "business" : "work";
    } catch (error) {
      return "work";
    }
  }

  function readSavedPath() {
    try {
      const saved = JSON.parse(localStorage.getItem(PATH_STORAGE_KEY) || "null");
      if (!saved || typeof saved.field !== "string") return null;
      const regions = Array.isArray(saved.regions)
        ? saved.regions.filter((key) => typeof key === "string")
        : typeof saved.region === "string"
          ? [saved.region]
          : [];
      if (regions.length) {
        return {
          field: saved.field,
          regions,
          performance: typeof saved.performance === "string" ? saved.performance : null,
        };
      }
    } catch (error) {
      /* storage can be unavailable in private modes; fall back to the default path */
    }
    return null;
  }

  function savePath(state) {
    try {
      localStorage.setItem(PATH_STORAGE_KEY, JSON.stringify(state));
    } catch (error) {
      /* saving the preference is a convenience, not a requirement */
    }
  }

  function fillPathOptions(data) {
    const fieldSelect = $("path-field");
    const regionSelect = $("path-region-options");

    if (!fieldSelect.options.length) {
      fieldSelect.innerHTML = data.fields
        .map((item) => `<option value="${esc(item.key)}">${esc(item.label)}</option>`)
        .join("");
    }
    if (!regionSelect.children.length) {
      const groups =
        Array.isArray(data.region_groups) && data.region_groups.length
          ? data.region_groups
          : [{ label: "", regions: data.regions }];
      regionSelect.innerHTML = groups
        .map(
          (group) => `<div class="path-locations__group">
            ${group.label ? `<span class="path-locations__heading">${esc(group.label)}</span>` : ""}
            <div class="path-locations__items">${group.regions
              .map(
                (item) => `<label class="loc">
                  <input type="checkbox" name="region" value="${esc(item.key)}">
                  <span>${esc(item.label)}</span>
                </label>`
              )
              .join("")}</div>
          </div>`
        )
        .join("");
    }

    fieldSelect.value = data.selected.field;
    const chosen = new Set((data.selected.regions || []).map((item) => item.key));
    regionSelect.querySelectorAll('input[name="region"]').forEach((input) => {
      input.checked = chosen.has(input.value);
    });

    const perfSelect = $("path-performance-options");
    if (perfSelect && !perfSelect.children.length && Array.isArray(data.performance_bands)) {
      perfSelect.innerHTML = data.performance_bands
        .map(
          (band) => `<label class="perf">
            <input type="radio" name="performance" value="${esc(band.key)}">
            <span>${esc(band.label)}</span>
          </label>`
        )
        .join("");
    }
    const activeBand = data.advisor && data.advisor.performance ? data.advisor.performance.key : null;
    if (perfSelect) {
      perfSelect.querySelectorAll('input[name="performance"]').forEach((input) => {
        input.checked = input.value === activeBand;
      });
    }
  }

  function opportunityList(items, showRegion) {
    if (!items.length) {
      return `<p class="empty">No listings for this combination yet. Use the search boards below, or open the Scholarships and Research tabs.</p>`;
    }
    return `<div class="opp-list">${items
      .map(
        (item) => `<a class="opp" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">
          <span class="opp__tags">
            <span class="chip chip--warm">${esc(item.kind)}</span>
            ${showRegion && item.region_label ? `<span class="chip">${esc(item.region_label)}</span>` : ""}
          </span>
          <strong>${esc(item.name)}</strong>
          <span class="opp__org">${esc(item.org)}</span>
          <span class="opp__detail">${esc(item.detail)}</span>
        </a>`
      )
      .join("")}</div>`;
  }

  function renderCareerPath(data) {
    const profile = data.profile;

    const startHere = (profile.start_here || [])
      .map((item) => `<li><strong>${esc(item.when)}</strong><p>${esc(item.action)}</p></li>`)
      .join("");

    const facts = [
      ["First roles", profile.first_roles],
      ["Credentials", profile.credentials],
      ["Proof of skill", profile.proof],
      ["Professional bodies", profile.bodies],
    ]
      .filter(([, value]) => value)
      .map(([label, value]) => `<div><span>${esc(label)}</span><p>${esc(value)}</p></div>`)
      .join("");

    const funding = (data.funding || [])
      .map(
        (item) => `<article class="board">
          <span class="scope">${esc((item.levels || []).join(" / "))}</span>
          <h4>${externalLink(item.url, item.name, "")}</h4>
          <p>${esc(item.funding)}</p>
        </article>`
      )
      .join("");

    const boards = (data.boards || [])
      .map(
        (item) => `<article class="board">
          <span class="scope">${esc(item.scope)}</span>
          <h4>${externalLink(item.url, item.name, "")}</h4>
          <p>${esc(item.note)}</p>
        </article>`
      )
      .join("");

    const advisor = data.advisor;
    const advisorMarkup = advisor
      ? `<article class="advisor">
        <p class="eyebrow eyebrow--dark">Your career agent · ${esc(advisor.performance.label)}</p>
        <h3>${esc(advisor.headline)}</h3>
        <p class="advisor__summary">${esc(advisor.summary)}</p>
        <div class="advisor__focus">${(advisor.focus || [])
          .filter((item) => item.body)
          .map(
            (item) => `<div>
              <span>${esc(item.label)}</span>
              <p>${esc(item.body)}</p>
            </div>`
          )
          .join("")}</div>
        <h4>Your next moves</h4>
        <ol class="advisor__steps">${(advisor.steps || [])
          .map((step) => `<li><strong>${esc(step.window)}</strong><p>${esc(step.action)}</p></li>`)
          .join("")}</ol>
        ${advisorViews(advisor, data.selected.field, data.selected.field_label, data.coverage)}
      </article>`
      : "";

    const gaps = data.gaps || [];
    const uncovered = gaps.filter((gap) => !gap.field_covered);
    const uncoveredLabel = joinLabels(uncovered.map((gap) => gap.region_label));
    const fieldLabel = data.selected.field_label;
    const localNote = uncovered.length
      ? `<p class="path-note">No ${esc(fieldLabel)} listing is specific to ${esc(
          uncoveredLabel
        )} yet — the routes below are pan-African or global.</p>`
      : "";
    const gapRows = gaps.filter((gap) => gap.missing.length);
    const gapSection = gapRows.length
      ? `<h2 class="section-title">Coverage gaps</h2>
        <p class="path-note">These fields have no country-specific listing in the locations you picked. The pan-African and abroad routes above still apply.</p>
        <ul class="path-gaps">${gapRows
          .map(
            (gap) => `<li>
              <strong>${esc(gap.region_label)}</strong>
              <span>${gap.missing.map((field) => esc(field.label)).join(" · ")}</span>
            </li>`
          )
          .join("")}</ul>`
      : `<h2 class="section-title">Coverage gaps</h2>
        <p class="path-note">Every field has at least one country-specific listing in ${esc(
          locationsLabel(data)
        )}.</p>`;

    const body = $("path-body");
    body.innerHTML = `
      <article class="path-hero">
        <p class="eyebrow eyebrow--dark">${esc(data.selected.field_label)} · Based in ${esc(locationsLabel(data))}</p>
        <h3>${esc(profile.headline)}</h3>
        <p>${esc(profile.summary)}</p>
        ${data.coverage ? `<p class="path-hero__coverage">${data.coverage.countries} countries · ${data.coverage.listings} listings</p>` : ""}
        <div class="chips">${(profile.keywords || [])
          .map((keyword) => `<span class="chip chip--teal">${esc(keyword)}</span>`)
          .join("")}</div>
      </article>

      ${advisorMarkup}

      <h2 class="section-title">Your next 90 days</h2>
      <ol class="steps">${startHere}</ol>

      <div class="path-columns">
        <section>
          <h2 class="section-title">Your locations · ${esc(locationsLabel(data))} · ${data.local.length}</h2>
          ${localNote}
          ${opportunityList(data.local, (data.selected.regions || []).length > 1)}
        </section>
        <section>
          <h2 class="section-title">Abroad · ${data.abroad.length}</h2>
          ${opportunityList(data.abroad, false)}
        </section>
      </div>

      ${gapSection}

      <h2 class="section-title">What this path asks of you</h2>
      <div class="path-facts">${facts}</div>

      <h2 class="section-title">Funding that fits your field · ${data.funding.length}</h2>
      <div class="boards">${funding}</div>

      <h2 class="section-title">Where to search</h2>
      <div class="boards">${boards}</div>

      <p class="path-footnote">Every listing links to the organisation's own page. Confirm eligibility and dates there before you apply.</p>
    `;
    body.className = "";

    body.querySelectorAll("[data-advisor-view]").forEach((button) => {
      button.addEventListener("click", () => setAdvisorView(button.dataset.advisorView));
    });
    body.querySelectorAll("[data-business-step]").forEach((input) => {
      input.addEventListener("change", () => {
        const field = data.selected.field;
        const steps = setBusinessStep(field, Number(input.dataset.businessStep), input.checked);
        if (input.closest) {
          const item = input.closest("li");
          if (item) item.classList.toggle("biz-step--done", input.checked);
        }
        const count = body.querySelector("[data-business-count]");
        if (count) {
          count.textContent = `${steps.size} of ${(data.advisor.business.steps || []).length} done`;
        }
        const plan = $("business-plan-text");
        if (plan) {
          plan.textContent = businessPlanText(
            data.selected.field,
            data.selected.field_label,
            data.advisor,
            data.coverage
          );
        }
      });
    });
    body.querySelectorAll("[data-business-note]").forEach((input) => {
      input.addEventListener("input", () => {
        setBusinessNote(data.selected.field, input.value);
        const plan = $("business-plan-text");
        if (plan) {
          plan.textContent = businessPlanText(
            data.selected.field,
            data.selected.field_label,
            data.advisor,
            data.coverage
          );
        }
      });
    });
  }

  async function loadCareerPath(params) {
    const body = $("path-body");
    if (!body) return;
    body.innerHTML = `<p class="loading">Loading your career path…</p>`;
    try {
      const query = params && params.toString() ? `?${params.toString()}` : "";
      const data = await getJSON(`/career-path${query}`);
      if (!$("path-body")) return; // the student navigated away mid-request
      fillPathOptions(data);
      savePath({
        field: data.selected.field,
        regions: (data.selected.regions || []).map((item) => item.key),
        performance: data.advisor && data.advisor.performance ? data.advisor.performance.key : null,
      });
      renderCareerPath(data);
    } catch (error) {
      body.innerHTML = errorBlock(error.message);
    }
  }

  function businessStepState(field) {
    try {
      const all = JSON.parse(localStorage.getItem(BUSINESS_STORAGE_KEY) || "{}");
      const stored = all && Array.isArray(all[field]) ? all[field] : [];
      return new Set(stored.filter((index) => Number.isInteger(index) && index >= 0));
    } catch (error) {
      return new Set();
    }
  }

  function setBusinessStep(field, index, done) {
    try {
      const all = JSON.parse(localStorage.getItem(BUSINESS_STORAGE_KEY) || "{}") || {};
      const steps = new Set(Array.isArray(all[field]) ? all[field] : []);
      if (done) steps.add(index);
      else steps.delete(index);
      all[field] = [...steps].sort((a, b) => a - b);
      localStorage.setItem(BUSINESS_STORAGE_KEY, JSON.stringify(all));
    } catch (error) {
      /* progress is a convenience; the list still works without storage */
    }
    return businessStepState(field);
  }

  function clearSavedData() {
    [PATH_STORAGE_KEY, BUSINESS_STORAGE_KEY, BUSINESS_NOTE_KEY, ADVISOR_VIEW_KEY].forEach((key) => {
      try {
        localStorage.removeItem(key);
      } catch (error) {
        /* nothing saved to remove if storage is blocked */
      }
    });
    Object.keys(noteFallback).forEach((key) => delete noteFallback[key]);
    advisorView = "work";
  }

  function businessNote(field) {
    try {
      const all = JSON.parse(localStorage.getItem(BUSINESS_NOTE_KEY) || "{}");
      if (all && typeof all[field] === "string") return all[field];
    } catch (error) {
      /* fall through to the in-memory copy */
    }
    return noteFallback[field] || "";
  }

  function setBusinessNote(field, value) {
    const note = String(value || "").trim().slice(0, BUSINESS_NOTE_LIMIT);
    noteFallback[field] = note;
    let all = {};
    try {
      const saved = JSON.parse(localStorage.getItem(BUSINESS_NOTE_KEY) || "{}");
      if (saved && typeof saved === "object") all = saved;
    } catch (error) {
      // corrupt storage is replaced rather than left to fail forever
      all = {};
    }
    try {
      all[field] = note;
      localStorage.setItem(BUSINESS_NOTE_KEY, JSON.stringify(all));
    } catch (error) {
      /* the note still shows this session; it just will not be remembered */
    }
    return note;
  }

  function wrapLine(text, width) {
    const lines = [];
    let line = "";
    String(text || "")
      .split(/\s+/)
      .filter(Boolean)
      .forEach((word) => {
        if (!line.length) line = word;
        else if (`${line} ${word}`.length <= width) line += ` ${word}`;
        else {
          lines.push(line);
          line = word;
        }
      });
    if (line) lines.push(line);
    return lines;
  }

  function businessPlanText(field, fieldLabel, advisor, coverage) {
    const business = advisor.business || { steps: [] };
    const steps = business.steps || [];
    const done = businessStepState(field);
    const lines = [`Business plan — ${fieldLabel}`, `Results band: ${advisor.performance.label}`];
    if (coverage) {
      lines.push(`Coverage: ${coverage.countries} countries · ${coverage.listings} listings`);
    }
    lines.push("", "Career agent brief:");
    if (advisor.headline) lines.push(advisor.headline);
    wrapLine(advisor.summary, 74).forEach((line) => lines.push(line));
    (advisor.focus || [])
      .filter((item) => item.body)
      .forEach((item) => {
        lines.push("", `${item.label}:`);
        wrapLine(item.body, 74).forEach((line) => lines.push(line));
      });
    lines.push("", "Next moves:");
    (advisor.steps || []).forEach((step) => {
      wrapLine(`${step.window}: ${step.action}`, 74).forEach((line) => lines.push(line));
    });
    lines.push("", `Progress: ${done.size} of ${steps.length} steps done`, "");
    steps.forEach((step, index) => {
      lines.push(`[${done.has(index) ? "x" : " "}] ${index + 1}. ${step.step}`);
      wrapLine(step.detail, 70).forEach((line) => lines.push(`    ${line}`));
    });
    lines.push("", "Note for your band:");
    wrapLine(business.note, 74).forEach((line) => lines.push(line));
    const note = businessNote(field);
    if (note) {
      lines.push("", "My next step:");
      wrapLine(note, 74).forEach((line) => lines.push(line));
    }
    lines.push("", "Before you trade:");
    wrapLine(
      "Registration rules, licences and costs differ by country. Confirm them with your national business registry and professional council before you trade.",
      74
    ).forEach((line) => lines.push(line));
    lines.push("", "From the Student Resources Centre · My career path");
    return lines.join("\n");
  }

  function advisorViews(advisor, field, fieldLabel, coverage) {
    const prospects = advisor.prospects || {};
    const business = advisor.business || { steps: [] };
    const sectors = (prospects.sectors || [])
      .map(
        (sector) => `<div>
          <span>${esc(sector.label)}</span>
          <p>${esc(sector.body)}</p>
        </div>`
      )
      .join("");
    const ventures = (prospects.ventures || [])
      .map((venture) => `<li><strong>${esc(venture.name)}</strong><p>${esc(venture.detail)}</p></li>`)
      .join("");
    const done = businessStepState(field);
    const steps = (business.steps || [])
      .map(
        (step, index) => `<li class="${done.has(index) ? "biz-step--done" : ""}">
          <label class="biz-step">
            <input type="checkbox" data-business-step="${index}" ${done.has(index) ? "checked" : ""}>
            <span class="biz-step__text">
              <strong>${esc(step.step)}</strong>
              <p>${esc(step.detail)}</p>
            </span>
          </label>
        </li>`
      )
      .join("");
    return `
      <div class="advisor__switch" role="tablist" aria-label="Career agent views">
        <button type="button" role="tab" data-advisor-view="work" aria-selected="${advisorView === "work"}">Job prospects</button>
        <button type="button" role="tab" data-advisor-view="business" aria-selected="${advisorView === "business"}">Start a business</button>
      </div>

      <section class="advisor__view" data-advisor-view-panel="work" ${advisorView === "work" ? "" : "hidden"}>
        <h4>Where your field is creating work</h4>
        <p class="advisor__summary">${esc(prospects.outlook)}</p>
        <div class="advisor__sectors">${sectors}</div>
        <h4>Working for yourself</h4>
        <p class="advisor__summary">${esc(prospects.self_employment)}</p>
        <ul class="advisor__ventures">${ventures}</ul>
        <p class="advisor__source">Prospects are drawn from the sectors this centre tracks, not live labour-market data. The boards below list current openings.</p>
      </section>

      <section class="advisor__view" data-advisor-view-panel="business" ${advisorView === "business" ? "" : "hidden"}>
        <h4>Set yourself up <span class="advisor__count" data-business-count>${done.size} of ${(business.steps || []).length} done</span></h4>
        <p class="advisor__summary">${esc(business.note)}</p>
        <ol class="advisor__steps advisor__steps--business">${steps}</ol>
        <label class="advisor__note">
          <span class="advisor__note-label">Your own next step <em>optional</em></span>
          <textarea data-business-note rows="2" maxlength="${BUSINESS_NOTE_LIMIT}" placeholder="e.g. Ask the registrar about a licence by 30 November">${esc(
            businessNote(field)
          )}</textarea>
          <span class="advisor__note-hint">Kept on this device and added to your copied, downloaded and printed plan.</span>
        </label>
        <p class="advisor__source">Registration rules, licences and costs differ by country. Confirm them with your national business registry and professional council before you trade.</p>
        <div class="advisor__actions">
          <button type="button" class="advisor__copy" data-copy-plan="business-plan-text">Copy plan</button>
          <button type="button" class="advisor__copy" data-download-plan="business-plan-text" data-plan-filename="business-plan-${field}.txt">Download .txt</button>
          <button type="button" class="advisor__copy" data-print-plan="business-plan-text">Print plan</button>
        </div>
        <pre class="advisor__plan-text" id="business-plan-text" hidden>${esc(
          businessPlanText(field, fieldLabel, advisor, coverage)
        )}</pre>
      </section>`;
  }

  function setAdvisorView(view) {
    advisorView = view === "business" ? "business" : "work";
    try {
      localStorage.setItem(ADVISOR_VIEW_KEY, advisorView);
    } catch (error) {
      /* the switch still works this visit */
    }
    const body = $("path-body");
    body.querySelectorAll("[data-advisor-view]").forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.advisorView === view));
    });
    body.querySelectorAll("[data-advisor-view-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.advisorViewPanel !== view;
    });
  }

  function joinLabels(labels) {
    if (!labels.length) return "";
    if (labels.length === 1) return labels[0];
    return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
  }

  function locationsLabel(data) {
    return data.selected.locations_label || data.selected.region_label;
  }

  function selectedRegions() {
    return [...document.querySelectorAll('#path-region-options input[name="region"]:checked')].map(
      (input) => input.value
    );
  }

  function selectedPerformance() {
    const input = document.querySelector('#path-performance-options input[name="performance"]:checked');
    return input ? input.value : "upper-second";
  }

  function initCareerPath() {
    const saved = readSavedPath();
    const params = new URLSearchParams();
    if (saved) {
      params.set("field", saved.field);
      saved.regions.forEach((key) => params.append("region", key));
      if (saved.performance) params.set("performance", saved.performance);
    }
    loadCareerPath(params);
  }

  function requestPath() {
    const params = new URLSearchParams({
      field: $("path-field").value,
      performance: selectedPerformance(),
    });
    selectedRegions().forEach((key) => params.append("region", key));
    loadCareerPath(params);
  }

  /* ----------------------------------------------------------------- library */

  function renderLibrary(data) {
    const cards = data.documents
      .map(
        (doc) => `<button class="doc-card" type="button" data-slug="${esc(doc.slug)}">
          <div class="chips"><span class="chip">${esc(doc.kind)}</span></div>
          <h3>${esc(doc.title)}</h3>
          <p>${esc(doc.description)}</p>
          <span class="doc-meta">${esc(doc.topics.join(" · "))}</span>
          <span class="doc-open">Open document →</span>
        </button>`
      )
      .join("");

    const body = $("library-body");
    body.innerHTML = `<div class="library-grid">${cards}</div>`;
    body.className = "";

    body.querySelectorAll(".doc-card").forEach((card) => {
      card.addEventListener("click", () => openDocument(card.dataset.slug));
    });
  }

  function inlineMarkdown(text) {
    const links = [];
    let output = text
      .replace(/<((?:https?:\/\/)[^>\s]+)>/g, (_, url) => {
        links.push({ url, text: url });
        return `\u0000L${links.length - 1}\u0000`;
      })
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, url) => {
        links.push({ url, text: label });
        return `\u0000L${links.length - 1}\u0000`;
      });

    output = esc(output)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    return output.replace(/\u0000L(\d+)\u0000/g, (_, index) => {
      const link = links[Number(index)];
      return `<a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">${esc(link.text)}</a>`;
    });
  }

  function renderMarkdown(source) {
    const lines = source.replace(/\r/g, "").split("\n");
    const out = [];
    let listType = null;
    let lastListItem = -1;
    let paragraph = [];

    const closeList = () => {
      if (listType) {
        out.push(`</${listType}>`);
        listType = null;
        lastListItem = -1;
      }
    };

    const flushParagraph = () => {
      if (paragraph.length) {
        out.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
        paragraph = [];
      }
    };

    for (const line of lines) {
      if (!line.trim()) {
        flushParagraph();
        // A blank line between bullets or numbered items does not end the list;
        // closing here restarted the numbering on every item.
        continue;
      }

      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flushParagraph();
        closeList();
        const level = Math.min(heading[1].length + 1, 5);
        out.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
        continue;
      }

      const bullet = line.match(/^\s*[-*]\s+(.*)$/);
      const numbered = line.match(/^\s*\d+\.\s+(.*)$/);

      if (bullet || numbered) {
        flushParagraph();
        const type = bullet ? "ul" : "ol";
        if (listType !== type) {
          closeList();
          listType = type;
          out.push(`<${type}>`);
        }
        out.push(`<li>${inlineMarkdown((bullet || numbered)[1])}</li>`);
        lastListItem = out.length - 1;
        continue;
      }

      if (listType && lastListItem >= 0) {
        const previous = out[lastListItem];
        out[lastListItem] = previous.replace(/<\/li>$/, ` ${inlineMarkdown(line.trim())}</li>`);
        continue;
      }

      // Plain prose after a list starts a new block, so the list ends here.
      closeList();
      paragraph.push(line.trim());
    }

    flushParagraph();
    closeList();
    return out.join("\n");
  }

  function dialog() {
    return $("doc-dialog");
  }

  async function openDocument(slug) {
    const node = dialog();
    const body = $("doc-body");
    body.innerHTML = `<p class="loading">Loading document…</p>`;
    $("doc-title").textContent = "Document";
    if (typeof node.showModal === "function") node.showModal();
    else node.setAttribute("open", "");

    try {
      const data = await getJSON(`/library/${slug}`);
      $("doc-title").textContent = data.document.title;
      $("doc-kind").textContent = data.document.kind;
      $("doc-source").textContent = `Source: ${data.document.source}`;
      $("doc-download").href = `${API}/library/${slug}/download`;
      $("doc-download").setAttribute("download", `${slug}.md`);
      body.innerHTML = `<article class="markdown">${renderMarkdown(data.content)}</article>`;
      body.scrollTop = 0;
    } catch (error) {
      body.innerHTML = errorBlock(error.message);
    }
  }

  function closeDocument() {
    const node = dialog();
    if (typeof node.close === "function") node.close();
    else node.removeAttribute("open");
  }

  /* ------------------------------------------------------------ thesis agent */

  function openThesisAgent() {
    if (window.ThesisAgent) {
      window.ThesisAgent.open();
      return;
    }
    if (agentLoading) return;
    agentLoading = new Promise((resolve) => {
      const script = document.createElement("script");
      script.src = "/static/thesis-agent.js";
      script.onload = () => {
        resolve();
        if (window.ThesisAgent) window.ThesisAgent.open();
      };
      script.onerror = () => {
        const log = $("agent-log");
        if (log) log.innerHTML = errorBlock("The thesis guide could not be loaded.");
        resolve();
      };
      document.head.appendChild(script);
    });
  }

  /* ----------------------------------------------------------------- binding */

  function bindShell() {
    $("path-picker").addEventListener("submit", (event) => event.preventDefault());
    $("path-field").addEventListener("change", requestPath);
    $("path-region-options").addEventListener("change", (event) => {
      if (event.target.name !== "region") return;
      if (!selectedRegions().length) {
        // keep at least one location so the tab always has something to show
        event.target.checked = true;
        return;
      }
      requestPath();
    });
    $("path-performance-options").addEventListener("change", (event) => {
      if (event.target.name === "performance") requestPath();
    });

    const resetButton = $("path-reset");
    let resetArmed = false;
    let resetTimer = null;
    const disarmReset = () => {
      resetArmed = false;
      resetButton.classList.remove("path-reset--armed");
      resetButton.textContent = "Clear my saved data";
    };
    resetButton.addEventListener("click", () => {
      if (!resetArmed) {
        // two taps, so a stray click does not wipe the student's progress
        resetArmed = true;
        resetButton.classList.add("path-reset--armed");
        resetButton.textContent = "Tap again to clear";
        resetTimer = setTimeout(disarmReset, 5000);
        return;
      }
      clearTimeout(resetTimer);
      disarmReset();
      clearSavedData();
      resetButton.textContent = "Saved data cleared";
      initCareerPath();
      setTimeout(() => (resetButton.textContent = "Clear my saved data"), 3000);
    });

    $("doc-close").addEventListener("click", closeDocument);
    dialog().addEventListener("click", (event) => {
      if (event.target === dialog()) closeDocument();
    });
  }

  function bindDocumentOnce() {
    if (documentBound) return;
    documentBound = true;

    document.addEventListener("click", async (event) => {
      const planButton = event.target.closest("[data-copy-plan]");
      if (!planButton) return;
      const planText = $(planButton.dataset.copyPlan);
      if (!planText) return;
      try {
        await navigator.clipboard.writeText(planText.textContent);
        planButton.textContent = "Copied";
      } catch (error) {
        // clipboard can be blocked; reveal the text so it can be selected by hand
        planText.hidden = false;
        planButton.textContent = "Select the text below";
      }
      setTimeout(() => (planButton.textContent = "Copy plan"), 2500);
    });

    document.addEventListener("click", (event) => {
      const downloadButton = event.target.closest("[data-download-plan]");
      if (!downloadButton) return;
      const planText = $(downloadButton.dataset.downloadPlan);
      if (!planText) return;
      const blob = new Blob([planText.textContent], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = downloadButton.dataset.planFilename || "business-plan.txt";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      downloadButton.textContent = "Downloaded";
      setTimeout(() => (downloadButton.textContent = "Download .txt"), 2500);
    });

    document.addEventListener("click", (event) => {
      const printButton = event.target.closest("[data-print-plan]");
      if (!printButton) return;
      const planText = $(printButton.dataset.printPlan);
      if (!planText) return;
      const label = printButton.textContent;
      // print only the plan text, not the app around it
      const lines = planText.textContent.split("\n");
      const heading = lines[0] || "Business plan";
      const band = (lines[1] || "").replace(/^Results band:\s*/, "");
      const progressAt = lines.findIndex((line) => line.startsWith("Progress:"));
      const printed = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

      const sheet = document.createElement("section");
      sheet.id = "print-plan-sheet";
      const head = document.createElement("header");
      head.className = "print-plan-head";
      const title = document.createElement("h1");
      title.textContent = heading;
      const meta = document.createElement("p");
      meta.textContent = [band, `Printed ${printed}`].filter(Boolean).join(" · ");
      head.appendChild(title);
      head.appendChild(meta);
      const pre = document.createElement("pre");
      pre.className = "print-plan-text";
      // the heading and band are in the header, so the body starts at progress
      pre.textContent = (progressAt > 0 ? lines.slice(progressAt) : lines).join("\n");
      sheet.appendChild(head);
      sheet.appendChild(pre);
      document.body.appendChild(sheet);
      document.body.classList.add("printing-plan");
      let cleaned = false;
      const cleanup = () => {
        if (cleaned) return;
        cleaned = true;
        document.body.classList.remove("printing-plan");
        sheet.remove();
        printButton.textContent = label;
        window.removeEventListener("afterprint", cleanup);
      };
      window.addEventListener("afterprint", cleanup);
      printButton.textContent = "Preparing…";
      window.print();
      // some browsers never fire afterprint; do not leave the sheet behind
      setTimeout(cleanup, 60000);
    });

    document.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-copy]");
      if (!button) return;
      const source = $(button.dataset.copy);
      if (!source) return;
      try {
        await navigator.clipboard.writeText(source.textContent);
        button.textContent = "Copied";
      } catch (error) {
        button.textContent = "Select and copy";
      }
      setTimeout(() => (button.textContent = "Copy"), 2000);
    });
  }

  /* -------------------------------------------------------------- the section */

  const RENDERERS = {
    scholarships: renderScholarships,
    research: renderResearch,
    career: renderCareer,
    employment: renderEmployment,
    library: renderLibrary,
  };

  function paintSection(key) {
    const container = $(SECTION_IDS[key]);
    if (!container) return;
    const result = cache[key];
    if (result.status === "fulfilled") {
      try {
        RENDERERS[key](result.value);
      } catch (error) {
        container.innerHTML = errorBlock(error.message);
      }
    } else {
      container.innerHTML = errorBlock(result.reason ? result.reason.message : "Unknown error");
    }
    container.classList.remove("loading");
  }

  async function loadSections() {
    const [overview, scholarships, research, career, employment, library] = await Promise.allSettled([
      getJSON("/overview"),
      getJSON("/scholarships"),
      getJSON("/research"),
      getJSON("/career"),
      getJSON("/employment"),
      getJSON("/library"),
    ]);

    Object.assign(cache, { scholarships, research, career, employment, library });

    if (overview.status === "fulfilled") renderHero(overview.value);
    Object.keys(SECTION_IDS).forEach(paintSection);
  }

  /**
   * Paint the centre into a container inside the app.
   * @param {HTMLElement} container
   * @param {{tab?: string}} options
   */
  function mount(container, options = {}) {
    container.innerHTML = SHELL;
    container.classList.add("rc-host");
    // A fresh shell means the career path has to start again: its markup, and
    // therefore its <select> and checkboxes, was just replaced.
    pathStarted = false;
    bindShell();
    bindDocumentOnce();
    initTabs();
    selectTab(TABS.includes(options.tab) ? options.tab : activeTab);

    if (Object.keys(cache).length) Object.keys(SECTION_IDS).forEach(paintSection);
    else loadSections();

    // A remount keeps the career path's own state, so only reload when it is the
    // visible tab and it has not been started on this page yet.
    if (activeTab === "path") {
      pathStarted = true;
      initCareerPath();
    }
  }

  window.ResourcesCentre = {
    mount,
    openSection(container, tab) {
      mount(container, { tab });
    },
  };
})();
