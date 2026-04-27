import time
import logging
from datetime import datetime, timedelta
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

RETRY_DELAYS = [1, 2, 4]
TIMEOUT = 5.0


class CRMError(Exception):
    pass


class CRMClient:
    """REST/JSON CRM client. Auth: OAuth 2.0 client credentials (D5.A3)."""

    def __init__(self, base_url: str, client_id: str, client_secret: str):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def _get_token(self) -> str:
        if (
            self._access_token
            and self._token_expires_at
            and datetime.utcnow() < self._token_expires_at - timedelta(seconds=60)
        ):
            return self._access_token

        resp = httpx.post(
            f"{self.base_url}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        return self._access_token

    def _request(self, method: str, path: str, **kwargs) -> dict:
        last_error: Optional[Exception] = None
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                token = self._get_token()
                resp = httpx.request(
                    method,
                    f"{self.base_url}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=TIMEOUT,
                    **kwargs,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_error = exc
                logger.warning("CRM request failed attempt %d: %s", attempt + 1, exc)
        raise CRMError(f"CRM unavailable after retries: {last_error}")

    def create_claim(
        self,
        source: str,
        raw_content: str,
        received_at: str,
        reference_number: str,
    ) -> dict:
        return self._request(
            "POST",
            "/claims",
            json={
                "source": source,
                "raw_content": raw_content,
                "received_at": received_at,
                "reference_number": reference_number,
            },
        )

    def update_claim(self, claim_id: str, state: str, metadata: dict) -> dict:
        return self._request(
            "PATCH",
            f"/claims/{claim_id}",
            json={"state": state, "metadata": metadata},
        )

    def get_adjusters(self, specialisation: str) -> list:
        return self._request("GET", f"/adjusters?specialisation={specialisation}&available=true")

    def assign_adjuster(self, claim_id: str, adjuster_id: str, routing_reason: str) -> dict:
        return self._request(
            "POST",
            f"/claims/{claim_id}/assignment",
            json={"adjuster_id": adjuster_id, "routing_reason": routing_reason},
        )

    def send_communication(
        self,
        claim_id: str,
        channel: str,
        template_id: str,
        recipient: dict,
        template_data: dict,
    ) -> dict:
        return self._request(
            "POST",
            "/communications",
            json={
                "claim_id": claim_id,
                "channel": channel,
                "template_id": template_id,
                "recipient": recipient,
                "template_data": template_data,
            },
        )

    def create_review_task(
        self, claim_id: str, priority: str, reason: str, dossier: dict
    ) -> dict:
        return self._request(
            "POST",
            "/review-queue",
            json={
                "claim_id": claim_id,
                "priority": priority,
                "reason": reason,
                "dossier": dossier,
            },
        )

    def get_review_task(self, task_id: str) -> dict:
        return self._request("GET", f"/review-queue/{task_id}")
