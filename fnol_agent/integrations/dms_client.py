"""Document Management System client.

REST/JSON assumed (D5.A5). Auth: API key (SCOPE-OUT — confirm with client).
Retention policy is a compliance unknown (D5.U4).
"""
import logging
import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 10.0


class DMSError(Exception):
    pass


class DMSClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    def upload_claim(self, claim_id: str, raw_content: str, extracted: dict, audit_log: list) -> dict:
        payload = {
            "claim_id": claim_id,
            "document_type": "fnol_claim",
            "content_type": "application/json",
            "payload": {
                "raw_content": raw_content,
                "extracted": extracted,
                "audit_log": audit_log,
            },
            "tags": ["fnol", f"claim_id:{claim_id}"],
        }
        try:
            resp = httpx.post(
                f"{self.base_url}/documents",
                json=payload,
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise DMSError(f"DMS upload failed: {exc}")

    def get_document(self, doc_id: str) -> dict:
        try:
            resp = httpx.get(
                f"{self.base_url}/documents/{doc_id}",
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise DMSError(f"DMS retrieval failed: {exc}")
