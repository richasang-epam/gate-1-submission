# Gate 1 — FNOL Agentic Processing System

An agentic First Notice of Loss (FNOL) claims processor built on the Claude API (`tool_use` pattern). The orchestrator model (claude-sonnet-4-6) drives a deterministic 9-step pipeline that extracts claim data, validates policy coverage, triages severity, routes to an adjuster, and sends two-stage acknowledgments — all with full audit trails.

---

## Architecture

```
Raw claim text (email / phone transcript / web form)
        │
        ▼
  FNOLOrchestrator  (claude-sonnet-4-6, tool_use loop)
        │
        ├─ parse_claim_document     →  claude-haiku-4-5 sub-call for extraction
        ├─ validate_policy          →  SOAP policy admin (zeep + circuit breaker)
        ├─ assess_severity          →  deterministic 7-rule triage
        ├─ find_available_adjuster  →  CRM REST query (OAuth2)
        ├─ send_acknowledgment      →  two-stage: receipt + routing_complete
        ├─ create_claim_record      →  DMS upload
        ├─ update_claim_status      →  CRM status patch
        ├─ poll_human_review        →  60 s polling, 90 min SLA
        └─ escalate_claim           →  CRM review task + escalation notice
```

### Integration clients

| Client | Protocol | Auth | Notes |
|--------|----------|------|-------|
| CRM | REST/JSON | OAuth2 client credentials | Token cached; Redis fallback queue |
| Policy Admin | SOAP | n/a | zeep + 5-min sliding-window circuit breaker |
| DMS | REST/JSON | API key (`X-API-Key`) | Upload + retrieve documents |

All three clients have drop-in mock implementations — no real HTTP calls needed for development or tests.

---

## Project structure

```
gate-1-submission/
├── fnol_agent/
│   ├── orchestrator.py      # FNOLOrchestrator — main agent loop
│   ├── tools.py             # All 9 tool implementations
│   ├── models.py            # Pydantic v2 data models & ClaimState enum
│   ├── config.py            # pydantic-settings config from env
│   ├── main.py              # SQS consumer entry point
│   └── integrations/
│       ├── crm_client.py    # CRM OAuth2 REST client
│       ├── policy_client.py # SOAP client + CircuitBreaker
│       ├── dms_client.py    # DMS REST client
│       └── mock_clients.py  # Mock implementations
├── tests/
│   ├── conftest.py          # autouse fixture — injects mock clients
│   ├── test_severity.py     # 50 deterministic triage tests
│   ├── test_routing.py      # 10 adjuster routing tests
│   ├── test_extraction.py   # 12 extraction + confidence tests
│   └── test_orchestrator.py # 18 end-to-end orchestration tests
├── dashboard.py             # Streamlit web dashboard
├── demo.py                  # Runs 3 sample claims with mock clients
├── requirements.txt
├── .env.example
└── Gate1-Richa-Sang-v2.md   # Specification document
```

---

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Run the demo (mock clients, no external calls)

```bash
python demo.py
```

Processes three sample claims (LOW / HIGH / MEDIUM severity) and prints full agent output.

### 4. Run the dashboard

```bash
python -m streamlit run dashboard.py
```

Opens at **http://localhost:8501**. Use the sample claims in the sidebar to process claims interactively, view history, and inspect metrics.

### 5. Run the test suite

```bash
python -m pytest tests/ -v
```

87 tests — all should pass with no real API calls (mock clients injected via `conftest.py`).

---

## Severity triage rules

Applied deterministically in first-match order:

| Priority | Condition | Severity | Confidence |
|----------|-----------|----------|------------|
| 1 | Bodily injury | HIGH | 1.00 |
| 2 | Third party involved AND amount > 0 | HIGH | 1.00 |
| 3 | Liability claim | HIGH | 1.00 |
| 4 | Amount > £50,000 | HIGH | 1.00 |
| 5 | £5,000 ≤ amount ≤ £50,000 | MEDIUM | 0.95 |
| 6 | Amount < £5,000 AND property damage | LOW | 1.00 |
| 7 | Default (conservative) | MEDIUM | 0.75 |

Claims with triage confidence < 0.85 are automatically escalated for human review.

---

## Escalation triggers

- Extraction confidence < 0.80 (fewer than 5 of 6 required fields extracted)
- Triage confidence < 0.85 (rule 7 default fires)
- Policy lapsed, not found, or coverage ambiguous
- No available adjuster found
- CRM or policy system unavailable

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Claude API key |
| `MOCK_MODE` | `true` | Use mock clients (no real HTTP) |
| `CRM_BASE_URL` | `https://crm.example.com/api/v1` | CRM endpoint |
| `CRM_CLIENT_ID` / `CRM_CLIENT_SECRET` | — | OAuth2 credentials |
| `DMS_BASE_URL` | `https://dms.example.com/api/v1` | DMS endpoint |
| `DMS_API_KEY` | — | DMS API key |
| `SOAP_WSDL_URL` | `https://policy-admin.example.com/ws?wsdl` | Policy WSDL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis fallback queue |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## Models used

| Role | Model |
|------|-------|
| Orchestrator (tool_use loop) | `claude-sonnet-4-6` |
| Claim data extraction | `claude-haiku-4-5-20251001` |
