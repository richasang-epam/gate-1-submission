"""FNOL Claims Processing Dashboard — run with: streamlit run dashboard.py"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

st.set_page_config(
    page_title="FNOL Claims Dashboard",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Bootstrap mock clients once per session ───────────────────────────────────
if "clients_ready" not in st.session_state:
    os.environ.setdefault("MOCK_MODE", "true")
    from fnol_agent.integrations.mock_clients import MockCRMClient, MockPolicyClient, MockDMSClient
    import fnol_agent.tools as tools
    tools.configure_clients(
        crm=MockCRMClient(),
        policy=MockPolicyClient(),
        dms=MockDMSClient(),
    )
    st.session_state["clients_ready"] = True

from fnol_agent.orchestrator import run_claim

HISTORY_FILE = Path("claim_history.json")

SAMPLE_CLAIMS = {
    "LOW — minor property damage (email)": {
        "source": "email",
        "text": (
            "Hi, I am Jane Smith (jane.smith@email.com). I need to file a claim under "
            "policy POL-2024-5678. On 24 April 2026 a tree branch fell on my car while "
            "it was parked outside. Estimated repair cost is £800. No other parties involved."
        ),
    },
    "HIGH — bodily injury, third party (phone transcript)": {
        "source": "phone_transcript",
        "text": (
            "Caller: Robert Chen, policy POL-2024-9999. Date: 25 April 2026. Road traffic "
            "accident on the M25 — other driver ran red light, collided with my vehicle. "
            "I sustained whiplash and was taken to hospital by ambulance. Other driver at fault. "
            "Estimated vehicle damage £12,000 plus medical costs. Contact: r.chen@email.com."
        ),
    },
    "MEDIUM — burst pipe / water damage (web form)": {
        "source": "web_form",
        "text": (
            "Claimant Name: Sarah O'Brien\nPolicy Number: POL-2024-1111\n"
            "Date of Loss: 2026-04-22\nDescription: Burst pipe in the kitchen caused water "
            "damage to flooring, cabinets and appliances. Estimated loss: £18,000. "
            "No third party.\nEmail: sarah.obrien@email.com\nPhone: 07700900000"
        ),
    },
    "Ambiguous coverage (lapsed policy)": {
        "source": "email",
        "text": (
            "Policy: LAPSED-2024-0001. Claimant: Tom Harris, tom@email.com. "
            "Date: 20 April 2026. Theft of vehicle from driveway overnight. "
            "Estimated loss: £9,500. No third party involved."
        ),
    },
}


# ── Persistence helpers ───────────────────────────────────────────────────────

def _load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            return []
    return []


def _append_history(record: dict) -> None:
    history = _load_history()
    history.insert(0, record)
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str))


# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("## FNOL Claims Processing Dashboard")
st.caption(
    "FNOLOrchestrator · claude-sonnet-4-6 extraction · claude-haiku-4-5-20251001 · "
    "Mock CRM / SOAP / DMS"
)

# API key check
api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key or api_key == "sk-ant-placeholder":
    st.error("ANTHROPIC_API_KEY not found. Add it to your .env file and restart.")
    st.stop()

st.success("API key loaded. Agent ready.", icon=None)
st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_submit, tab_history, tab_metrics = st.tabs(
    ["Submit Claim", "Claim History", "Metrics"]
)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SUBMIT CLAIM
# ═══════════════════════════════════════════════════════════════════════════════
with tab_submit:
    st.subheader("Submit a new FNOL claim")

    col_form, col_sample = st.columns([3, 2], gap="large")

    with col_sample:
        st.markdown("**Load a sample claim**")
        selected_sample = st.selectbox(
            "Choose sample", ["(none)"] + list(SAMPLE_CLAIMS.keys()), label_visibility="collapsed"
        )
        if selected_sample != "(none)":
            st.info(SAMPLE_CLAIMS[selected_sample]["text"][:300] + "...")

    with col_form:
        with st.form("claim_form", clear_on_submit=False):
            source_options = ["email", "phone_transcript", "web_form"]

            # Pre-fill from sample
            default_source = "email"
            default_text = ""
            if selected_sample != "(none)":
                default_source = SAMPLE_CLAIMS[selected_sample]["source"]
                default_text = SAMPLE_CLAIMS[selected_sample]["text"]

            source = st.selectbox(
                "Source channel",
                source_options,
                index=source_options.index(default_source),
            )
            raw_text = st.text_area(
                "Claim text",
                value=default_text,
                height=220,
                placeholder="Paste or type the raw claim content here...",
            )
            submitted = st.form_submit_button("Process Claim", type="primary", use_container_width=True)

        if submitted:
            if not raw_text.strip():
                st.warning("Please enter claim text before submitting.")
            else:
                started_at = datetime.now(timezone.utc)
                with st.spinner("FNOLOrchestrator is processing the claim..."):
                    try:
                        t0 = time.time()
                        outcome = run_claim(raw_content=raw_text, source=source)
                        elapsed = round(time.time() - t0, 1)
                        status = outcome.get("status", "unknown")
                        summary = outcome.get("summary", "")

                        record = {
                            "submitted_at": started_at.isoformat(),
                            "source": source,
                            "snippet": raw_text[:100].replace("\n", " "),
                            "status": status,
                            "processing_time_s": elapsed,
                            "summary": summary,
                        }
                        _append_history(record)

                        if status == "complete":
                            st.success(f"Claim processed in {elapsed}s")
                        else:
                            st.error(f"Claim ended with status: {status}")

                        st.markdown("**Agent summary**")
                        st.info(summary or "(no summary returned)")

                        with st.expander("Full outcome JSON"):
                            st.json(outcome)

                    except Exception as exc:
                        st.error(f"Error: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CLAIM HISTORY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_history:
    st.subheader("Processed claims this session")

    col_refresh, col_clear = st.columns([1, 1])
    with col_refresh:
        if st.button("Refresh", use_container_width=True):
            st.rerun()
    with col_clear:
        if st.button("Clear history", use_container_width=True):
            if HISTORY_FILE.exists():
                HISTORY_FILE.unlink()
            st.rerun()

    history = _load_history()

    if not history:
        st.info("No claims processed yet. Submit one in the 'Submit Claim' tab.")
    else:
        import pandas as pd
        df = pd.DataFrame(history)
        display_cols = ["submitted_at", "source", "snippet", "status", "processing_time_s"]
        df_display = df[display_cols].rename(columns={
            "submitted_at": "Submitted",
            "source": "Source",
            "snippet": "Claim (excerpt)",
            "status": "Status",
            "processing_time_s": "Time (s)",
        })
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        st.markdown("**Claim summaries**")
        for i, rec in enumerate(history):
            with st.expander(f"{rec['submitted_at'][:19]}  |  {rec['source']}  |  {rec['status'].upper()}"):
                st.markdown(f"**Excerpt:** {rec['snippet']}")
                st.markdown(f"**Status:** `{rec['status']}`  |  **Time:** {rec['processing_time_s']}s")
                if rec.get("summary"):
                    st.markdown(f"**Summary:** {rec['summary']}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — METRICS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_metrics:
    st.subheader("Session metrics")
    history = _load_history()

    if not history:
        st.info("No claims processed yet.")
    else:
        import pandas as pd
        df = pd.DataFrame(history)

        total = len(df)
        complete = len(df[df["status"] == "complete"])
        errors = len(df[df["status"] == "error"])
        avg_time = round(df["processing_time_s"].mean(), 1) if "processing_time_s" in df else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total claims", total)
        col2.metric("Completed", complete)
        col3.metric("Errors / escalated", errors)
        col4.metric("Avg processing time", f"{avg_time}s")

        st.divider()

        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("**Claims by source channel**")
            source_counts = df["source"].value_counts().reset_index()
            source_counts.columns = ["Source", "Count"]
            st.bar_chart(source_counts.set_index("Source"))

        with col_right:
            st.markdown("**Outcome distribution**")
            status_counts = df["status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            st.bar_chart(status_counts.set_index("Status"))

        if "processing_time_s" in df and len(df) > 1:
            st.markdown("**Processing time per claim (seconds)**")
            time_df = df[["submitted_at", "processing_time_s"]].copy()
            time_df["submitted_at"] = time_df["submitted_at"].str[:19]
            st.line_chart(time_df.set_index("submitted_at"))

        st.divider()
        st.markdown("**Target vs observed (spec §D1)**")
        target_df = pd.DataFrame({
            "Metric": [
                "SLA breach rate",
                "Routing error rate",
                "Avg handling time (automated)",
                "Claims requiring no human intervention",
            ],
            "Baseline": ["31%", "18%", "22 min", "0%"],
            "Target": ["≤ 5%", "≤ 3%", "≤ 4 min", "≥ 65%"],
            "Agent (demo)": [
                "N/A — mock clients",
                "N/A — mock clients",
                f"{avg_time}s (mock)",
                "N/A — shadow mode needed",
            ],
        })
        st.dataframe(target_df, use_container_width=True, hide_index=True)
        st.caption(
            "Live metrics require shadow mode against real CRM data (spec §4.2). "
            "Figures above are demo-only."
        )
