# Interview Demo Cheat Sheet

Purpose: use ClinSafer as evidence of how you think, not as a product pitch. The audience may be defensive about their existing product. Your job is to show humility, alignment, speed of execution, and unusual cross-domain judgment.

Live app:

```text
https://clinsafer.fly.dev/
```

Deck:

```text
decks/clinsafer-interview-demo/output/output.pptx
```

## Core Positioning

Use this frame first:

> I built this less as a product proposal and more as a way to make my thinking concrete. Interviews can become words about safety, product judgment, AI risk, and patient trust. I wanted you to be able to evaluate how I think, not just hear me describe it.

Then reduce defensiveness:

> I am assuming your team already has strong clinical reasoning, escalation logic, physician handoff, and safety infrastructure. I am not claiming this exact prototype is something you need. I built it to show how I approach the layer between AI reasoning and permission to act.

Then make the hiring case:

> What I think I can bring is the bridge: medicine, software, AI behavior, patient psychology, workflow operations, business pressure, and governance. I can take an ambiguous clinical/product risk, turn it into architecture, build a working artifact, expose the logic, test it, deploy it, and improve it from feedback.

## 30-Second Version

Use if time is tight:

> This is a working artifact I built in about a week to show how I think. It is not an AI doctor and not a critique of your system. It is a governed boundary layer around clinical AI: what did the patient say, what can safely be treated as fact, what remains unknown, what may be distorted by human factors, and what autonomy is allowed next.
>
> The reason I built it is that words are cheap in interviews. This makes my thinking inspectable. It shows how I translate clinical safety, patient trust, provider burden, and business realities into a working system.

Click path:

1. Open app.
2. Click `Show Cost-Fear Case`.
3. Click `Analyze This Encounter`.
4. Show `Statement vs Fact`.
5. Show `Provenance & Authority`.
6. Jump to `Final Recommendations`.

Close:

> The point is not that this prototype is the answer. The point is that I can convert ambiguous clinical/product risk into a buildable, testable, governed system.

## 5-Minute Version

### 1. Open With Deference

Say:

> I am assuming your team already has strong diagnosis, triage, escalation, prescription, and clinician-review infrastructure. I built this to show a narrower question: when should an AI system not act yet, even if it can generate a medically plausible answer?

Avoid:

> Your product may miss this.

Use instead:

> Some of this may overlap with what you already do. I would be interested in where your approach is stronger and where this kind of boundary thinking might still be useful.

### 2. Name The Problem

Say:

> The narrow problem is not whether AI can reason medically. It is whether the system knows the limits of what it can safely infer from the encounter.

Then:

> Patient answers are measurements shaped by context. A denial is not always reliable negative evidence. Silence is not absence. Stale data is not current safety. A patient trying to appear tough, avoid cost, avoid embarrassment, or get a specific outcome may shape the transcript before the AI ever reasons over it.

Key line:

> Do we know what we do not know, and are we setting dynamic boundaries around interpretation?

### 3. Explain The Human Premise

Say:

> The difficult part is often humans being human. Patients bring life experience, fear, family beliefs, prior medical experiences, cultural assumptions, internet searches, embarrassment, access pressure, and personal identity into the encounter.

Then:

> I am not blaming patients. I am designing for the reality that people answer medical questions through the lens of their lives.

Add customer-specific point:

> Different customer populations may have different vocabulary, trust patterns, access barriers, health literacy, and reasons for withholding or reshaping history. The boundary layer should be configurable and learnable, while still governed.

### 4. Explain Why You Built It

Say:

> One problem in interviews is that words are just words. Anyone can say they care about clinical safety, patient trust, governance, or AI risk. I built this in about a week so you could evaluate how I think in action.

Then:

> My goal is to show possible alignment: I think about AI medicine as clinical reasoning plus patient psychology plus workflow operations plus revenue pressure plus risk governance plus software architecture.

Key line:

> I wanted you to be able to evaluate how I think, not just hear me describe how I think.

### 5. Make The Hiring Case

Say:

> The practical hiring question is: why take a risk on me? What I think I can bring is not just coding and not just clinical interest. I can sit at the intersection of medicine, software, AI behavior, patient psychology, business operations, and risk governance, and turn that into working systems.

Then:

> A lot of people can talk about AI safety. A lot of people can build features. The value I am trying to show is the bridge: finding a subtle real-world failure mode, translating it into system architecture, making it visible in the UX, and thinking through safety, clinician workload, trust, revenue, and governance.

Key line:

> If you hired me, I think I could help convert ambiguous clinical/product risks into buildable, testable, governed systems.

## Demo Walkthrough

### Screen 1: Encounter

Click:

1. `Show Cost-Fear Case`
2. `Analyze This Encounter`

Say:

> I will use one case to show the thought process. The case is not meant to be exotic. It is meant to show how a normal-looking telemedicine conversation can become unsafe if the system over-trusts the patient’s framing.

### Section: Statement Vs Fact

Say:

> This is the core idea: separate what the patient said from what can safely be treated as fact.

Point to:

- patient says no chest pain,
- patient describes tight indigestion with walking,
- cost/work pressure asks for delay,
- the system does not treat denial as clean negative evidence.

Say:

> In real telemedicine, the transcript is not ground truth. It is a measurement artifact shaped by vocabulary, fear, cost, work, embarrassment, culture, health literacy, prior experiences, and what the patient hopes the answer will be.

Key line:

> This is the layer I naturally think about: not just what diagnosis might fit, but what the system is allowed to infer from the data it actually has.

Add patient goal-seeking:

> Patients often enter with a desired outcome. For example, someone may say, "I am having trouble sleeping and I need a sleep medication." They may underplay caffeine amount, caffeine timing, alcohol, stimulant use, shift work, sleep apnea symptoms, or anxiety because they believe the answer is already clear. The system should not punish that. But it must distinguish what the patient wants from what the evidence supports.

Business/trust point:

> If the system simply blocks the desired outcome, that can create churn. If it grants it too easily, that creates safety and regulatory risk. The better answer is goal-preserving redirection: understand what the patient wants, ask the smallest useful question, and explain the safe path forward.

Patient-advocate language:

> The patient should feel the system is advocating for them, not judging them. Instead of "stop coffee, stop alcohol, exercise, eat perfectly," the system should say: "Let’s reframe your goal. You want to sleep better tonight and function tomorrow. To do that safely, I need to know what may be keeping your body awake or making sedating medicine risky."

### Section: Provenance & Authority

Say:

> This section is about authority. Not every signal should have the same power.

Point to:

- curated clinical rules,
- curated safety guardrails,
- AI candidate signals,
- learned priors,
- memory recall,
- ensemble governor.

Say:

> The architecture is not "AI decides." It is "AI proposes, governed layers dispose."

Then:

> A model can notice subtle patterns, but it cannot independently authorize care, prescribe, close a case, or create a hard stop. Signals carry authority metadata.

Hiring point:

> This is the kind of discipline I would bring: not just making models smarter, but making their authority explicit, bounded, auditable, and useful in product workflows.

### Section: Known Unknowns Map

Say:

> This is where the system shows what it does not know.

Point to categories:

- missing,
- uncertain,
- distorted,
- contradictory,
- remote-unknowable,
- objective-needed.

Say:

> Telemedicine fails when absence of evidence becomes evidence of absence. If diaphoresis was never asked, it cannot be summarized as absent. If vitals are missing, the system should not assume they are normal.

Key line:

> This is not just explainability. It is decision hygiene.

Provider point:

> The clinician should not have to reconstruct this from a raw transcript. The system should provide a boundary map: what is known, what is not known, what may be distorted, and what would change the decision.

### Section: Safety Decision And Autonomy Boundary

Say:

> This is where analysis becomes permissioning.

Then:

> The danger is not only a wrong answer. The danger is an answer being acted on at the wrong autonomy level.

Key line:

> This is AI as a governed actor, not just AI as a text generator.

Actionable-vs-generative point:

> Generative output can sound fluent and medically reasonable but still be operationally useless or unsafe. Actionable output tells the system, patient, clinician, and business what to do next, what not to do, and why.

Sharper line:

> The bar is not "can the AI explain itself?" The bar is "can the system safely decide what is allowed next?"

### Section: Immediate Next Steps

Say:

> The goal is not to ask every possible medical question. The goal is to ask the smallest set of questions that could change the autonomy boundary or improve the handoff.

Key line:

> Each question should earn its place.

Provider-burden point:

> If the case can be safely resolved with one clarification, ask it before routing. If it cannot be safely resolved, route with the reason already organized. Either way, reduce low-value clinician work.

### Page: Final Recommendations

Say:

> This is the page I care about most, because this is where analysis becomes action.

Point to:

- disposition,
- immediate actions,
- do-not-infer boundaries,
- critical evidence,
- next questions,
- patient-facing message,
- clinician handoff,
- Human Factors Boundary,
- governance follow-up,
- quality metrics.

Say:

> This is intentionally not just a generated paragraph. It is structured operational output.

Human Factors Boundary:

> This section does not label the patient. It identifies how patient goals, fear, embarrassment, access pressure, anxiety framing, stoic minimization, or desired outcomes may alter answer reliability.

Then:

> The response is not "the patient is unreliable." The response is: what can the system safely infer, what should it not infer, and what respectful question would close the boundary?

Provider-burden driver:

> A major design constraint here is provider burden. If a safety layer creates more work without improving the handoff, it will fail operationally. The system should absorb complexity upstream so the provider receives fewer, better, more actionable decisions.

Key line:

> The driver is burden reduction through structured complexity management.

## Prove It Is Interactive

If they ask whether it is fixed copy, do this:

1. Go back to `Encounter`.
2. Add a dialogue line.
3. Use:

```text
Question: Anything else worrying you?
Answer: I am probably just overreacting, but I do not want to make a fuss. I searched online and now I am scared it is something bad.
Concept: care_context
```

4. Click `Analyze This Encounter`.
5. Go to `Final Recommendations`.
6. Point to `Human Factors Boundary`.

Say:

> Now the human factors layer changes. It is picking up anxiety framing, fear, and minimization as reliability modifiers. The system does not diagnose the patient as anxious. It changes what it is willing to infer and how it asks next.

Then:

> That matters because real transcripts evolve. The safety layer has to adapt dynamically, not just run a fixed checklist.

## If They Say "We Already Do This"

Say:

> That would make sense, and I would expect a mature system to handle many of these pieces already.

Then:

> The reason I am showing this is not to claim you lack this. It is to show how I decompose the problem: patient language, evidence reliability, inference boundaries, authority, autonomy, workflow burden, and governance.

Then ask:

> Where does your team currently see the most friction: patient disclosure, clinician handoff quality, edge-case safety, physician routing yield, patient trust, or governance of model-generated recommendations?

If they ask what is new:

> The novelty is not one isolated rule. It is the integrated method: statement-versus-fact boundaries, human factor reliability modifiers, provenance authority, ensemble autonomy caps, actionable recommendations, and governance feedback in one workflow.

## If They Challenge The Rules

Say:

> The current implementation is deliberately inspectable. For production, I would expect AI-generated or AI-assisted expert-system graphs, simulation, clinician review, outcome calibration, and governed template promotion. But I would still keep the authority boundary explicit.

Then:

> I am not trying to hide behind a model. I want the system to be inspectable enough that clinicians and engineers can argue with it productively.

## If They Challenge Clinical Validity

Say:

> This is an interview artifact, not a validated medical device. The claim is not clinical validation. The claim is that the methodology is concrete, testable, auditable, and extensible.

Then:

> In production I would want retrospective replay, clinician-labeled outcomes, false-positive and false-negative review, patient abandonment metrics, and governance approval before rule promotion.

## If They Ask What You Would Do First If Hired

Say:

> I would start in shadow mode. Pick one workflow where automation, clinician routing, patient trust, and revenue all intersect. Replay recent encounters, map the boundary failures, measure provider burden, and identify which clarifying questions actually change disposition.

Then:

> I would not start by adding a giant feature. I would start by finding one high-leverage ambiguity and making it measurable.

## Metrics To Mention

Use these if asked about business value:

- provider time-to-decision,
- routed-case yield,
- clinician override rate,
- clarification-to-resolution rate,
- abandonment after boundary messages,
- patient satisfaction after blocked requests,
- repeat visit / return engagement,
- percentage of routed cases where one clarification would have avoided handoff,
- percentage of autonomous cases later corrected by clinician,
- quality of clinician handoff.

## Best Closing

Say:

> What I am trying to show is not that this prototype is the answer. It is how I think and how I work. I can take ambiguous clinical/product risk, make it concrete, build quickly, expose the logic, test it, and connect safety to patient trust, provider burden, and business reality.

Then ask:

> Where inside your current system would this kind of boundary thinking be most useful or most wrong?

That question is useful because either answer becomes a working conversation.

