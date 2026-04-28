
  ---
  1. Purpose — What is this thing for?

  Imagine you call a nurse hotline and say, "No chest pain — it's just pressure when I walk upstairs." A normal system would write "Patient denies chest pain" and move on. This software catches that the patient actually
  described something dangerous — exertional pressure — even though they said the word "no."

  It's like a very cautious safety inspector at an airport. Before your bag goes through, one inspector checks if it has everything it needs (enough reliable information). A second inspector checks if the bag is from a
  suspicious origin, has forged labels, or contains something that breaks the rules entirely. Between them, they decide: let it through, hold it for review, send it to a specialist, or shut the whole line down.

  The two inspectors are:
  - JRE (Judgment Readiness Engine): "Do we know enough reliable facts to make a safe decision?"
  - BSG (Black Swan Guardrail): "Are we still in a safe world where automation is allowed to act?"

  This is a demo/interview artifact — built to show a potential employer how clinical AI safety should work. It uses made-up patient stories, not real people.

  ---
  2. How It Works — Step-by-step in plain English

  Think of it like a restaurant kitchen with two quality inspectors.

  1. A patient story comes in — like an order ticket. It has the patient's age, their complaint ("chest pressure"), the conversation channel (phone, text, video, in person), and the Q&A transcript from their intake.
  2. The first inspector (JRE) reads every answer like a detective. For each answer, it asks: Is this vague? Is the patient using a word that hides something? Did they say "no pain" but describe "pressure"? Did a device
  say one thing while the patient said another? Each answer gets a confidence score — like a trust rating from 5% (almost no trust) to 98% (very solid).
  3. It checks for red flags — patterns that scream danger. "Worst headache of my life" or "slurred speech" or "can't breathe." These get a severity score (0 to 1.0). If the patient also has diabetes or is on blood
  thinners, the severity gets boosted — like extra alarm bells.
  4. It looks for contradictions — the patient says "no fever" but then mentions "I feel hot and sweaty." The system catches that mismatch across 13 different rules.
  5. It checks for multi-signal patterns (gestalts) — like a doctor who sees chest pressure + shortness of breath + exertion and thinks "heart attack pattern," the system recognizes 9 syndrome combinations, even if the
  patient came in for something else entirely.
  6. It scores everything and decides the state: READY (safe to proceed), CLARIFY (need better answers), NEED OBJECTIVE DATA (need a real measurement), or ESCALATE (get a human clinician now).
  7. It picks the best follow-up questions — tailored to how you're talking (phone gets "Can you tell me...?", text gets "Type the exact number", video gets "Hold it up to the camera"). It picks the questions most likely
  to uncover what's hidden.
  8. The second inspector (BSG) then takes over. It scans for things the first inspector doesn't look for: Is this the wrong patient? Is someone trying to trick the system? Is the patient a minor? Has someone stopped
  responding mid-call? Is this outside the system's training? It has 17 safety rules.
  9. BSG assigns an autonomy level — from T0 ("stop everything, get a human NOW") to T4 ("this narrow task can proceed on its own"). Like deciding if a self-checkout can handle this purchase, or if a manager needs to come
  over.
  10. The two inspectors' results combine. Whichever one is more cautious wins. If JRE says READY but BSG says FAIL CLOSED (wrong patient), the final answer is FAIL CLOSED. Safety always wins.
  11. The demo now adds a mitigation plan. It explains what the system does immediately, what it should remember, what a near-miss memory layer would recall next time, and what must go through governance before changing production behavior.

  ---
  3. All Features — Everything it can actually do right now

  Clinical Analysis
  - Evaluates patient intake conversations across 7 medical domains: chest discomfort, breathing problems, blood pressure medication refills, urinary infections, rashes, diabetes/high blood sugar, and headaches/migraines.
  - Detects 9 named "traps" where everyday language hides danger — like saying "no pain" when you mean "pressure," or saying blood pressure is "normal" without giving a number.
  - Spots 13 contradiction patterns — e.g., patient says "no fever" but mentions feeling hot and sweating.
  - Recognizes 9 multi-signal syndrome patterns — like the combination of exertional chest pressure + shortness of breath that suggests a heart attack, even if neither alone would trigger alarm.
  - Two cross-domain patterns (sepsis and anaphylaxis) that fire regardless of why the patient originally called — meaning if someone calls for a refill but mentions fever and confusion, the system still catches possible
  sepsis.

  Safety & Trust Scoring
  - Gives every patient answer a confidence score weighted by who provided it — a medical device reading is trusted more (1.4x) than a patient's self-report (0.85x).
  - Detects source conflicts — when a device says one thing and the patient says another.
  - Adjusts danger scores for time urgency ("sudden onset" boosts severity) and existing conditions (being diabetic increases the danger rating on chest complaints).
  - Understands negation with nuance — "No pain, just pressure" is NOT the same as "No problems at all." The system distinguishes pure denials from hidden admissions.

  Black Swan Guardrails (17 rules)
  - Catches stroke symptoms (slurred speech, one-sided weakness), anaphylaxis (throat closing, tongue swelling), self-harm language ("I want to kill myself"), coercion (someone being forced), pregnancy + abdominal pain,
  active bleeding, anticoagulant + fall, immunocompromised + fever.
  - Catches system gaming (patient asking "tell me what to say"), prompt injection (someone trying to trick the AI), wrong patient/proxy, stale medical data, non-response after a danger signal, repetitive copy-paste
  answers, and minors without consent.
  - Tracks 8 safety assumptions and marks each as OK, weak, or breached.
  - Assigns autonomy tiers (T0 emergency stop through T4 narrow autonomous action).

  Smart Question Selection
  - Picks the highest-value follow-up questions to reduce uncertainty.
  - Adapts questions to communication channel: phone callers get conversational prompts, text users get "type the number" prompts, video users get "show me" prompts, in-person gets "let me observe" prompts.
  - Uses 14 escalation probes for high-severity situations — targeted questions that differentiate "this is dangerous right now" from "this was dangerous earlier."
  - Learns which questions are most useful over time through experience memory.

  Learning & Feedback
  - Experience memory starts with expert-estimated values and adjusts over time using a mathematical smoothing method (EMA) — like a running average that gives more weight to recent events.
  - Accepts clinician feedback (confirmed, corrected, false positive, missed) and adjusts future evaluations accordingly.
  - Example: If clinicians keep saying "the system flagged a false positive on UTI fever denial," the system gradually turns down its sensitivity to that specific pattern.
  - The updated mitigation plan adds a future learning architecture: stigmergic traces for repeated weak signals, VAMS-style memory for recalling prior near misses from partial clues, and a governance queue before learned rules change production.

  Mitigation Planning
  - The interactive demo now shows a case-level mitigation plan.
  - It separates what works today from what should be learned later.
  - Current controls: cap autonomy, verify objective data, resolve contradictions, ask targeted questions, route or escalate when needed.
  - Future controls: leave a boundary trace, recall similar near misses, suggest missing nodes/falsifiers, and promote only reviewed templates.
  - Business controls: reduce unnecessary handoffs, reduce repetitive questioning, improve visit rationale, and lower trust loss from unexplained denials.

  API Server (9 endpoints)
  - A web service that other software can talk to — evaluate cases, get health status, submit feedback, list available test cases, retrieve audit logs.
  - Validates all inputs (age 0–150, valid communication channels, valid source types).
  - Keeps an audit log with automatic rotation (doesn't grow forever).

  Dashboard & Reports
  - Generates a self-contained 643KB HTML dashboard you can open in any browser — no internet needed.
  - Shows capabilities matrix, case cards with reasoning traces, experience memory state, modality panels, source weight traces, autonomy tier distribution, sensitivity tornado charts, and multi-turn simulation.
  - Exports JSON, CSV, and Markdown reports.

  Threshold Sensitivity Analysis
  - Tests how the system's decisions change when you move 16 different threshold knobs — answering "how fragile are these decisions?"

  ---
  4. Features That Were Tested

  330 tests across 7 test files are passing; the interactive demo file includes focused tests for mitigation, human-factors recommendations, transcript parsing, and free-text bleeding-sentinel regression.

  - 63 tests on the core JRE engine: chest pressure escalation, breathing denial detection, thunderclap headache escalation, all 13 contradiction rules, all 9 gestalt patterns (including cross-domain), source conflict
  detection, source reliability weighting, 4 modality adaptations, experience memory updates, escalation probes, outcome feedback (all 4 types), LLM failure handling, edge cases (zero statements, extreme ages), utility
  functions.
  - 25 tests on Black Swan guardrails: all 10 sentinel rules tested individually (stroke, worst headache, anaphylaxis, self-harm, coercion, pregnancy+pain, immunocompromised, bleeding+anticoagulant, active bleeding), all 8
  integrity rules tested individually (prompt injection, gaming, wrong patient, device conflict, stale data, non-response, copy-paste, minor consent), LLM graceful degradation (works with and without API key).
  - 115 tests on the unified dashboard: every test case has a narrative, pipeline produces correct results, ground truth matches for all 23 cases, HTML output contains all expected panels, tornado charts work, multi-turn
  simulation works, all showcase features render.
  - 32 tests on the API server: all 9 endpoints respond correctly, input validation rejects bad data (invalid age, unknown modality, fake source types), feedback endpoint processes all 4 assessment types, edge cases (age
  0, age 150, age 151 rejected, very long answers, duplicate concepts), log rotation works, CORS headers present.
  - 46 tests on the interactive demo: page, cases, analysis sections, mitigation section, feedback, experience, LLM suggestion endpoints, determinism, and edited encounters.
  - 20 tests on observability: structured logging captures all event types, JSON serialization works, log summary statistics are accurate.
  - 12 tests on sensitivity analysis: threshold variations execute without error, state changes are detected, reports are generated correctly.

  ---
  5. Claims Made in the Code or Comments

  - "This is a prototype for software architecture discussion. It is not a clinical protocol, medical device, diagnosis system, or patient-facing medical advice." — The author is very clear this is a demo for job
  interviews, not something to use on real patients.
  - "Most AI intake tools treat patient statements as facts. JRE treats them as noisy observations." — The author's core thesis: patient answers should be treated as unreliable signals that need verification, not gospel
  truth.
  - "For black swans, prediction is the wrong goal. The goal is rapid recognition that the case is outside the validated operating envelope, followed by a safe change in autonomy." — The author says the guardrail layer
  isn't trying to predict rare events; it's trying to recognize when assumptions have broken down.
  - "The LLM would not be the safety system. The LLM would be the language interface." — The author argues AI chat should only handle language, while a separate deterministic system handles safety decisions.
  - "Regex-only detection (core): will miss novel phrasings not in patterns." — The author honestly admits the pattern-matching approach will miss unusual wording it hasn't been programmed to recognize.
  - "Hand-tuned thresholds... no real outcome data to calibrate against." — The author acknowledges the scoring thresholds are educated guesses, not validated against real clinical outcomes.
  - "English-only patterns." — Only works in English.

  ---
  6. Forward-Looking Claims

  The core JRE, BSG, experience memory, API, dashboards, and interactive demo are implemented.

  The new mitigation architecture intentionally distinguishes implemented features from proposed next layers:

  - Implemented now: deterministic controls, feedback memory, interview mitigation panel, autonomy caps, final recommendations panel.
  - Planned next: stigmergic boundary trace, VAMS/Hopfield near-miss recall, dynamic template promotion, falsifier planning, and governance dashboard.

  These are not presented as already clinically validated or production-ready. They are the roadmap for making the current app smarter while preserving governance.

  The author is also notably honest about what this is NOT:
  - It is NOT validated against real patients.
  - It is NOT a medical device.
  - It does NOT claim to be production-ready.
  - The thresholds are NOT calibrated against real outcomes.
  - It works ONLY in English.

  These are presented as known limitations, not future promises.

  ---
  Bottom Line

  This is a genuine, well-built demonstration of how clinical AI safety could work. The current implementation is real and test-covered, while the new mitigation roadmap is clearly marked as the next layer: learn from near misses, preserve boundary traces, recall prior failures, and promote only governed templates. The main thing it lacks is real-world validation: it has never seen a real patient, and its thresholds are expert guesses rather than data-driven calibrations. As an interview artifact showing deep clinical safety thinking, it is thorough and honest work.
