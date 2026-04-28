import fs from "node:fs/promises";
import path from "node:path";
import {
  Presentation,
  PresentationFile,
  text,
  panel,
  row,
  column,
  grid,
  rule,
  shape,
  fill,
  hug,
  fixed,
  wrap,
  fr,
  auto,
} from "@oai/artifact-tool";

const W = 1920;
const H = 1080;

const outDir = path.resolve("output");
const scratchDir = path.resolve("scratch");
await fs.mkdir(outDir, { recursive: true });
await fs.mkdir(scratchDir, { recursive: true });

const C = {
  bg: "#F6FBFA",
  paper: "#FFFFFF",
  ink: "#102A43",
  muted: "#52677A",
  faint: "#D8E9E7",
  teal: "#089B92",
  tealDeep: "#08756F",
  blue: "#2364AA",
  coral: "#E2604D",
  amber: "#D4941E",
  violet: "#725AC1",
  green: "#3A9D6B",
  slate: "#243B53",
};

const S = {
  title: { fontSize: 52, bold: true, color: C.ink },
  subtitle: { fontSize: 24, color: C.muted },
  body: { fontSize: 27, color: C.ink },
  small: { fontSize: 18, color: C.muted },
  tiny: { fontSize: 14, color: C.muted },
  eyebrow: { fontSize: 18, bold: true, color: C.tealDeep },
  number: { fontSize: 78, bold: true, color: C.tealDeep },
  coverTitle: { fontSize: 92, bold: true, color: C.ink },
  coverSub: { fontSize: 31, color: C.muted },
};

const sources = "Sources: live ClinSafer app, local test suite, and generated demo artifacts.";

const deck = Presentation.create({
  slideSize: { width: W, height: H },
});

function addNotes(slide, noteText) {
  slide.speakerNotes.setText(noteText.trim());
}

function slideBase(slide, children, opts = {}) {
  slide.compose(
    panel(
      {
        name: "slide-stage",
        width: fill,
        height: fill,
        fill: opts.fill || C.bg,
        padding: { x: 82, y: 58 },
      },
      column(
        { name: "slide-root", width: fill, height: fill, gap: opts.gap || 30 },
        children,
      ),
    ),
    { frame: { left: 0, top: 0, width: W, height: H }, baseUnit: 8 },
  );
}

function titleStack(title, subtitle, eyebrow = "") {
  const parts = [];
  if (eyebrow) parts.push(text(eyebrow, { name: "eyebrow", width: fill, height: hug, style: S.eyebrow }));
  parts.push(text(title, { name: "slide-title", width: fill, height: fixed(132), style: S.title }));
  if (subtitle) parts.push(text(subtitle, { name: "slide-subtitle", width: fill, height: fixed(74), style: S.subtitle }));
  return column({ name: "title-stack", width: fill, height: hug, gap: 10 }, parts);
}

function footer(label = "ClinSafer interview demo | Apr 2026") {
  return row(
    { name: "footer", width: fill, height: hug, justify: "between", align: "end" },
    [
      text(label, { name: "footer-left", width: wrap(900), height: hug, style: S.tiny }),
      text("clinsafer.fly.dev", { name: "footer-right", width: fixed(260), height: hug, style: { ...S.tiny, color: C.tealDeep, bold: true } }),
    ],
  );
}

function smallCaps(value, color = C.tealDeep) {
  return text(value, { width: hug, height: hug, style: { fontSize: 16, bold: true, color } });
}

function openBullets(items, opts = {}) {
  return column(
    { name: opts.name || "bullets", width: fill, height: hug, gap: opts.gap || 18 },
    items.map((item, i) =>
      row(
        { name: `bullet-row-${i}`, width: fill, height: hug, gap: 14, align: "start" },
        [
          shape({ name: `bullet-mark-${i}`, width: fixed(9), height: fixed(36), fill: opts.color || C.teal }),
          text(item, { name: `bullet-text-${i}`, width: fill, height: hug, style: opts.style || S.body }),
        ],
      ),
    ),
  );
}

function pill(label, color = C.tealDeep, opts = {}) {
  const width = opts.width ? fixed(opts.width) : hug;
  return panel(
    {
      width,
      height: hug,
      fill: "#FFFFFF",
      line: { color, width: 1.5 },
      borderRadius: "rounded-full",
      padding: { x: 18, y: 9 },
    },
    text(label, { width: opts.width ? fill : hug, height: hug, style: { fontSize: 17, bold: true, color } }),
  );
}

function metric(number, label, color = C.tealDeep) {
  return column(
    { width: fill, height: hug, gap: 6 },
    [
      text(number, { width: fill, height: hug, style: { ...S.number, color } }),
      text(label, { width: wrap(430), height: hug, style: { fontSize: 20, color: C.muted } }),
    ],
  );
}

function compactPanel(title, body, color = C.tealDeep) {
  return panel(
    {
      width: fill,
      height: hug,
      fill: C.paper,
      line: { color: C.faint, width: 1 },
      padding: { x: 22, y: 18 },
    },
    column(
      { width: fill, height: hug, gap: 8 },
      [
        text(title, { width: fill, height: hug, style: { fontSize: 23, bold: true, color } }),
        text(body, { width: fill, height: hug, style: { fontSize: 19, color: C.muted } }),
      ],
    ),
  );
}

function qaRow(q, a, color = C.blue) {
  return grid(
    { width: fill, height: hug, columns: [fr(0.9), fr(1.5)], columnGap: 26 },
    [
      text(q, { width: fill, height: hug, style: { fontSize: 21, bold: true, color } }),
      text(a, { width: fill, height: hug, style: { fontSize: 20, color: C.ink } }),
    ],
  );
}

function addCover() {
  const slide = deck.slides.add();
  slide.compose(
    panel(
      { name: "cover-stage", width: fill, height: fill, fill: C.bg, padding: { x: 86, y: 66 } },
      grid(
        { name: "cover-grid", width: fill, height: fill, columns: [fr(1.2), fr(0.8)], rows: [fr(1), auto], columnGap: 70, rowGap: 34 },
        [
          column(
            { width: fill, height: fill, gap: 20, justify: "center" },
            [
              text("ClinSafer", { width: fill, height: hug, style: { fontSize: 30, bold: true, color: C.tealDeep } }),
              text("Autonomy boundaries for AI medicine", { name: "cover-title", width: wrap(1050), height: hug, style: S.coverTitle }),
              rule({ width: fixed(260), stroke: C.coral, weight: 6 }),
              text("A live interview demo for showing how messy patient language becomes governed action.", { width: wrap(950), height: hug, style: S.coverSub }),
            ],
          ),
          column(
            { width: fill, height: fill, gap: 26, justify: "center" },
            [
              metric("46", "synthetic cases in the live library", C.tealDeep),
              metric("333", "passing tests after final polish", C.blue),
              metric("1", "most-restrictive governor decides autonomy", C.coral),
            ],
          ),
          row(
            { width: fill, height: hug, columnSpan: 2, justify: "between", align: "end" },
            [
              text("Prepared for an AI healthcare interview conversation", { width: wrap(900), height: hug, style: S.small }),
              text("Live app: clinsafer.fly.dev", { width: hug, height: hug, style: { ...S.small, bold: true, color: C.tealDeep } }),
            ],
          ),
        ],
      ),
    ),
    { frame: { left: 0, top: 0, width: W, height: H }, baseUnit: 8 },
  );
  addNotes(slide, `
Open with humility. Do not imply the team lacks safeguards.

Talk track:
- "I am assuming your team already has strong AI doctor, triage, escalation, and telemedicine infrastructure."
- "This is a layer around that: what the AI is allowed to infer, what remains unknown, and when autonomy should be capped."
- "The point of the deck is to orient the demo; the live app is the proof."

Goal for this slide: position yourself as additive, not adversarial.
`);
}

function addContext() {
  const slide = deck.slides.add();
  slideBase(slide, [
    titleStack(
      "Healthcare AI scale changes the safety problem",
      "At consumer scale, the hard failures are often not obvious triage misses. They are inference, workflow, and autonomy-boundary failures.",
      "WHY THIS AUDIENCE SHOULD CARE",
    ),
    grid(
      { width: fill, height: fill, columns: [fr(1.15), fr(0.85)], columnGap: 58 },
      [
        column(
          { width: fill, height: fill, gap: 24, justify: "center" },
          [
            text("The product question is not just diagnosis.", { width: wrap(900), height: hug, style: { fontSize: 54, bold: true, color: C.ink } }),
            text("It is whether the system has enough reliable evidence to act, reassure, refill, route, or stop.", { width: wrap(910), height: hug, style: { fontSize: 32, color: C.muted } }),
          ],
        ),
        column(
          { width: fill, height: fill, gap: 34, justify: "center" },
          [
            metric("Scale", "high-volume patient-facing AI intake", C.tealDeep),
            metric("Handoff", "low-friction clinician escalation", C.green),
            metric("Autonomy", "governed permission to act or stop", C.violet),
          ],
        ),
      ],
    ),
    footer(sources),
  ]);
  addNotes(slide, `
Talk track:
- "At this scale, even a small autonomy-boundary issue matters operationally."
- "If a patient minimizes because of cost, shame, fear, misunderstanding, anxiety framing, or stoic denial, the AI conversation itself becomes part of the risk."
- "That is where I think this layer fits: not replacing internal reasoning, but governing its action boundary."
`);
}

function addThesis() {
  const slide = deck.slides.add();
  slideBase(slide, [
    titleStack("The thesis", "Messy language needs an autonomy governor, not just a smarter answer generator.", "ONE SENTENCE"),
    grid(
      { width: fill, height: hug, columns: [fr(1), fr(1), fr(1)], columnGap: 34, alignItems: "start" },
      [
        compactPanel("What was said", "Patient statements, denials, goals, barriers, source, freshness.", C.tealDeep),
        compactPanel("What can be inferred", "Only bounded interpretations with confidence, provenance, and close-boundary questions.", C.blue),
        compactPanel("What cannot be assumed", "Unasked symptoms, stale data, remote-unknowable findings, coercion, contradiction.", C.coral),
      ],
    ),
    text("The demo is about safe permission to act, not diagnosis prediction.", { width: fill, height: hug, style: { fontSize: 34, bold: true, color: C.ink } }),
    footer(),
  ]);
  addNotes(slide, `
This slide is the core framing.

Say:
- "I am not trying to win a differential diagnosis contest."
- "The system should know what it knows, what it inferred, what it did not ask, and what it cannot know remotely."
- "That determines whether autonomy is appropriate."

This is a good place to say "interpretation boundary" out loud.
`);
}

function addDemoPath() {
  const slide = deck.slides.add();
  const steps = [
    ["1", "Pick or paste", "Use cost-fear case or real encounter text."],
    ["2", "Analyze", "JRE and Black Swan Guard run deterministically."],
    ["3", "Inspect", "Statement vs Fact and Provenance show authority."],
    ["4", "Decide", "Most restrictive governor caps autonomy."],
    ["5", "Recommend", "Final page gives action, handoff, and metrics."],
  ];
  slideBase(slide, [
    titleStack("Seven-minute live demo path", "Keep the interview on the product idea. Do not wander through the whole case library.", "HOW TO RUN IT"),
    grid(
      { width: fill, height: fill, columns: [fr(1), fr(1), fr(1), fr(1), fr(1)], columnGap: 20 },
      steps.map(([n, h, b], i) =>
        column(
          { width: fill, height: fill, gap: 16, justify: "center" },
          [
            text(n, { width: fill, height: hug, style: { fontSize: 74, bold: true, color: [C.tealDeep, C.blue, C.violet, C.coral, C.green][i] } }),
            text(h, { width: fill, height: hug, style: { fontSize: 28, bold: true, color: C.ink } }),
            text(b, { width: fill, height: hug, style: { fontSize: 20, color: C.muted } }),
          ],
        ),
      ),
    ),
    footer(),
  ]);
  addNotes(slide, `
Actual path:
1. Open https://clinsafer.fly.dev
2. Use "Show Cost-Fear Case" first.
3. Optional: click Paste Transcript and import a short real encounter.
4. Analyze.
5. Stop on Statement vs Fact and Provenance & Authority.
6. Open Final Recommendations.

If he asks for a real encounter: paste it. The app now parses Q/A and speaker-labeled transcripts, leaves turns editable, infers concepts if blank, and shows an Input Coverage Audit proving each line was used, mapped, routed, or held for review.
`);
}

function addPasteSlide() {
  const slide = deck.slides.add();
  slideBase(slide, [
    titleStack("If they ask for real dialogue, use paste import", "The demo is not locked to fixed cases. Pasted encounter text becomes editable, inferred, and analyzed.", "LIVE INPUT PROOF"),
    grid(
      { width: fill, height: fill, columns: [fr(1.1), fr(0.9)], columnGap: 50, alignItems: "start" },
      [
        panel(
          { width: fill, height: hug, fill: "#FFFFFF", line: { color: C.faint, width: 1 }, padding: { x: 26, y: 24 } },
          text("Clinician: Do you have chest pain?\nPatient: No, just tight indigestion when I walk.\nClinician: Any shortness of breath?\nPatient: Not really. I slow down so it does not get bad.", {
            width: fill,
            height: hug,
            style: { fontSize: 27, color: C.ink },
          }),
        ),
        column(
          { width: fill, height: fill, gap: 24, justify: "center" },
          [
            compactPanel("Parsed", "Q/A, clinician/patient labels, and alternating turns.", C.tealDeep),
            compactPanel("Editable", "Question, answer, source, and concept can be changed before analysis.", C.blue),
            compactPanel("Inferred", "Blank or generic concepts are inferred from question plus answer text.", C.coral),
            compactPanel("Coverage", "Each line is marked used, context, red flag, hard stop, or review.", C.green),
          ],
        ),
      ],
    ),
    footer(),
  ]);
  addNotes(slide, `
This is a practical demo safety feature.

Say:
- "If you give me a small de-identified encounter fragment, I can paste it here."
- "The UI will show a live input parsed proof line so it is obvious that the encounter changed."
- "Concepts can be blank. The engine infers the likely slot from the question and answer."
- "The Input Coverage Audit is the proof that no line quietly disappears."

Caution: ask for de-identified text only. Avoid PHI in an interview.
`);
}

function addArchitecture() {
  const slide = deck.slides.add();
  const nodes = [
    ["Input", "Transcript + coverage audit"],
    ["Extractor", "Normalize observations and confidence"],
    ["JRE", "Missing, uncertain, distorted, contradictory"],
    ["BSG", "Operating envelope and autonomy cap"],
    ["Governor", "Most restrictive state wins"],
    ["Output", "Questions, handoff, recommendations"],
  ];
  slideBase(slide, [
    titleStack("The method is ensemble governance", "LLM candidates help find signals, but deterministic validators and guardrails decide autonomy.", "TECHNICAL BACKBONE"),
    row(
      { width: fill, height: fill, gap: 10, align: "center" },
      nodes.flatMap(([h, b], i) => {
        const block = panel(
          { width: fixed(226), height: hug, fill: "#FFFFFF", line: { color: C.faint, width: 1 }, padding: { x: 14, y: 16 } },
          column({ width: fill, height: hug, gap: 8 }, [
            text(h, { width: fill, height: hug, style: { fontSize: 23, bold: true, color: [C.tealDeep, C.blue, C.violet, C.coral, C.amber, C.green][i] } }),
            text(b, { width: fill, height: hug, style: { fontSize: 17, color: C.muted } }),
          ]),
        );
        return i === nodes.length - 1 ? [block] : [block, text("->", { width: fixed(26), height: hug, style: { fontSize: 24, bold: true, color: C.muted } })];
      }),
    ),
    text("Autonomy is capped by authority, not by model confidence alone.", { width: fill, height: hug, style: { fontSize: 34, bold: true, color: C.ink } }),
    footer(),
  ]);
  addNotes(slide, `
Technical explanation:
- Patient statements become observations with source confidence and trap tags.
- JRE evaluates readiness: missingness, distortion, contradiction, red flags, objective needs, remote boundaries.
- Black Swan Guard checks assumptions: identity/proxy, communication channel, envelope fit, source integrity, sentinel risk.
- LLM findings are advisory candidate signals. They cannot authorize or hard-stop.
- The final state is the most restrictive of JRE and guardrail state.

Good phrase: "The LLM proposes. Governed software disposes."
`);
}

function addProvenance() {
  const slide = deck.slides.add();
  const rows = [
    ["Curated rules", "Enforced", "Can ask, route, block, or cap."],
    ["LLM candidates", "Advisory", "Can suggest review targets only."],
    ["Learned priors", "Bounded", "Tune confidence and question priority."],
    ["Memory hooks", "Advisory", "Suggest missing nodes and falsifiers."],
    ["Ensemble governor", "Enforced", "Most restrictive final state wins."],
  ];
  slideBase(slide, [
    titleStack("Provenance is the safety interface", "The demo separates signal source from action authority.", "WHAT TO POINT AT"),
    column(
      { width: fill, height: fill, gap: 14 },
      rows.map(([a, b, c], i) =>
        grid(
          { width: fill, height: hug, columns: [fr(0.85), fr(0.55), fr(1.4)], columnGap: 24 },
          [
            text(a, { width: fill, height: hug, style: { fontSize: 29, bold: true, color: C.ink } }),
            pill(b, [C.tealDeep, C.amber, C.blue, C.violet, C.coral][i], { width: 165 }),
            text(c, { width: fill, height: hug, style: { fontSize: 25, color: C.muted } }),
          ],
        ),
      ),
    ),
    footer(),
  ]);
  addNotes(slide, `
This slide anticipates the "LLMs are unsafe" objection.

Say:
- "Every visible signal has provenance and authority."
- "The LLM is useful, but it is not allowed to make the final autonomy decision."
- "Memory is also bounded. It can suggest but not authorize."

If they ask why this matters:
- "Without provenance, a clinician or regulator cannot tell whether a decision came from a validated rule, a model hunch, or a memory prior."
`);
}

function addRecommendations() {
  const slide = deck.slides.add();
  slideBase(slide, [
    titleStack("The final page must be actionable", "A polished analysis is not enough. The output has to tell a human and the system what to do next.", "FINAL RECOMMENDATIONS"),
    grid(
      { width: fill, height: hug, columns: [fr(1), fr(1)], columnGap: 46, rowGap: 24, alignItems: "start" },
      [
        compactPanel("Disposition", "ESCALATE, HOLD, NEED_OBJECTIVE_DATA, ROUTE_CLINICIAN, or narrow audited action.", C.coral),
        compactPanel("Immediate action", "What is allowed now, what is blocked, and what restores readiness.", C.tealDeep),
        compactPanel("Human factors", "Defense/disclosure cues become inference limits and next-question strategy, not patient labels.", C.blue),
        compactPanel("Clinician handoff", "Boundary map and top blockers instead of raw transcript only.", C.violet),
      ],
    ),
    footer(),
  ]);
  addNotes(slide, `
When you click Final Recommendations in the app, frame it as the conversion from analysis into action.

Emphasize:
- "This is not just explainability. It is operational instruction."
- "The page distinguishes patient language, human defense patterns, clinical handoff, governance actions, and quality metrics."
- "This helps with safety, physician efficiency, and patient trust."

Do not overstate that the patient copy is final clinical guidance. Say it is a demo draft requiring product/clinical review.
`);
}

function addRealVsPrototype() {
  const slide = deck.slides.add();
  const rows = [
    ["Implemented now", "Deterministic JRE, Black Swan Guard, live edit/paste, LLM extractor, final recommendations, tests."],
    ["Prototype hooks", "In-memory learning, trace regions, VAMS-style near-miss recall, governed template promotion."],
    ["Not claimed", "Production clinical validation, persistent memory, autonomous prescription approval, medical device readiness."],
  ];
  slideBase(slide, [
    titleStack("Be precise about what is real", "This slide prevents the demo from sounding like vaporware or overclaiming.", "CREDIBILITY CHECK"),
    column(
      { width: fill, height: fill, gap: 24 },
      rows.map(([h, b], i) =>
        grid(
          { width: fill, height: hug, columns: [fr(0.55), fr(1.6)], columnGap: 36 },
          [
            text(h, { width: fill, height: hug, style: { fontSize: 30, bold: true, color: [C.tealDeep, C.blue, C.coral][i] } }),
            text(b, { width: fill, height: hug, style: { fontSize: 26, color: C.ink } }),
          ],
        ),
      ),
    ),
    row(
      { width: fill, height: hug, gap: 28, align: "center" },
      [pill("333 tests passed", C.tealDeep), pill("Live Fly deployment", C.blue), pill("OpenRouter model configurable", C.violet)],
    ),
    footer(),
  ]);
  addNotes(slide, `
Use this if the technical audience is skeptical.

Say:
- "The real piece is the governed analysis and live UI."
- "The memory layer is intentionally described as a prototype hook."
- "I would not deploy online memory without outcome governance and simulation."

This honesty is a strength. It avoids sounding like you are selling magic.
`);
}

function addShowpieces() {
  const slide = deck.slides.add();
  slideBase(slide, [
    titleStack("Cases to run if the conversation shifts", "Use one case at a time. Each one demonstrates a different boundary failure.", "DEMO CHOICES"),
    grid(
      { width: fill, height: hug, columns: [fr(1), fr(1)], columnGap: 44, rowGap: 24, alignItems: "start" },
      [
        compactPanel("Cost fear minimizes alarm", "Patient asks the system to approve delay while describing exertional tightness.", C.coral),
        compactPanel("Embarrassment curbs history", "Patient walks back alarm details because of shame, internet fear, and chart anxiety.", C.amber),
        compactPanel("Defense pattern distortion", "Patient labels exertional pressure as anxiety while also trying to tough it out.", C.green),
        compactPanel("Caregiver conflict", "Patient says fine; caregiver reports confusion. Source conflict caps autonomy.", C.violet),
      ],
    ),
    footer(),
  ]);
  addNotes(slide, `
Preferred first case: cost-fear minimizes alarm.

Why:
- It is subtle enough for a physician.
- It is business-relevant without sounding mercenary.
- It shows patient behavior shaping the conversation.

Second case if they ask about real-world subtlety: embarrassment curbs history.
- It shows shame, fear of a bad outcome, misconstrued medical facts, and chart anxiety distorting the history before the model reasons over it.

Third case if they ask what "human" means beyond embarrassment: defense pattern distortion.
- It bridges anxious somatic amplification/reassurance seeking and stoic minimization/denial without using stigmatizing labels.

If they care about prescriptions/refills, switch to the stale ACE/CKD/NSAID refill case.
If they care about caregiver workflows, use caregiver conflict.
If they care about documentation integrity, use unasked-is-not-denied.
`);
}

function addValue() {
  const slide = deck.slides.add();
  slideBase(slide, [
    titleStack("The value is safer automation", "The same boundary layer can reduce unsafe automation and avoidable human routing.", "OPERATING LEVERAGE"),
    grid(
      { width: fill, height: fill, columns: [fr(1), fr(1), fr(1), fr(1)], columnGap: 28 },
      [
        metric("Safety", "Blocks action when assumptions fail.", C.coral),
        metric("Margin", "Closes fixable evidence gaps before routing.", C.green),
        metric("Trust", "Explains uncertainty without dismissing the patient.", C.tealDeep),
        metric("Review", "Hands clinicians a boundary map, not just transcript.", C.blue),
      ],
    ),
    text("Metric to track: percent of routed cases where one clarification changes disposition or prevents avoidable physician review.", { width: wrap(1480), height: hug, style: { fontSize: 28, bold: true, color: C.ink } }),
    footer(),
  ]);
  addNotes(slide, `
This is where you connect medicine and business without making it sound like safety is secondary.

Say:
- "The product win is safe automation."
- "Sometimes the right answer is route now. Sometimes the right answer is ask one better question and avoid unnecessary routing."
- "Both matter at scale."

If challenged:
- "I would measure confirmation rate, false positive escalations, avoidable routing prevented, patient completion after escalation, and clinician correction rate."
`);
}

function addWhatIBring() {
  const slide = deck.slides.add();
  slideBase(slide, [
    titleStack("What I bring", "The differentiator is cross-domain judgment, not just code output.", "YOUR STORY"),
    grid(
      { width: fill, height: hug, columns: [fr(1), fr(1), fr(1)], columnGap: 36, rowGap: 24, alignItems: "start" },
      [
        compactPanel("Medicine", "Clinical risk, patient language, remote limits, physician workflow.", C.coral),
        compactPanel("AI systems", "LLM extraction, expert-system shells, ensemble governance, memory boundaries.", C.blue),
        compactPanel("Operations", "Routing, churn, escalation rationale, clinician efficiency, auditability.", C.green),
        compactPanel("Risk", "Fail-closed thinking, provenance, governed promotion, no uncontrolled online learning.", C.violet),
        compactPanel("Product", "Demoable UX that makes invisible safety reasoning visible.", C.tealDeep),
        compactPanel("Execution", "Built, tested, pushed, deployed, and iterated from feedback.", C.amber),
      ],
    ),
    footer(),
  ]);
  addNotes(slide, `
This is not a brag slide. It is a bridge from demo to interview.

Say:
- "What I wanted to show is how I think."
- "At healthcare AI scale, medicine, business, risk, and engineering are not separate problems."
- "I can work across those surfaces and still build working software."

Keep it calm. Let the app be the evidence.
`);
}

function addExecutiveQuestions() {
  const slide = deck.slides.add();
  const rows = [
    ["Are you saying we lack this?", "No. I assume you have strong safeguards. This is how I think about the next boundary layer."],
    ["How does it help the business?", "Safer automation, less avoidable review, clearer escalation rationale, lower abandonment."],
    ["What would you measure?", "Clinician confirmation, correction rate, avoidable routing, patient completion, evidence-gap closure."],
    ["Where would it fit?", "Before autonomous action, refill renewal, low-acuity closure, or physician handoff."],
    ["What is production path?", "Persistent memory, outcome labels, simulation suite, governance promotion, clinical review."],
  ];
  slideBase(slide, [
    titleStack("Likely executive questions", "Answer directly, then point back to the live app.", "EXECUTIVE CONVERSATION"),
    column({ width: fill, height: fill, gap: 20 }, rows.map(([q, a]) => qaRow(q, a, C.tealDeep))),
    footer(),
  ]);
  addNotes(slide, `
Use this slide as your mental checklist, not necessarily as something to present.

Important tone:
- Never say "you probably do not have this."
- Say "I do not know your internal safeguards, so I built the kind of layer I would look for at scale."

If asked where you would start:
- "Pick one workflow with clear value and measurable risk, likely prescription renewal or low-acuity closure. Run shadow mode against historical cases first."
`);
}

function addDevQuestions() {
  const slide = deck.slides.add();
  const rows = [
    ["Is this rules or AI?", "Both. AI proposes candidates; deterministic systems validate, score, and cap action."],
    ["How are nodes selected?", "Domain templates now; next version lets AI propose case-specific graph nodes for governed validation."],
    ["Can LLM override rules?", "No. LLM-only findings are advisory and cannot authorize or hard-stop."],
    ["What about latency?", "Core analysis is fast and deterministic. LLM runs async with timeout and retry."],
    ["How prevent memory drift?", "Memory proposes missing nodes/falsifiers only. Promotion requires review and simulation."],
  ];
  slideBase(slide, [
    titleStack("Likely technical questions", "Be crisp: deterministic core, advisory model, governed learning.", "DEV TEAM CONVERSATION"),
    column({ width: fill, height: fill, gap: 20 }, rows.map(([q, a]) => qaRow(q, a, C.blue))),
    footer(),
  ]);
  addNotes(slide, `
If they ask for architecture details:
- Input schema: patient_context plus statements with question, answer, concept, source, metadata.
- Extraction: normalize, infer concept if blank, assign source confidence, apply trap priors.
- JRE: produces observations, findings, JRI, next questions.
- BSG: evaluates assumptions and max autonomy tier.
- Governor: most restrictive state wins.
- LLM: separate /demo/llm-analyze endpoint, async in UI.

If they ask about distributions:
- Current demo uses bounded deterministic confidence and severity, not full probabilistic distributions.
- Next version would have AI-proposed node ranges and distributions validated against governed templates and calibration data.
`);
}

function addHardObjections() {
  const slide = deck.slides.add();
  slideBase(slide, [
    titleStack("How to handle hard objections", "Do not defend everything. Separate what is implemented from what is future architecture.", "INTERVIEW DEFENSE"),
    grid(
      { width: fill, height: hug, columns: [fr(1), fr(1)], columnGap: 48, rowGap: 28, alignItems: "start" },
      [
        compactPanel("This is too static", "Agree. The demo is inspectable. The next version uses AI-proposed graphs with deterministic validation.", C.blue),
        compactPanel("This may over-route", "Agree that calibration matters. Track false positives, avoided routing, clinician confirmation, and patient completion.", C.green),
        compactPanel("Memory is dangerous", "Agree. Memory cannot authorize action. It only suggests questions, falsifiers, and review targets.", C.coral),
        compactPanel("We already have triage", "Good. This layer governs what triage is allowed to infer and do under uncertainty.", C.tealDeep),
      ],
    ),
    footer(),
  ]);
  addNotes(slide, `
This is your anti-fragile slide.

The pattern:
1. Agree with the serious part of the objection.
2. Clarify the boundary.
3. Say how production would validate it.

Example:
- "Yes, a static rule system cannot cover all medicine. That is why I would not scale it by hand-writing templates. I would use AI to propose the expert-system graph, then validate and execute it with governed deterministic software."
`);
}

function addClose() {
  const slide = deck.slides.add();
  slideBase(slide, [
    titleStack("The ask", "Use the demo to start a working conversation, not to claim finished production software.", "CLOSE"),
    grid(
      { width: fill, height: fill, columns: [fr(0.9), fr(1.1)], columnGap: 60 },
      [
        column(
          { width: fill, height: fill, gap: 22, justify: "center" },
          [
            text("Where would this boundary layer plug into your highest-leverage workflow?", { width: wrap(760), height: hug, style: { fontSize: 50, bold: true, color: C.ink } }),
            text("Refills, low-acuity closure, physician handoff, or post-chat escalation persistence.", { width: wrap(740), height: hug, style: { fontSize: 26, color: C.muted } }),
          ],
        ),
        column(
          { width: fill, height: fill, gap: 22, justify: "center" },
          [
            compactPanel("First 30 days", "Shadow-mode one workflow, map failure modes, define metrics, and run historical replay.", C.tealDeep),
            compactPanel("First 60 days", "Integrate with one intake surface and clinician feedback loop.", C.blue),
            compactPanel("First 90 days", "Governed promotion process for new nodes, rules, and memory recalls.", C.violet),
          ],
        ),
      ],
    ),
    footer("Deck sources: app verification, local tests, Fly deployment, and generated demo artifacts."),
  ]);
  addNotes(slide, `
Close with a collaborative question.

Say:
- "I would love to understand where this kind of boundary layer would matter most inside your current system."
- "I am not asking you to accept this exact implementation. I am showing the way I think and what I can build."

If the interview goes well, offer a specific next step:
- "Give me one de-identified failure mode or tricky workflow and I can show how I would map it into this boundary framework."
`);
}

[
  addCover,
  addContext,
  addThesis,
  addDemoPath,
  addPasteSlide,
  addArchitecture,
  addProvenance,
  addRecommendations,
  addRealVsPrototype,
  addShowpieces,
  addValue,
  addWhatIBring,
  addExecutiveQuestions,
  addDevQuestions,
  addHardObjections,
  addClose,
].forEach((fn) => fn());

const pptxBlob = await PresentationFile.exportPptx(deck);
await pptxBlob.save(path.join(outDir, "output.pptx"));

for (let i = 0; i < deck.slides.items.length; i += 1) {
  const slide = deck.slides.items[i];
  const slideNo = String(i + 1).padStart(2, "0");
  const png = await slide.export({ format: "png" });
  await fs.writeFile(path.join(scratchDir, `slide-${slideNo}.png`), Buffer.from(await png.arrayBuffer()));
  const layout = await slide.export({ format: "layout" });
  const layoutOut = typeof layout.text === "function" ? await layout.text() : JSON.stringify(layout, null, 2);
  await fs.writeFile(path.join(scratchDir, `slide-${slideNo}.layout.json`), layoutOut);
}

await fs.writeFile(
  path.join(scratchDir, "deck-summary.json"),
  `${JSON.stringify({ slides: deck.slides.items.length, output: path.join(outDir, "output.pptx") }, null, 2)}\n`,
  "utf8",
);

console.log(`wrote ${path.join(outDir, "output.pptx")}`);
