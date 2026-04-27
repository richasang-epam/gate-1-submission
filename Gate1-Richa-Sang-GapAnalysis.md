# Spec Buildability Gap Analysis
**Spec:** Gate1-Richa-Sang.md
**Question:** How confidently can Claude Code build from this spec as-is?
**Verdict: ~65% buildable right now.**

---

## Green — Buildable immediately (no guessing needed)

| Component | Why it's ready |
|---|---|
| Data entity schemas | Field names, types, and enums all explicit |
| State machine | Every state and transition condition is named |
| Severity classifier | Deterministic rules with concrete thresholds |
| Routing algorithm | Steps 1–5 are unambiguous |
| Escalation trigger table | All 10 triggers with reason codes |
| CRM integration | Method, path, request/response shape, retry/timeout, fallback all specified |
| Error handling | Per-failure-mode table is complete |
| Tool function signatures | Parameters and return types defined |

---

## Amber — Buildable but Claude Code would guess, not ask

| Gap | What it would guess | Risk |
|---|---|---|
| DMS request/response body | Invents a JSON shape for `POST /documents` | May not match the real system |
| Redis fallback queue | Picks a key structure and TTL arbitrarily | May not survive restarts correctly |
| Circuit breaker implementation | Picks a library (e.g. `pybreaker`) | Fine for a prototype, not validated against client environment |
| SLA clock check timing | Checks at the start of each tool call | Could miss a slow tool mid-execution |

---

## Red — Would block the build entirely

### 1. Orchestration model is undefined
The spec names `FNOLOrchestrator` but never says what it *is*. Claude Code cannot write the entry point without knowing the runtime. Options it would have to guess between:
- Claude API agent with `tool_use`
- Plain Python script running sequentially
- Workflow engine (Temporal, Prefect, Airflow)
- Lambda function triggered by SQS/SNS

**Fix:** Add one paragraph to §3.1 stating the runtime. Example: *"FNOLOrchestrator is a Python process using the Claude API with `tool_use`. Each incoming claim triggers a synchronous agent loop invoked by a queue consumer."*

---

### 2. `parse_claim_document` has no prompt, no model, no confidence definition
The tool says "calls LLM extraction with structured output schema" — but three things are missing:

- **Which LLM / which API?** Claude? GPT-4? Same account as the orchestrator?
- **What is the extraction prompt?** No system prompt or user prompt template is given.
- **How is `extraction_confidence` (0.0–1.0) calculated?** This float gates every escalation decision in the system. The spec never says where it comes from. Options:
  - LLM self-reports a confidence score
  - Fraction of required fields successfully extracted (non-null)
  - A separate validation pass after extraction
  - Some combination

**Fix:** Add a subsection to §3.4 specifying: the model, the prompt template (even a skeleton), and the exact formula for `extraction_confidence`.

---

### 3. SOAP integration is unbuildable
Correctly scoped out — but this means the entire policy validation step (`lookup_policy`) can only be a stub. That is ~25% of the agent's critical path. The spec handles this correctly with a labelled scope-out and resolution plan, but it should be noted: **a builder cannot wire up the policy validation component until the WSDL and sample payloads are obtained.**

**No fix needed in the spec** — the scope-out is honest and has a resolution plan. Just be aware this component ships last.

---

### 4. Human review re-entry mechanism is not specified
The state machine shows `ESCALATED → HUMAN_REVIEWED` when "human acts in queue" — but the spec never says *how* the agent learns a human has acted. A builder must pick one of:
- Webhook pushed from CRM to the agent when a reviewer submits a decision
- Agent polls `GET /review-queue/{task_id}` on a timer
- Human action publishes an event to a message queue the agent consumes

Without this, the escalation loop cannot be wired up end-to-end.

**Fix:** Add one sentence to §3.5. Example: *"Agent polls `GET /review-queue/{task_id}` every 60 seconds. When `status = completed`, it reads `human_decision` from the response and re-enters the pipeline at the ROUTING step."*

---

### 5. Acknowledgment templates are undefined
`send_acknowledgment` takes `template_id` and `template_data` but the spec provides:
- No list of template IDs
- No field list per template (what goes in `template_data`?)
- No definition of where templates are stored or managed

Claude Code would invent a template format that may be incompatible with the CRM's `POST /communications` endpoint.

**Fix:** Add a template reference table to §3.6. Minimum: template ID, trigger event, required `template_data` fields. Example:

| template_id | Triggered when | Required template_data fields |
|---|---|---|
| `receipt_acknowledgment` | On intake (step ①) | `reference_number`, `claimant_name` |
| `routing_complete` | After adjuster assigned (step ⑥) | `reference_number`, `adjuster_name`, `next_contact_window` |
| `escalation_notice` | On escalation to human queue | `reference_number`, `estimated_resolution_time` |

---

### 6. Two-stage acknowledgment is contradicted
The **flow diagram** says "Send receipt acknowledgment immediately" at step ①, before any processing.
The **tool signatures** show `send_acknowledgment` called only after adjuster routing (step ⑥).

These are inconsistent. A builder would have to choose one or invent a two-call pattern that isn't specified.

**Fix:** Decide and state explicitly. The recommended design is two acknowledgments:
- **Immediate receipt ACK** (step ①): sent on intake, uses `receipt_acknowledgment` template, contains only reference number.
- **Routing complete ACK** (step ⑥): sent after adjuster assigned, uses `routing_complete` template, contains adjuster name and next steps.

Update the tool signature section to reflect two separate calls with different template IDs.

---

## Priority order for closing gaps

| Priority | Gap | Effort to fix |
|---|---|---|
| 1 | Orchestration model | 1 paragraph in §3.1 |
| 2 | `extraction_confidence` formula | 3–5 sentences in §3.4 |
| 3 | Human review re-entry mechanism | 1–2 sentences in §3.5 |
| 4 | Acknowledgment template definitions | One table in §3.6 |
| 5 | Two-stage acknowledgment clarification | One paragraph + tool signature update |
| — | SOAP integration | Cannot fix until client discovery is done |

Closing gaps 1–5 would move the spec from **~65% buildable to ~85% buildable.** The remaining 15% is the SOAP integration, which is blocked on client discovery and correctly labelled as such.
