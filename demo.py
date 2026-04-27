"""Demo: runs three claims through FNOLOrchestrator with mock external systems.

Requires a real ANTHROPIC_API_KEY (set in .env or environment).
All CRM, SOAP, and DMS calls use mock clients — no external network traffic.

Usage:
    python demo.py
"""
import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s  %(message)s",
)
logger = logging.getLogger("demo")

CLAIMS = [
    {
        "label": "LOW severity — automated happy path",
        "source": "email",
        "raw_content": (
            "Hi, I'm Jane Smith (jane.smith@email.com). I need to file a claim under "
            "policy POL-2024-5678. On 24 April 2026 a tree branch fell and dented my car "
            "bonnet while it was parked outside my house. Estimated repair cost is £800. "
            "No other parties involved. Please acknowledge receipt. Thanks."
        ),
    },
    {
        "label": "HIGH severity — bodily injury, expect escalation",
        "source": "phone_transcript",
        "raw_content": (
            "Caller: Robert Chen, policy number POL-2024-9999. "
            "Date of incident: 25 April 2026. I was in a road traffic accident on the M25. "
            "The other driver ran a red light and collided with my vehicle. I sustained "
            "whiplash injuries and was taken to hospital by ambulance. The other driver was "
            "at fault. Estimated vehicle damage is £12,000 plus medical costs. "
            "Contact: r.chen@email.com."
        ),
    },
    {
        "label": "MEDIUM severity — web form submission",
        "source": "web_form",
        "raw_content": (
            "Claimant Name: Sarah O'Brien\n"
            "Policy Number: POL-2024-1111\n"
            "Date of Loss: 2026-04-22\n"
            "Description: Burst pipe in the kitchen caused significant water damage to "
            "flooring, cabinets and appliances. Estimated loss: £18,000. No third party involved.\n"
            "Email: sarah.obrien@email.com\n"
            "Phone: 07700 900000"
        ),
    },
]


def run_demo() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "sk-ant-placeholder":
        logger.error(
            "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key."
        )
        return

    # Ensure mock mode is active so no real CRM/SOAP/DMS calls are made
    os.environ["MOCK_MODE"] = "true"

    # Re-import config after env is set
    from fnol_agent import config as cfg
    cfg.config.MOCK_MODE = True

    from fnol_agent.orchestrator import run_claim
    from fnol_agent.integrations.mock_clients import MockCRMClient, MockPolicyClient, MockDMSClient
    import fnol_agent.tools as tools

    tools.configure_clients(
        crm=MockCRMClient(),
        policy=MockPolicyClient(),
        dms=MockDMSClient(),
    )

    for i, claim in enumerate(CLAIMS, 1):
        print(f"\n{'='*70}")
        print(f"CLAIM {i}: {claim['label']}")
        print(f"{'='*70}")
        print(f"Source : {claim['source']}")
        print(f"Content: {claim['raw_content'][:120]}...")
        print()

        try:
            outcome = run_claim(raw_content=claim["raw_content"], source=claim["source"])
            print(f"Status : {outcome.get('status', 'unknown').upper()}")
            print(f"Summary: {outcome.get('summary', '(no summary)')}")
        except Exception as exc:
            logger.exception("Claim %d failed: %s", i, exc)


if __name__ == "__main__":
    run_demo()
