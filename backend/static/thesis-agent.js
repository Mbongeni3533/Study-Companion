/* Thesis guide agent for the Student Resources Centre.
 *
 * A self-contained guide that walks a student from an empty page to a defended
 * thesis: scope, question, literature, method, proposal, data, findings,
 * write-up, submission. It answers questions from a built-in knowledge base,
 * builds a dated plan from the student's own deadline, and tracks stage
 * progress. Everything stays in this browser - no network calls, no account.
 */
(function () {
  "use strict";

  const STORE = {
    profile: "studyCompanion.thesisProfile",
    checks: "studyCompanion.thesisChecks",
    chat: "studyCompanion.thesisChat",
  };

  const $ = (id) => document.getElementById(id);

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));

  function readStore(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function writeStore(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      /* private mode or full storage: the guide still works for this visit */
    }
  }

  /* ------------------------------------------------------------- the path */

  const STAGES = [
    {
      id: "topic",
      label: "Scope the topic",
      title: "Stage 1 · Choose and scope your topic",
      weeks: 1,
      goal: "Pick something you can finish with the time, data access and skills you actually have — not the biggest question you can imagine.",
      produce: "A one-page topic statement: what you will study, where, and why it matters to whom.",
      checks: [
        "The topic fits my degree and my supervisor's expertise",
        "I can explain the problem in two sentences without jargon",
        "The data or sources I need are ones I can actually reach",
        "The scope is small enough for my deadline",
        "I have checked that an existing study has not already answered it",
      ],
      pitfalls: [
        "A topic that needs a laboratory, dataset or travel you do not have",
        "Three questions wearing one topic — you will answer none of them well",
        "Choosing a topic only because a supervisor suggested it, with no interest of your own: you will be alone with it for months",
      ],
      ask: ["How do I narrow my topic?", "What makes a good research topic?", "How do I know my topic is already taken?"],
    },
    {
      id: "question",
      label: "Frame the question",
      title: "Stage 2 · Turn the topic into research questions",
      weeks: 1,
      goal: "Convert the topic into questions that a method can answer and an examiner can check.",
      produce: "One main question, two to four sub-questions, and objectives that map one-to-one onto them.",
      checks: [
        "One sentence carries the main question, with no 'and also'",
        "Each sub-question names who, where and when",
        "Each objective starts with a verb I can demonstrate (compare, measure, describe)",
        "Every sub-question can be answered with the data I will collect",
        "A supervisor reading only my questions would know what to expect",
      ],
      pitfalls: [
        "A yes/no question that quietly needs a sample you can never reach",
        "'Explore' with no focus — nothing can fail, so nothing can be concluded",
        "Objectives that each need a different method, doubling the work",
      ],
      ask: ["How do I write a research question?", "What is the difference between objectives and questions?", "Should I have a hypothesis?"],
    },
    {
      id: "literature",
      label: "Search the literature",
      title: "Stage 3 · Find what is known, and what is not",
      weeks: 2,
      goal: "Establish the gap honestly: what has been studied, what is contested, and what nobody has answered yet.",
      produce: "A search log (databases, strings, dates, hits), a reference library, and one written gap statement.",
      checks: [
        "I searched at least three databases, not only Google Scholar",
        "My search strings and dates are written down so they can be repeated",
        "I screened the key sources and kept notes on each",
        "My references live in a manager (Zotero, Mendeley, EndNote)",
        "I can write the gap as one sentence that my study fills",
      ],
      pitfalls: [
        "Citing papers you have only read the abstract of — examiners ask",
        "'No one has studied this' when you have not searched properly",
        "Only citing what agrees with you; the contradictions are where the gap hides",
      ],
      ask: ["How do I search the literature properly?", "What counts as a research gap?", "What is snowballing?"],
    },
    {
      id: "review",
      label: "Write the review",
      title: "Stage 4 · Write a literature review, not a list",
      weeks: 2,
      goal: "Synthesise sources into themes and debates that lead directly to your question.",
      produce: "A themed review with a synthesis table, a named theoretical framework, and a closing paragraph that hands over to your study.",
      checks: [
        "Sections are organised by theme or debate, not author by author",
        "Every paragraph makes a claim supported by two or more sources",
        "Contradicting findings are discussed, not hidden",
        "One framework or theory is named and used, not just mentioned",
        "The last paragraph points at my question and my gap",
      ],
      pitfalls: [
        "'Smith says… Jones says…' with no argument connecting them",
        "Long quotations doing the thinking for you",
        "A framework named in the introduction and never heard from again",
      ],
      ask: ["How do I structure a literature review?", "How much should I quote?", "What is a theoretical framework?"],
    },
    {
      id: "method",
      label: "Design the method",
      title: "Stage 5 · Design a method that can answer the question",
      weeks: 2,
      goal: "Choose a design, sample and analysis plan that fit the question — and that an ethics committee will approve.",
      produce: "A methods chapter: design and justification, population and sampling, instruments, analysis plan, rigour, ethics.",
      checks: [
        "The design is justified against the question, not just named",
        "Sampling procedure and size are stated, with a reason",
        "Instruments were piloted and revised",
        "The analysis plan matches the type of data I will have",
        "Consent, anonymity, storage and ethics approval are arranged",
        "Limitations are stated before anyone asks",
      ],
      pitfalls: [
        "Calling a convenience sample 'random'",
        "Sending out a questionnaire nobody piloted",
        "Running a statistical test that does not fit the data",
        "Leaving ethics approval until the month before data collection",
      ],
      ask: ["How do I choose a research design?", "How big should my sample be?", "What do I need for ethics approval?"],
    },
    {
      id: "proposal",
      label: "Get the proposal approved",
      title: "Stage 6 · Write the proposal",
      weeks: 1,
      goal: "Produce a document a committee can say yes to without guessing what you mean.",
      produce: "A 10–20 page proposal: background, problem statement, questions, literature, methods, timeline, budget, references.",
      checks: [
        "My problem statement ends with the gap and my question",
        "The timeline is in weeks and adds up to my deadline",
        "Costs like transport, transcription and printing are budgeted",
        "My supervisor has read and approved the final version",
        "I followed my institution's template exactly",
        "The ethics application is drafted alongside it",
      ],
      pitfalls: [
        "A proposal that reads like an essay with methods bolted on",
        "A timeline with no dates, or one that assumes no delays",
        "Forgetting that data collection costs money and permission takes weeks",
      ],
      ask: ["What goes in a research proposal?", "How detailed should my timeline be?", "How do I answer reviewers' comments?"],
    },
    {
      id: "data",
      label: "Collect and analyse",
      title: "Stage 7 · Collect, clean and analyse",
      weeks: 2,
      goal: "Gather data you can defend, then analyse it the way you said you would.",
      produce: "A clean dataset with a codebook, a collection log, and written analysis outputs.",
      checks: [
        "Every variable, code or theme is defined somewhere",
        "Data is backed up in two places, with versions kept",
        "Anonymised IDs are linked to consent forms in one secure place",
        "Analysis follows the plan; deviations are recorded and explained",
        "Every quote or figure can be traced back to a source ID",
      ],
      pitfalls: [
        "Starting analysis without a plan and hunting for a result",
        "Losing the key that links anonymised data to consent forms",
        "Changing the analysis after seeing the results without saying so",
      ],
      ask: ["How do I analyse qualitative data?", "Which statistical test should I use?", "How do I know when I have enough interviews?"],
    },
    {
      id: "findings",
      label: "Report and discuss",
      title: "Stage 8 · Write results, then discussion",
      weeks: 2,
      goal: "Report what the data show, separately from what you think it means.",
      produce: "A results chapter that answers each sub-question in order, and a discussion that reads it against the literature.",
      checks: [
        "Results are ordered by my sub-questions",
        "Every table and figure is numbered, titled and referred to in the text",
        "No new literature appears in the results",
        "The discussion compares my findings with at least three prior studies",
        "Effect sizes and confidence intervals are reported, not just p-values",
        "Limitations and implications are written before the conclusion",
      ],
      pitfalls: [
        "Interpreting inside the results chapter",
        "Claims the data cannot carry, phrased as 'proves'",
        "Treating a p-value as a measure of importance",
      ],
      ask: ["What is the difference between results and discussion?", "How do I report statistics properly?", "How do I write the limitations section?"],
    },
    {
      id: "writeup",
      label: "Draft the thesis",
      title: "Stage 9 · Draft the whole document",
      weeks: 2,
      goal: "Get a complete draft on paper in the order that is easiest to write, not the order it is read.",
      produce: "A full first draft, every chapter present, figures placed, references complete.",
      checks: [
        "Chapter structure matches my institution's guide",
        "The abstract is written last, with no citations",
        "The introduction funnels from context to problem to gap to aim",
        "Tense and voice are consistent throughout",
        "Every in-text citation appears in the reference list, and nothing extra",
        "Word counts per chapter fit the limits",
      ],
      pitfalls: [
        "Rewriting chapter one for a month instead of finishing the draft",
        "Leaving referencing to the end",
        "Switching between US and UK spelling halfway through",
      ],
      ask: ["How is a thesis structured?", "How do I write an abstract?", "How do I beat writer's block?"],
    },
    {
      id: "finish",
      label: "Submit and defend",
      title: "Stage 10 · Edit, submit, defend",
      weeks: 1,
      goal: "Turn a draft into a submission you can stand behind — and a defence you can walk into calm.",
      produce: "Final checked PDF, similarity report understood, submission receipt, viva notes.",
      checks: [
        "Supervisor sign-off is in hand",
        "I read the whole document aloud or had it proofread",
        "Reference style is consistent, checked against the guide",
        "Similarity report reviewed and explained, not just filed",
        "Formatting, margins and word count meet the rules",
        "Submission portal, deadline and printed copies confirmed",
        "A five-minute summary and likely questions are rehearsed",
      ],
      pitfalls: [
        "Submitting in the last hour on a portal that closes hard",
        "Panicking over similarity caused by standard method wording",
        "Having no copy of exactly what was submitted",
      ],
      ask: ["How do I prepare for my viva?", "How much similarity is too much?", "Should I publish my thesis?"],
    },
  ];

  const LEVELS = [
    ["undergraduate", "Undergraduate project"],
    ["honours", "Honours / fourth year"],
    ["masters", "Master's"],
    ["phd", "Doctoral"],
  ];

  /* ------------------------------------------------------- knowledge base */

  const KB = [
    {
      id: "scope",
      stage: "topic",
      title: "Narrowing a topic into something you can finish",
      keys: ["topic", "narrow", "scope", "research topic", "choose a topic", "title", "too broad", "too wide"],
      body: `<p>A topic is too broad when you cannot name who you will look at, where, and with what material. Narrow it in three cuts:</p>
        <ol>
          <li><strong>Population or case</strong> — not "students" but "second-year engineering students at one university".</li>
          <li><strong>Angle</strong> — not "mental health" but "how students describe help-seeking after a failed assessment".</li>
          <li><strong>Boundary</strong> — one site, one semester, one document set, one intervention.</li>
        </ol>
        <p>Test it by writing the sentence you want the examiner to read: <em>"This study examines how [who] in [where] [do or experience what], in order to [why it matters]."</em> If the sentence needs an "and also", cut something.</p>
        <p class="agent-tip">A good topic is interesting to you, reachable in your setting, and small enough that a negative finding is still a finding. Ambition is the most common reason projects fail to finish.</p>`,
    },
    {
      id: "gap",
      stage: "literature",
      title: "What a research gap actually is",
      keys: ["gap", "research gap", "novelty", "nobody has studied", "original", "already taken", "already studied", "duplicate", "already researched"],
      body: `<p>A gap is not "nobody has written about this". Almost always somebody has. A defensible gap is one of these:</p>
        <ul>
          <li><strong>Population gap</strong> — the finding exists, but never for the group you are studying (rural clinics, first-generation students, a specific province).</li>
          <li><strong>Method gap</strong> — everything published is survey-based; interviews would answer the <em>why</em>.</li>
          <li><strong>Contradiction</strong> — two credible studies disagree, and the disagreement has not been resolved.</li>
          <li><strong>Time gap</strong> — the last credible study predates a policy, technology or market change.</li>
          <li><strong>Application gap</strong> — the theory is well tested in laboratories but never in the setting where it must work.</li>
        </ul>
        <p class="agent-tip">Write it as one sentence with three parts: <em>"Studies have shown X (citations), but none has examined X in Y, which matters because Z."</em> If you cannot fill Y and Z, the gap is not there yet.</p>`,
    },
    {
      id: "search",
      stage: "literature",
      title: "Searching the literature so you can stop searching",
      keys: ["search", "database", "boolean", "keywords", "google scholar", "snowball", "scopus", "pubmed", "sabinet"],
      body: `<p>Search in this order, and keep a log you could hand to an examiner.</p>
        <ol>
          <li><strong>Break the question into concepts.</strong> Two to four concepts, each with synonyms and spelling variants.</li>
          <li><strong>Build strings</strong> with AND between concepts, OR inside them: <code>("first-generation" OR "first generation") AND (university OR higher education) AND (retention OR dropout)</code>.</li>
          <li><strong>Run it in more than one place.</strong> Google Scholar finds breadth; Scopus, Web of Science, PubMed, EBSCO, JSTOR, Sabinet and your library's subject database find depth. Grey literature — government reports, theses, NGO evaluations — often holds the local data no journal published.</li>
          <li><strong>Snowball.</strong> Take the three best papers and read who they cite (backward) and who cites them (forward, via "cited by"). This is usually where the real gap is found.</li>
          <li><strong>Screen and stop.</strong> Title and abstract first, full text only for what survives. Stop when new searches return only papers you have already seen — that is saturation of the literature.</li>
        </ol>
        <p class="agent-tip">Save each search with its date and number of hits. Re-running an old search with a new date is the cheapest way to look thorough.</p>`,
    },
    {
      id: "review",
      stage: "review",
      title: "Structuring a literature review",
      keys: ["literature review", "lit review", "review chapter", "synthesise", "synthesis", "quote", "quotation", "framework", "theoretical framework", "conceptual framework"],
      body: `<p>A review is an argument about what is known, organised by ideas. Four moves, in order:</p>
        <ol>
          <li><strong>Frame</strong> the field: what the debate is about, and the main positions.</li>
          <li><strong>Synthesise</strong> by theme. Each paragraph opens with a claim, then two or three sources that support, qualify or contradict it.</li>
          <li><strong>Evaluate</strong>: note sample sizes, methods and settings, so the reader trusts your judgement about what holds.</li>
          <li><strong>Close on the gap</strong>: what remains unanswered, and why your question follows.</li>
        </ol>
        <p>A synthesis table makes this much easier. Columns: study, setting, sample, method, key finding, limitation. Fill it as you read, and the review almost writes itself from the rows.</p>
        <p class="agent-tip">Quote only when the wording itself is the evidence — a definition, a policy clause. Everything else is paraphrased with a citation.</p>`,
    },
    {
      id: "question",
      stage: "question",
      title: "Writing a research question",
      keys: ["research question", "question", "pico", "spider", "objectives", "hypothesis", "aim"],
      body: `<p>A good question is answerable, specific and bounded. Use a structure to get there:</p>
        <ul>
          <li><strong>PICO</strong> for quantitative work: Population, Intervention (or exposure), Comparison, Outcome.</li>
          <li><strong>SPIDER</strong> for qualitative work: Sample, Phenomenon of interest, Design, Evaluation, Research type.</li>
          <li><strong>Descriptive</strong> for exploratory work: "How do [who] in [where] experience [what], and what does that mean for [practice]?"</li>
        </ul>
        <p>Then check it: Can I collect data to answer this? Can it be answered in my time? Would a negative answer still be a result? If yes to all three, it is a research question rather than a wish.</p>
        <p class="agent-tip">Objectives are the question in verbs: <em>to compare</em>, <em>to describe</em>, <em>to determine the relationship between</em>. Count them against your sub-questions — one each, no orphans.</p>
        <p>A hypothesis is for quantitative designs that test a predicted relationship. Qualitative work usually asks a question instead, and says so.</p>`,
    },
    {
      id: "design",
      stage: "method",
      title: "Choosing a design",
      keys: ["design", "qualitative", "quantitative", "mixed method", "methodology", "case study", "survey", "ethnography", "experiment"],
      body: `<ul>
          <li><strong>Quantitative</strong> — you are measuring how much, how many, or whether a relationship exists. Surveys, experiments, secondary datasets. Strength: generalisation. Cost: depth.</li>
          <li><strong>Qualitative</strong> — you are explaining how and why, in a setting. Interviews, focus groups, observation, document analysis. Strength: meaning. Cost: you cannot generalise statistically, and you must not claim to.</li>
          <li><strong>Mixed methods</strong> — one design leads and the other follows (explanatory sequential: survey then interviews; exploratory: interviews then survey). Say which leads and why, or it looks like two studies stapled together.</li>
        </ul>
        <p>The design must follow the question, not your comfort. If your question asks "how do students experience…", a questionnaire with Likert items will not answer it.</p>
        <p class="agent-tip">Name the design and cite the methodology text you are following. "Case study" is a design only when you can state the case, its boundaries and why it is a case.</p>`,
    },
    {
      id: "sample",
      stage: "method",
      title: "Sample size and sampling",
      keys: ["sample size", "sample", "sampling", "how many", "how big", "participants", "respondents", "power", "random", "convenience", "saturation", "enough interviews", "how many interviews"],
      body: `<p>Quantitative: the size comes from the analysis. For a survey, use a sample-size calculator with your population, confidence level (95%) and margin of error (5%), then expect a response rate well below 100% and inflate accordingly. For comparisons, run a power calculation for the effect size you care about.</p>
        <p>Qualitative: there is no formula. You stop at <strong>saturation</strong> — the point where new interviews stop producing new codes. Six to twelve interviews is common for a focused question; say how you judged saturation rather than picking a number to look respectable.</p>
        <p>Name the procedure honestly: random, stratified, purposive, snowball, convenience. A convenience sample is fine for an exploratory study — calling it random is not.</p>
        <p class="agent-tip">Write one sentence of justification per choice. "Thirty participants were selected purposively for their direct involvement in the process" beats a paragraph of textbook definitions.</p>`,
    },
    {
      id: "ethics",
      stage: "method",
      title: "Ethics, consent and data protection",
      keys: ["ethics", "ethics approval", "approval", "consent", "anonymity", "confidential", "permission", "irb", "popia", "gdpr", "vulnerable"],
      body: `<p>Most delays in a thesis come from ethics, not analysis. Prepare it in stage 5, submit in stage 6.</p>
        <ul>
          <li><strong>Approval</strong> from your institution's ethics committee (and the health, education or municipal authority whose site you use) before any data collection. Retrospective approval is not a thing.</li>
          <li><strong>Informed consent</strong>: purpose, what participation involves, risks, voluntariness, right to withdraw, how data will be stored and used, who to contact. Written, signed, and a copy to the participant.</li>
          <li><strong>Anonymity vs confidentiality</strong>: anonymity means you cannot identify the person at all; confidentiality means you can, but will not disclose. Know which one you are promising.</li>
          <li><strong>Data protection</strong>: in South Africa, POPIA applies to personal information; in the EU, GDPR. Encrypt or lock storage, separate identifiers from data, keep consent forms apart, and state a retention period.</li>
          <li><strong>Vulnerable participants</strong> — minors, patients, employees of the site — need extra safeguards and often a guardian's consent.</li>
        </ul>
        <p class="agent-tip">Your ethics application and your methods chapter should agree word for word on sample and procedure. Reviewers compare them.</p>`,
    },
    {
      id: "instrument",
      stage: "method",
      title: "Questionnaires and interview guides",
      keys: ["questionnaire", "interview guide", "survey design", "pilot", "likert", "open-ended", "focus group"],
      body: `<p>Questionnaire rules: one idea per question; no leading wording ("How much do you agree that the new system is excellent?"); avoid double-barrelled items; offer mutually exclusive, exhaustive options; put demographics at the end; keep it under 10 minutes unless it is the whole study.</p>
        <p>Interview guide rules: five to eight open questions with probes, starting broad ("Tell me how you ended up in this programme") and narrowing. Silence is a tool — let people finish.</p>
        <p>Pilot with five people who resemble your sample, then revise. Report the pilot; it is evidence of care.</p>
        <p class="agent-tip">For a validated instrument, cite the original and report any changes you made. Reliability (e.g. Cronbach's alpha) belongs in the results, not the appendix.</p>`,
    },
    {
      id: "analysis-qual",
      stage: "data",
      title: "Analysing qualitative data",
      keys: ["thematic analysis", "coding", "qualitative analysis", "qualitative data", "analyse qualitative", "analyze qualitative", "code", "theme", "nvivo", "atlas", "transcri", "interviews", "interview data"],
      body: `<p>Thematic analysis (Braun &amp; Clarke) is the workhorse. Six phases:</p>
        <ol>
          <li>Transcribe and read everything twice.</li>
          <li>Code: label meaningful segments, close to the data.</li>
          <li>Cluster codes into candidate themes.</li>
          <li>Review themes against the coded extracts and the whole dataset.</li>
          <li>Define and name each theme — what it is, and what it is not.</li>
          <li>Write it up with representative quotes and their IDs.</li>
        </ol>
        <p>Keep a codebook with definitions and example extracts. For team work, code a shared subset independently and report agreement.</p>
        <p class="agent-tip">A theme is a claim about the data, not a topic. "Barriers" is a topic; "Participants read the online form as a test they expected to fail" is a theme.</p>`,
    },
    {
      id: "analysis-quant",
      stage: "data",
      title: "Choosing the right statistical test",
      keys: ["statistics", "statistical test", "quantitative data", "analyse quantitative", "analyze quantitative", "t-test", "anova", "regression", "chi-square", "correlation", "p-value", "spss", "r studio"],
      body: `<ul>
          <li><strong>One group vs a value</strong> — one-sample t-test (or non-parametric equivalent).</li>
          <li><strong>Two independent groups</strong> — independent t-test; Mann-Whitney if assumptions fail.</li>
          <li><strong>Same group twice</strong> — paired t-test; Wilcoxon signed-rank as the alternative.</li>
          <li><strong>Three or more groups</strong> — ANOVA with post-hoc tests; Kruskal-Wallis as the alternative.</li>
          <li><strong>Two categorical variables</strong> — chi-square.</li>
          <li><strong>Relationship between continuous variables</strong> — correlation to describe, regression to predict or adjust for confounders.</li>
        </ul>
        <p>Check assumptions first: normality, independence, homogeneity of variance, and for regression, multicollinearity. Report descriptives, the test statistic, degrees of freedom, p-value, effect size and confidence intervals.</p>
        <p class="agent-tip">State the alpha (usually 0.05) and whether you corrected for multiple comparisons <em>before</em> you look at the results, not after.</p>`,
    },
    {
      id: "plagiarism",
      stage: "finish",
      title: "Similarity, plagiarism and AI use",
      keys: ["plagiarism", "similarity", "turnitin", "ai", "chatgpt", "copy", "paraphras", "cite"],
      body: `<p>Plagiarism is presenting someone else's words, ideas or structure as your own, whether or not you meant to. Similarity reports flag matching text; they do not decide guilt. Common false positives: your own method boilerplate, standard instrument wording, reference lists, and quoted definitions you did cite.</p>
        <p>Practically: cite every idea that is not yours, paraphrase into your own sentence structure (not just swapped synonyms), and quote with page numbers when the wording matters.</p>
        <p>On AI tools: most institutions now require <strong>declaration</strong> of what you used and for what. Using one to brainstorm or tighten your own prose is usually allowed; submitting generated text as your analysis is not. Check your institution's policy and state your use in the methods or acknowledgements.</p>
        <p class="agent-tip">Keep drafts. A version history is the strongest evidence that the work and thinking are yours.</p>`,
    },
    {
      id: "referencing",
      stage: "writeup",
      title: "Referencing without losing a weekend",
      keys: ["reference", "referencing", "citation", "apa", "harvard", "zotero", "mendeley", "bibliography", "doi"],
      body: `<p>Pick the style your department mandates (APA 7, Harvard, Vancouver, Chicago) and do not mix them. A reference manager (Zotero is free and open source) imports from DOIs and most databases, and reformats the whole list when the style changes.</p>
        <p>Discipline that saves time later:</p>
        <ul>
          <li>Enter the reference when you read the paper, not months later.</li>
          <li>Attach the PDF to the entry, so you can check the quote.</li>
          <li>Cite page numbers for direct quotations.</li>
          <li>Use a placeholder like <code>[CITE]</code> when you know a claim needs a source but not yet which one, and search for the placeholder before submission.</li>
        </ul>
        <p class="agent-tip">Audit at the end with two passes: every in-text citation appears in the list, and every listed reference is cited somewhere. Both directions catch different errors.</p>`,
    },
    {
      id: "abstract",
      stage: "writeup",
      title: "Writing the abstract",
      keys: ["abstract", "executive summary", "keywords"],
      body: `<p>Write it last. One paragraph, usually 200–300 words, no citations, no abbreviations you do not define. Five sentences do the job:</p>
        <ol>
          <li>Context and problem.</li>
          <li>Gap and aim.</li>
          <li>Method: design, setting, sample, instruments, analysis.</li>
          <li>Main findings with a number or a theme, not "results are discussed".</li>
          <li>Conclusion and what it means for practice or policy.</li>
        </ol>
        <p class="agent-tip">Then add four to six keywords your reader would actually search — and avoid words already in your title.</p>`,
    },
    {
      id: "structure",
      stage: "writeup",
      title: "How a thesis is structured",
      keys: ["structure", "chapters", "imrad", "introduction", "conclusion", "methodology chapter", "word count"],
      body: `<p>Most theses follow IMRAD with an academic wrapper: title page, abstract, acknowledgements, contents, list of tables and figures, then chapters 1–5, references, appendices.</p>
        <ul>
          <li><strong>Chapter 1 Introduction</strong> — context, problem statement, gap, aim, questions, objectives, significance, scope and delimitation, structure of the document.</li>
          <li><strong>Chapter 2 Literature review</strong> — themes, framework, gap.</li>
          <li><strong>Chapter 3 Methods</strong> — design, population, sampling, instruments, procedure, analysis, rigour, ethics, limitations.</li>
          <li><strong>Chapter 4 Results</strong> — findings, in the order of your sub-questions.</li>
          <li><strong>Chapter 5 Discussion and conclusion</strong> — interpretation against the literature, limitations, recommendations, conclusion.</li>
        </ul>
        <p>Write out of order if it helps: methods and results first, introduction when you know what you found.</p>
        <p class="agent-tip">Follow your faculty's style guide over any generic template. Word-count limits and heading numbering are pass/fail rules in some departments.</p>`,
    },
    {
      id: "results-discussion",
      stage: "findings",
      title: "Results vs discussion",
      keys: ["results", "discussion", "findings chapter", "interpret"],
      body: `<p><strong>Results</strong>: what you observed. No interpretation, no new literature. Tables and figures carry detail; the text carries the message ("Response rates were lowest among part-time students, 31% against 68%").</p>
        <p><strong>Discussion</strong>: what it means. Three moves per key finding: state it, compare it with prior work (agreeing and disagreeing), then say what follows for theory, practice or policy.</p>
        <p>Keep the same order in both chapters as your sub-questions. An examiner should be able to trace one question from aim to finding to conclusion without hunting.</p>
        <p class="agent-tip">If a finding surprises you, that is the paragraph worth the most attention — explain it rather than burying it.</p>`,
    },
    {
      id: "limitations",
      stage: "findings",
      title: "Writing limitations without undermining yourself",
      keys: ["limitation", "weakness", "bias", "validity", "reliability", "generalis"],
      body: `<p>Limitations are about the reach of your claims, not a confession. One paragraph, four parts:</p>
        <ol>
          <li>What the constraint was (single site, cross-sectional, self-report, small sample).</li>
          <li>How it could affect the findings.</li>
          <li>What you did to reduce it.</li>
          <li>Which claims you therefore do not make.</li>
        </ol>
        <p class="agent-tip">Never write "due to time constraints the sample was small" and stop there. Say what a small purposive sample does and does not let the reader conclude.</p>`,
    },
    {
      id: "proposal",
      stage: "proposal",
      title: "What goes in a research proposal",
      keys: ["proposal", "concept note", "protocol", "reviewer", "comments", "committee"],
      body: `<p>Ten to twenty pages, in this order. Each section answers the next question a reader will ask.</p>
        <ol>
          <li><strong>Title</strong> — specific, and honest about the scope.</li>
          <li><strong>Background and problem statement</strong> — context, then the specific problem, ending with the gap and your question.</li>
          <li><strong>Aim, questions and objectives</strong> — one each, and they align.</li>
          <li><strong>Literature review</strong> — themes, framework, gap. Short, but with real sources.</li>
          <li><strong>Methods</strong> — design, population, sampling, instruments, procedure, analysis, rigour, ethics, limitations.</li>
          <li><strong>Timeline</strong> — by week or month, with data collection and analysis windows you can defend.</li>
          <li><strong>Budget</strong> — transcription, transport, printing, software, incentives. Even if you fund it yourself.</li>
          <li><strong>References and appendices</strong> — instruments, consent form, permission letters.</li>
        </ol>
        <p class="agent-tip">Answering reviewers is a skill: reply to every point in the same order, say what you changed and where, and accept the ones that are right. "Noted, changed on page 7" is a complete answer.</p>`,
    },
    {
      id: "viva",
      stage: "finish",
      title: "Preparing for the defence",
      keys: ["viva", "defence", "defense", "oral", "examiner", "presentation"],
      body: `<p>Examiners are testing whether the work is yours, whether you understand it, and whether you know its limits.</p>
        <ul>
          <li>Prepare a five-minute summary: problem, gap, aim, method, three findings, contribution. Rehearse it aloud until it is 4:30.</li>
          <li>Predict the questions. Almost always: Why this method? Why this sample? How did you handle bias? What is your contribution? What would you do differently? What next?</li>
          <li>Re-read your own methods chapter the week before. The detail they probe is there.</li>
          <li>Bring a marked copy with tabbed pages for your key tables and quotes.</li>
          <li>Answer "I don't know, but I would look at it this way" instead of inventing. Examiners forgive gaps; they do not forgive bluffing.</li>
        </ul>
        <p class="agent-tip">If a correction is fair, say so and write it down. Defending an error costs more than accepting one.</p>`,
    },
    {
      id: "supervisor",
      stage: "topic",
      title: "Working with your supervisor",
      keys: ["supervisor", "meeting", "feedback", "email supervisor", "advisor"],
      body: `<p>Supervisors respond to specifics. Bring one page: what you did since last time, what you decided, what you need decided now, and the exact question you want answered.</p>
        <ul>
          <li>Book a standing slot rather than asking for time each week.</li>
          <li>Send material at least a week before the meeting, with the questions at the top.</li>
          <li>Take notes and confirm decisions in a short follow-up email — this becomes your record if plans change.</li>
          <li>When you disagree, bring evidence, not preference.</li>
        </ul>
        <p class="agent-tip">Silence is not approval. If you have not had a reply in two weeks, send a two-line nudge with a deadline. That is professional, not pushy.</p>`,
    },
    {
      id: "time",
      stage: "topic",
      title: "When you are behind schedule",
      keys: ["time", "deadline", "behind", "procrastinat", "overwhelm", "stuck", "motivation", "timeline", "writer's block", "writers block", "writer", "block"],
      body: `<p>Being behind is usually a scope problem, not a discipline problem. In this order:</p>
        <ol>
          <li><strong>Cut scope, not quality.</strong> One site instead of three, one method instead of two, one population instead of a comparison. Tell your supervisor before you do it.</li>
          <li><strong>Protect the analysis window.</strong> Analysis and writing always take longer than expected. Trim data collection, never the write-up.</li>
          <li><strong>Work in deliverables, not hours.</strong> "Draft 800 words of the methods section" is a task; "work on thesis" is not.</li>
          <li><strong>Start each session by editing yesterday's last paragraph.</strong> It removes the blank-page problem.</li>
        </ol>
        <p class="agent-tip">If your remaining weeks are fewer than your remaining stages, ask me to rebuild the plan after you choose what to cut — a compressed plan that is honest beats one that is fiction.</p>`,
    },
    {
      id: "publish",
      stage: "finish",
      title: "Publishing after submission",
      keys: ["publish", "journal", "predatory", "conference", "open access", "dhet", "doi"],
      body: `<p>Publish if the work adds something, not because it exists. In order of effort: a conference poster or paper from one chapter, then a journal article from the findings and discussion.</p>
        <ul>
          <li><strong>Check the journal before you submit.</strong> Think.Check.Submit is the standard checklist; the Directory of Open Access Journals (DOAJ) lists legitimate open-access titles.</li>
          <li>In South Africa, subsidy and recognition follow the DHET accredited journal lists — confirm your target appears there if that matters for your department.</li>
          <li>Read the author guidelines for structure, word count and reference style; most desk rejections are formatting and fit, not science.</li>
          <li>Know the open-access terms and the fee before submitting. Legitimate journals state costs plainly.</li>
          <li>Co-authorship with your supervisor is normal; agree order and contributions early and in writing.</li>
        </ul>
        <p class="agent-tip">Never pay a "fast-track" fee without checking the journal's indexing and editorial board. A publication in a predatory journal is worse than no publication.</p>`,
    },
  ];

  /* --------------------------------------------------------------- state */

  const state = {
    booted: false,
    profile: readStore(STORE.profile, null),
    checks: readStore(STORE.checks, {}),
    chat: readStore(STORE.chat, []),
    pending: false,
  };

  function save() {
    writeStore(STORE.checks, state.checks);
    writeStore(STORE.chat, state.chat.slice(-40));
  }

  function stageById(id) {
    return STAGES.find((stage) => stage.id === id) || STAGES[0];
  }

  function stageIndex(id) {
    return STAGES.findIndex((stage) => stage.id === id);
  }

  function checkKey(stageId, index) {
    return `${stageId}:${index}`;
  }

  function stageDone(stage) {
    return stage.checks.every((_, index) => state.checks[checkKey(stage.id, index)]);
  }

  function stageCount(stage) {
    return stage.checks.filter((_, index) => state.checks[checkKey(stage.id, index)]).length;
  }

  function totalChecks() {
    return STAGES.reduce((sum, stage) => sum + stage.checks.length, 0);
  }

  function doneChecks() {
    return STAGES.reduce((sum, stage) => sum + stageCount(stage), 0);
  }

  function currentStage() {
    return STAGES.find((stage) => !stageDone(stage)) || STAGES[STAGES.length - 1];
  }

  /* ------------------------------------------------------------ rendering */

  function summarise(html) {
    // chat history is rendered from HTML we generated; this only guards against
    // a corrupted localStorage entry breaking the panel
    return typeof html === "string" ? html : "";
  }

  function renderChat() {
    const log = $("agent-log");
    if (!log) return;
    log.innerHTML = state.chat
      .map(
        (message) => `<div class="agent__msg agent__msg--${message.role}">
          <span class="agent__who">${message.role === "you" ? "You" : "Thesis guide"}</span>
          <div class="agent__bubble">${summarise(message.html)}</div>
        </div>`
      )
      .join("");
    log.scrollTop = log.scrollHeight;
  }

  function say(html) {
    state.chat.push({ role: "agent", html });
    save();
    renderChat();
  }

  function hear(text) {
    state.chat.push({ role: "you", html: `<p>${esc(text)}</p>` });
    save();
    renderChat();
  }

  function renderRoadmap() {
    const list = $("agent-roadmap");
    if (!list) return;
    list.innerHTML = STAGES.map((stage, index) => {
      const done = stageCount(stage);
      const complete = done === stage.checks.length;
      return `<li class="agent__stage${complete ? " agent__stage--done" : ""}">
        <button type="button" data-stage="${stage.id}" aria-label="Open ${esc(stage.label)}">
          <span class="agent__dot" aria-hidden="true">${complete ? "✓" : index + 1}</span>
          <span class="agent__stage-label">${esc(stage.label)}</span>
          <span class="agent__stage-count">${done}/${stage.checks.length}</span>
        </button>
      </li>`;
    }).join("");

    const percent = Math.round((doneChecks() / totalChecks()) * 100);
    $("agent-bar").style.width = `${percent}%`;
    $("agent-percent").textContent = `${percent}% complete`;
  }

  function stageCard(stage) {
    const checks = stage.checks
      .map((item, index) => {
        const checked = Boolean(state.checks[checkKey(stage.id, index)]);
        return `<li class="agent__check${checked ? " agent__check--done" : ""}">
          <label>
            <input type="checkbox" data-check="${stage.id}" data-index="${index}"${checked ? " checked" : ""} />
            <span>${esc(item)}</span>
          </label>
        </li>`;
      })
      .join("");

    const pitfalls = stage.pitfalls.map((item) => `<li>${esc(item)}</li>`).join("");
    const chips = stage.ask
      .map((prompt) => `<button type="button" class="agent__ask" data-ask="${esc(prompt)}">${esc(prompt)}</button>`)
      .join("");

    return `<div class="agent__card" data-card="${stage.id}">
      <p class="agent__eyebrow">Stage ${STAGES.indexOf(stage) + 1} of ${STAGES.length} · about ${stage.weeks} week${stage.weeks === 1 ? "" : "s"}</p>
      <h3>${esc(stage.title.replace(/^Stage \d+ · /, ""))}</h3>
      <p>${esc(stage.goal)}</p>
      <p class="agent__produce"><strong>You should end this stage with:</strong> ${esc(stage.produce)}</p>
      <p class="agent__card-label">Checklist</p>
      <ul class="agent__checks">${checks}</ul>
      <p class="agent__card-label">Where students lose time</p>
      <ul class="agent__pitfalls">${pitfalls}</ul>
      <div class="agent__chips agent__chips--inline">${chips}</div>
    </div>`;
  }

  function showStage(stageId) {
    const stage = stageById(stageId);
    say(stageCard(stage));
    renderRoadmap();
  }

  /* ------------------------------------------------------------ the plan */

  function planWeeks(profile) {
    const deadline = new Date(profile.deadline);
    if (Number.isNaN(deadline.getTime())) return null;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Math.round((deadline - today) / 86400000);
    if (days < 1) return null;
    return { weeks: Math.max(1, Math.floor(days / 7)), days, deadline };
  }

  function allocation(weeks) {
    const weight = STAGES.reduce((sum, stage) => sum + stage.weeks, 0);
    let used = 0;
    return STAGES.map((stage, index) => {
      const share = (stage.weeks / weight) * weeks;
      const start = 1 + Math.round((used / weight) * weeks);
      used += stage.weeks;
      const end = index === STAGES.length - 1 ? weeks : Math.max(start, Math.round((used / weight) * weeks));
      return { stage, start: Math.min(start, weeks), end: Math.max(1, Math.min(end, weeks)), share };
    });
  }

  function fmtDate(date) {
    return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  }

  function weekDate(weeks, week) {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    start.setDate(start.getDate() + (week - 1) * 7);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    return `${fmtDate(start)} – ${fmtDate(end)}`;
  }

  function planRows(profile) {
    const timing = planWeeks(profile);
    if (!timing) return null;
    const hours = Math.max(1, Number(profile.hours) || 6);
    const rows = allocation(timing.weeks).map(({ stage, start, end }) => ({
      stage,
      start,
      end,
      label: start === end ? `Week ${start}` : `Weeks ${start}–${end}`,
      dates: start === end ? weekDate(timing.weeks, start) : `${weekDate(timing.weeks, start).split(" – ")[0]} – ${weekDate(timing.weeks, end).split(" – ")[1]}`,
      hours: Math.max(2, Math.round(hours * (end - start + 1))),
    }));
    return { timing, rows, hours };
  }

  function planText(profile) {
    const plan = planRows(profile);
    if (!plan) return "";
    const level = (LEVELS.find(([value]) => value === profile.level) || ["", "Research project"])[1];
    const lines = [
      `Thesis plan · ${level}${profile.field ? ` · ${profile.field}` : ""}`,
      `Deadline ${fmtDate(plan.timing.deadline)} · ${plan.timing.weeks} week${plan.timing.weeks === 1 ? "" : "s"} · about ${plan.hours} hours a week`,
      "",
      ...plan.rows.map(
        (row) => `${row.label} (${row.dates}) · ~${row.hours}h · ${row.stage.label}\n   Deliverable: ${row.stage.produce}`
      ),
    ];
    return lines.join("\n");
  }

  function planMessage(profile, { intro = true } = {}) {
    const plan = planRows(profile);
    if (!plan) {
      return `<p>I need a deadline in the future to build a plan. Set your deadline again and I will lay the stages out week by week.</p>`;
    }
    const level = (LEVELS.find(([value]) => value === profile.level) || ["", "Research project"])[1];
    const rows = plan.rows
      .map(
        (row) => `<tr>
          <td>${esc(row.label)}<br /><span class="agent__muted">${esc(row.dates)}</span></td>
          <td>${esc(row.stage.label)}</td>
          <td>${esc(row.stage.produce)}</td>
          <td class="agent__num">~${row.hours}h</td>
        </tr>`
      )
      .join("");

    const tight =
      plan.timing.weeks < 6
        ? `<p class="agent__warn">${plan.timing.weeks} weeks is compressed for a full research project. Narrow the scope now — one site, one method, one population — rather than discovering it in week four.</p>`
        : "";

    const milestones = plan.rows
      .filter((row) => ["proposal", "data", "writeup", "finish"].includes(row.stage.id))
      .map((row) => `<li><strong>${esc(row.stage.label)} finished by ${esc(row.dates.split(" – ").pop())}</strong> — ${esc(row.stage.produce)}</li>`)
      .join("");

    return `${intro ? `<p>Here is the whole thing laid out backwards from your deadline. ${esc(level)}${profile.field ? ` in ${esc(profile.field)}` : ""}, about ${plan.hours} hours a week.</p>` : ""}
      <div class="agent__table-wrap"><table class="agent__table">
        <thead><tr><th>When</th><th>Stage</th><th>Deliverable</th><th>Time</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      ${tight}
      <p class="agent__card-label">Milestones to hold yourself to</p>
      <ul>${milestones}</ul>
      <div class="agent__chips agent__chips--inline">
        <button type="button" class="agent__ask" data-download-plan>Download this plan</button>
        <button type="button" class="agent__ask" data-ask="What should I do next?">What should I do next?</button>
      </div>
      <p class="agent__muted">Estimates assume steady weekly work. If a stage runs long, cut scope in the next one rather than compressing the analysis.</p>`;
  }

  /* ------------------------------------------------------------- answering */

  function containsWord(query, key) {
    // Match at the start of a word only: "search" must not match inside
    // "research", while "snowball" still matches "snowballing".
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(^|[^a-z])${escaped}`).test(query);
  }

  function scoreEntry(entry, query) {
    let score = 0;
    entry.keys.forEach((key) => {
      if (containsWord(query, key)) score += key.includes(" ") ? key.length * 2 : key.length;
    });
    if (containsWord(query, entry.title.toLowerCase())) score += 25;
    return score;
  }

  function findEntry(query) {
    const normalised = query.toLowerCase();
    let best = null;
    let bestScore = 0;
    KB.forEach((entry) => {
      const score = scoreEntry(entry, normalised);
      if (score > bestScore) {
        best = entry;
        bestScore = score;
      }
    });
    return bestScore >= 4 ? best : null;
  }

  function answerEntry(entry) {
    const stage = stageById(entry.stage);
    return `<p class="agent__eyebrow">Guide · ${esc(stage.label)}</p>
      <h3>${esc(entry.title)}</h3>
      ${entry.body}
      <div class="agent__chips agent__chips--inline">
        <button type="button" class="agent__ask" data-stage="${stage.id}">Open ${esc(stage.label)}</button>
        <button type="button" class="agent__ask" data-ask="What should I do next?">What should I do next?</button>
      </div>`;
  }

  function fallback(query) {
    const words = query.toLowerCase().split(/[^a-z]+/).filter((word) => word.length > 3);
    const ranked = KB.map((entry) => ({
      entry,
      hits: words.filter((word) => entry.keys.some((key) => key.includes(word)) || entry.title.toLowerCase().includes(word)).length,
    }))
      .filter((item) => item.hits > 0)
      .sort((a, b) => b.hits - a.hits)
      .slice(0, 3)
      .map((item) => item.entry);

    const suggestions = (ranked.length ? ranked : KB.slice(0, 3))
      .map((entry) => `<button type="button" class="agent__ask" data-ask="${esc(entry.title)}">${esc(entry.title)}</button>`)
      .join("");

    return `<p>I do not have a written answer for that one. I guide research writing from a fixed handbook, so I am strongest on things like scoping a topic, searching the literature, sampling, ethics, analysis, structure, referencing and defending.</p>
      <p>Try one of these, or ask again in your own words:</p>
      <div class="agent__chips agent__chips--inline">${suggestions}</div>`;
  }

  function nextStep() {
    const stage = currentStage();
    const index = stage.checks.findIndex((_, position) => !state.checks[checkKey(stage.id, position)]);
    const percent = Math.round((doneChecks() / totalChecks()) * 100);

    if (percent === 100) {
      return `<p><strong>Every checklist item is ticked.</strong> That is a finished thesis on paper. Before you submit, confirm three things: your supervisor has signed off, the reference list matches every in-text citation, and you have a copy of exactly what you sent.</p>
        <div class="agent__chips agent__chips--inline">
          <button type="button" class="agent__ask" data-stage="finish">Open the submission checklist</button>
          <button type="button" class="agent__ask" data-ask="How do I prepare for my viva?">How do I prepare for my viva?</button>
        </div>`;
    }

    const item = stage.checks[index];
    const before = stage.checks.slice(0, index);

    return `<p>You are ${percent}% through the guide. Next is <strong>${esc(stage.label)}</strong>, item ${index + 1} of ${stage.checks.length}:</p>
      <p class="agent__next">${esc(item)}</p>
      ${before.length ? `<p class="agent__muted">Earlier items in this stage are ticked: ${esc(before.join("; "))}.</p>` : ""}
      <p>${esc(stage.goal)}</p>
      <div class="agent__chips agent__chips--inline">
        <button type="button" class="agent__ask" data-stage="${stage.id}">Open the ${esc(stage.label.toLowerCase())} stage</button>
        <button type="button" class="agent__ask" data-ask="I am behind schedule">I am behind schedule</button>
      </div>`;
  }

  function startHere() {
    return `<p>Then start with the smallest honest version of your topic. Three questions settle it:</p>
      <ol>
        <li><strong>What can you reach?</strong> Which people, documents or datasets can you actually access in the next month?</li>
        <li><strong>What can you measure or describe?</strong> Pick a question your access makes answerable.</li>
        <li><strong>What is already known?</strong> One database search tells you whether the gap is real.</li>
      </ol>
      <p>Answer those three and you have a topic, a question and a search plan.</p>
      <div class="agent__chips agent__chips--inline">
        <button type="button" class="agent__ask" data-stage="topic">Open stage 1</button>
        <button type="button" class="agent__ask" data-ask="How do I narrow my topic?">How do I narrow my topic?</button>
      </div>`;
  }

  function profileForm() {
    const levels = LEVELS.map(([value, label]) => `<option value="${value}"${state.profile && state.profile.level === value ? " selected" : ""}>${esc(label)}</option>`).join("");
    const saved = state.profile || {};
    return `<form class="agent__form">
      <p class="agent__card-label">Set up my plan</p>
      <div class="agent__fields">
        <label>Level
          <select name="level">${levels}</select>
        </label>
        <label>Field of study
          <input name="field" type="text" placeholder="e.g. Public health" value="${esc(saved.field || "")}" />
        </label>
        <label>Submission deadline
          <input name="deadline" type="date" value="${esc(saved.deadline || "")}" required />
        </label>
        <label>Hours a week
          <input name="hours" type="number" min="1" max="60" value="${esc(saved.hours || 6)}" />
        </label>
      </div>
      <button type="submit" class="button">Build my week-by-week plan</button>
    </form>`;
  }

  function greeting() {
    const intro = `<p>Hello. I am your thesis guide — I take you from a topic you can still change to a document you can defend.</p>
      <p>I work through ten stages: scope, question, literature, review, method, proposal, data, findings, write-up, submission. Each stage has a checklist, the traps students fall into, and the deliverable it should produce.</p>
      <p>Tell me your deadline and I will lay those stages out week by week. Or start with a question:</p>
      <div class="agent__chips agent__chips--inline">
        <button type="button" class="agent__ask" data-ask="How do I narrow my topic?">How do I narrow my topic?</button>
        <button type="button" class="agent__ask" data-ask="How do I search the literature properly?">How do I search the literature?</button>
        <button type="button" class="agent__ask" data-ask="What should I do next?">What should I do next?</button>
      </div>`;
    say(intro + profileForm());
  }

  function capabilities() {
    return `<p>Here is what I can do:</p>
      <ul>
        <li>Build a dated plan from your submission deadline and hours a week.</li>
        <li>Walk you through the ten stages of a thesis, with a checklist for each.</li>
        <li>Answer questions on scoping, literature searching, review writing, methods, sampling, ethics, analysis, structure, referencing, similarity and the viva.</li>
        <li>Track what you have finished and tell you what to do next.</li>
      </ul>
      <p>I work from a fixed handbook rather than the internet, so I will say when a question is outside it.</p>
      <div class="agent__chips agent__chips--inline">
        <button type="button" class="agent__ask" data-ask="What should I do next?">What should I do next?</button>
        <button type="button" class="agent__ask" data-stage="topic">Open stage 1</button>
      </div>`;
  }

  function respond(text) {
    const query = text.toLowerCase().trim();
    const plan = planRows(state.profile || {});

    if (/^(hi|hello|hey|good (morning|afternoon|evening))\b/.test(query)) {
      return `<p>Hello. Ask me anything about writing your research or thesis, or say "build my plan" and I will lay out the stages against your deadline.</p>`;
    }
    if (/^(thanks|thank you|thankyou)\b/.test(query)) {
      return `<p>You are welcome. One thing worth doing now: ${esc(currentStage().checks.find((_, index) => !state.checks[checkKey(currentStage().id, index)]) || "review the submission checklist")}.</p>`;
    }
    if (/^(help|what can you do|how does this work)/.test(query)) return capabilities();

    if (/(what|where)\b.*\b(next|now)\b|\bstuck\b|behind schedule/.test(query) && !/(plan|deadline)/.test(query)) {
      return nextStep();
    }
    if (/(build|make|rebuild|show|give|new).{0,20}(plan|schedule|timeline)|my plan|the plan|deadline|reschedule/.test(query)) {
      return state.profile && plan ? planMessage(state.profile) : `<p>Set your deadline first and I will build the plan around it.</p>` + profileForm();
    }
    if (/^(start|begin|where do i start|first step)/.test(query)) {
      const entry = findEntry(query);
      return entry ? answerEntry(entry) : startHere();
    }
    const entry = findEntry(query);
    if (entry) return answerEntry(entry);
    return fallback(text);
  }

  function send(text) {
    const clean = text.trim();
    if (!clean || state.pending) return;
    hear(clean);
    state.pending = true;
    $("agent-input").value = "";

    // a short pause so the answer arrives like a reply, not a page repaint
    setTimeout(() => {
      say(respond(clean));
      state.pending = false;
    }, 320);
  }

  /* --------------------------------------------------------------- events */

  function bind() {
    const section = $("thesis-agent");
    if (!section || section.dataset.bound === "yes") return;
    section.dataset.bound = "yes";

    $("agent-form").addEventListener("submit", (event) => {
      event.preventDefault();
      send($("agent-input").value);
    });

    section.addEventListener("click", (event) => {
      const ask = event.target.closest("[data-ask]");
      if (ask) {
        send(ask.dataset.ask);
        return;
      }

      const jump = event.target.closest("[data-stage]");
      if (jump) {
        showStage(jump.dataset.stage);
        return;
      }

      if (event.target.closest("[data-download-plan]")) {
        const text = state.profile ? planText(state.profile) : "";
        if (!text) return;
        const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "thesis-plan.txt";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        return;
      }

      if (event.target.closest("#agent-reset")) {
        const button = event.target.closest("#agent-reset");
        if (button.dataset.armed !== "yes") {
          button.dataset.armed = "yes";
          button.textContent = "Tap again to clear";
          setTimeout(() => {
            button.dataset.armed = "no";
            button.textContent = "Start over";
          }, 5000);
          return;
        }
        state.profile = null;
        state.checks = {};
        state.chat = [];
        save();
        writeStore(STORE.profile, null);
        renderRoadmap();
        greeting();
        button.dataset.armed = "no";
        button.textContent = "Start over";
      }
    });

    section.addEventListener("change", (event) => {
      const box = event.target.closest("[data-check]");
      if (box) {
        state.checks[checkKey(box.dataset.check, box.dataset.index)] = box.checked;
        save();
        renderRoadmap();
        const card = box.closest(".agent__check");
        if (card) card.classList.toggle("agent__check--done", box.checked);
        return;
      }

      if (event.target.closest(".agent__form")) {
        // handled on submit; change events keep the fields responsive without a plan rebuild
      }
    });

    section.addEventListener("submit", (event) => {
      const form = event.target.closest(".agent__form");
      if (!form) return;
      event.preventDefault();
      const data = new FormData(form);
      const profile = {
        level: String(data.get("level") || "masters"),
        field: String(data.get("field") || "").trim(),
        deadline: String(data.get("deadline") || ""),
        hours: Number(data.get("hours") || 6),
      };
      if (!profile.deadline) {
        say(`<p>Pick a submission deadline — even an approximate one — so the plan has an anchor.</p>`);
        return;
      }
      state.profile = profile;
      writeStore(STORE.profile, profile);
      say(planMessage(profile));
    });
  }

  function open() {
    if (!state.booted) {
      state.booted = true;
      bind();
      renderRoadmap();
      if (!state.chat.length) greeting();
      else renderChat();
    }
  }

  window.ThesisAgent = { open };
})();
