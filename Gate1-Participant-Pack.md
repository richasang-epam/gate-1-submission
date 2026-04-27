# Gate 1 — Participant Pack

**Gate:** Gate 1 (Week 1) — AI-Native Specification
**Released:** Monday 27 April 2026, morning (scenario previously unseen).
**Timed exercise:** 2.5 hours, starts when you open this pack. Submissions close 2.5 hours after release.
**Live walkthrough:** ~10 minutes, scheduled same day in the afternoon.

Read this pack end-to-end before you start. The clock begins when you open it, not when you finish reading it — but reading the whole pack first will pay back more than the time it costs.

---

## 1. What Gate 1 is testing

Gate 1 tests a single core skill: **given a previously unseen business problem, design an agentic solution and produce a specification precise enough for an AI coding agent to build from.**

The output is a **written spec**, not a slide deck, not a strategy memo, not a product pitch. Treat it as the document you would hand to Claude Code (or any capable AI coding agent) tomorrow morning and expect real code back. If a builder — human or AI — would have to guess what you meant, the spec is not yet done.

You will produce five deliverables (Section 4 below) against the scenario in Section 3. You may use any tools you already have set up — including AI assistants — but the spec you submit must be the one you would stand behind in a walkthrough. You will be challenged on it live.

---

## 2. How to run the 2.5 hours

A rough shape that has worked for test run; adapt as you like:

- **0–30 min:** Read the scenario twice. Note what's stated, what's implied, what's missing. List your unknowns before you start building answers.
- **30–120 min:** Draft deliverables 1–3 (problem statement, delegation analysis, agent specification). These are the substance.
- **120–140 min:** Draft deliverables 4 and 5 (validation, assumptions & unknowns). These are where honesty shows.
- **140–150 min:** Final pass. Hunt for hand-waving verbs, undefined state, integration vagueness, assumptions not marked as assumptions.

Near-pass is a fail. A spec that's 90% confident and 10% vague on the parts that matter reads the same to a coach as a spec that's 60% confident — because the parts that matter are the parts being assessed.

---

## 3. Scenario

> A mid-size insurance company's claims team processes 300 first-notice-of-loss (FNOL) reports per day. Each report arrives as unstructured text (email, phone transcript, web form) and must be: triaged by severity, validated against policy coverage, routed to the appropriate adjuster, and acknowledged to the claimant — all within 2 hours of receipt. Currently, a team of 12 specialists handles this manually. Average handling time is 22 minutes per claim. Error rate on routing: 18%. SLA breach rate: 31%.
>
> The client wants to explore whether AI can handle most of this. They are open to full automation where appropriate but insist on human oversight for high-value or ambiguous claims. They have a modern CRM with APIs, a legacy policy administration system with SOAP endpoints, and a document management system. They have no AI infrastructure today.
>
> **Design the agentic solution.**

That is the full scenario. There is no appendix, no SOW, no sample claim data. The constraints are what is written above. The numbers are what is written above. The systems are what is written above. If you need more than what is here, that is an assumption — name it as one in Deliverable 5.

---

## 4. Deliverables

Five deliverables, all in one document. Any format that renders cleanly as text or markdown is fine. Length is not scored — precision is.

| # | Deliverable | Guidance |
|---|---|---|
| 1 | **Problem statement & success metrics** | Frame the problem from both the **claimant's** perspective and the **business's** perspective. Define measurable outcomes that would justify the investment. Reference the scenario's specific numbers. |
| 2 | **Delegation analysis** | For each part of FNOL processing, decide: fully agentic / agent-led with human oversight / human-led with agent support / human only. Justify each boundary. Arbitrary boundaries ("this feels like a human decision") will be challenged. |
| 3 | **Agent specification** | Purpose, scope, inputs/outputs, decision logic, escalation triggers, integration contracts, state model, error handling. Precise enough that Claude Code could begin building from it. This is the largest deliverable — expect to spend the most time here. |
| 4 | **Validation design** | How do you know the agent is working? What do you test? What does failure look like — not just obvious failure, but *quiet* failure (the agent is wrong and no one notices)? |
| 5 | **Assumptions & unknowns** | What are you assuming about the client's data, systems, organisation, or the problem itself? What must be validated with the client before building? **At least 5 genuine unknowns.** Filler ("we assume the client has good data") does not count. |

**Known gaps are better than hidden gaps.** If you do not have time to fully specify a part of the contract (e.g., the exact SOAP request/response shape for the legacy policy system), name it explicitly as a scope-out with a concrete plan to resolve. A senior FDE ships specs with known-and-labelled gaps under time pressure — silent omissions on integration contracts do not earn the same read.

---

## 5. Live walkthrough

After the timed exercise, each participant gets a ~10-minute walkthrough with a coach:

- **~3 minutes** — you summarise your approach. No slides. Walk the coach through the document. This is the test of your way of thinking - so doc is expected to demostrate this. 
- **~7 minutes** — coach challenge. Expect questions in the shape of *"Why did you draw the human/agent boundary here?"*, *"What happens when this assumption is wrong?"*, *"How would you know this agent is failing in production?"*.

The walkthrough is not a presentation. It is a judgment test: can you defend your boundaries, explain your reasoning, and hold your ground (or update cleanly) under pressure?

---

## 6. Evaluation criteria

The rubric assesses seven dimensions. You are not being shown weights or band thresholds — coaches score, and the point of the exercise is the work, not the optimisation. Internalise the criteria; do not optimise against a weight column.

1. **Problem framing** — Is the problem framed from both user **and** business perspectives, with measurable outcomes, specific to this scenario? (Generic framings that could be written without reading the scenario will be called out.)
2. **Delegation justification** — Are delegation boundaries justified with clear rationale, not drawn arbitrarily? Is the codifiability of each agentic step addressed?
3. **Agent spec precision** — Would an AI coding agent need to guess at intent? Entities defined, state machines named, integration contracts explicit (endpoint / auth / request / response / timeout / retry / fallback), decision logic with concrete thresholds.
4. **Validation design** — Does validation cover happy path, edge cases, and failure modes? Does it include how you would *detect* the agent is wrong — not just confirm it is right?
5. **Assumptions & unknowns** — Are assumptions identified honestly and unknowns surfaced? At least five genuine, scenario-relevant items, not filler.
6. **Live walkthrough** — Can you explain *why*, not just *what*? Do you defend boundaries with reasoning, and update cleanly when challenged?
7. **Professional quality** — Is the document clear, organised, readable? Would a builder pick it up and know where to look for each piece?

---

## 7. What anti-patterns will cost you

Not exhaustive — but these are the failure modes coaches watch for closely:

- **Hand-waving verbs.** "Handles claims triage, routes intelligently, manages exceptions" — with no inputs, outputs, or decision logic behind the verbs.
- **Implicit state.** References to a claim being "validated", "routed", "acknowledged" without defining what creates, invalidates, or checks that state.
- **Integration hand-wave.** "Integrates with CRM / policy admin / DMS" without naming endpoint, auth, request/response shape, timeout, retry, or fallback. (A named scope-out with a plan is fine — a silent omission is not.)
- **Generic problem framing.** A problem statement that could have been written without reading the scenario — no mention of the 300/day volume, the 22-minute handling time, the 18% routing error, the 31% SLA breach, the SOAP legacy, or the claimant perspective.
- **Vanishing claimant.** Framing the problem purely from the insurance company's efficiency perspective. The scenario distinguishes claimant from customer, and the claimant perspective is part of the problem.
- **Filler assumptions.** Assumptions lists that are platitudes ("We assume the client has good data") with no specific testable claim.
- **Bluffing.** Confident-sounding claims about systems, data, or constraints the scenario did not state — and the participant did not mark as an assumption. (If the scenario says SOAP endpoints and you design around REST, that is an assumption. Name it.)

---

## 8. Submission logistics

- **Format:** Markdown or plain text, one document containing all five deliverables. Headings per deliverable (1 through 5) so the coach can navigate.
- **Filename:** Gate1-<First Name>-<Last Name>.md/txt
- **Where to submit:** General Channel/Gate 1 Submissions Folder - https://epam.sharepoint.com/:f:/r/sites/EPAMFDETrainingProgramApril2026/Shared%20Documents/General/Gate%201%20Submissions?csf=1&web=1&e=Exr544.
- **Deadline:** 2.5 hours from scenario release. Late submissions are flagged and handled separately as negotiated with the coach; partial submissions are accepted and scored on what is present.
- **Walkthrough scheduling:** Your slot is on the shared afternoon schedule posted alongside this pack.

If something goes wrong — tooling failure, system outage, lost work — contact your squad lead immediately. Do not rebuild silently past the deadline.

---

## 9. A final framing

You are not being asked to solve the full problem. You are being asked to produce a spec that makes the problem *buildable* — precise enough that an AI coding agent could start, honest enough that the gaps it cannot build from are named rather than hidden, and opinionated enough that the delegation boundaries are defensible under live challenge.

Near-pass is a fail. Write the spec you would stand behind in front of a senior FDE who has ten more of these to read today.

Good luck.
