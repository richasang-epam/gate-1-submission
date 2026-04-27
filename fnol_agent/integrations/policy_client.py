"""SOAP policy admin system client.

WSDL location and auth scheme are unknowns pending client discovery (D5.U1, D5.A4).
WS-Security assumed until confirmed. This module wraps zeep once the WSDL is available;
until then, a NotImplementedError is raised in production mode.
"""
import time
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

RETRY_DELAYS = [2, 4, 8]
TIMEOUT = 10.0
# Circuit breaker: open if >50% of calls fail within a 5-minute window
CB_THRESHOLD = 0.5
CB_WINDOW_SECONDS = 300


class PolicySystemError(Exception):
    pass


class PolicySystemUnavailable(PolicySystemError):
    """Raised after retries exhausted — caller should escalate the claim."""
    pass


class CircuitBreaker:
    def __init__(self, threshold: float = CB_THRESHOLD, window: int = CB_WINDOW_SECONDS):
        self.threshold = threshold
        self.window = window
        self._calls: deque = deque()
        self._open = False
        self._opened_at: Optional[datetime] = None

    def record_success(self) -> None:
        self._calls.append((datetime.utcnow(), True))
        self._prune()

    def record_failure(self) -> None:
        self._calls.append((datetime.utcnow(), False))
        self._prune()
        if len(self._calls) >= 2:
            failure_rate = sum(1 for _, ok in self._calls if not ok) / len(self._calls)
            if failure_rate > self.threshold:
                self._open = True
                self._opened_at = datetime.utcnow()
                logger.error("Policy circuit breaker OPEN (failure rate %.0f%%)", failure_rate * 100)

    def is_open(self) -> bool:
        return self._open

    def reset(self) -> None:
        self._open = False
        self._calls.clear()

    def _prune(self) -> None:
        cutoff = datetime.utcnow() - timedelta(seconds=self.window)
        while self._calls and self._calls[0][0] < cutoff:
            self._calls.popleft()


_circuit_breaker = CircuitBreaker()


class PolicyClient:
    """SOAP client for GetPolicyDetails and ValidateCoverage operations."""

    def __init__(self, wsdl_url: str):
        self.wsdl_url = wsdl_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from zeep import Client
                from zeep.transports import Transport
                transport = Transport(operation_timeout=TIMEOUT)
                self._client = Client(self.wsdl_url, transport=transport)
            except Exception as exc:
                raise PolicySystemError(f"Failed to load WSDL from {self.wsdl_url}: {exc}")
        return self._client

    def _call(self, operation: str, **kwargs) -> dict:
        if _circuit_breaker.is_open():
            raise PolicySystemUnavailable("Circuit breaker open — policy system unavailable")

        last_error: Optional[Exception] = None
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                client = self._get_client()
                result = getattr(client.service, operation)(**kwargs)
                _circuit_breaker.record_success()
                # zeep returns a zeep object; convert to dict
                return dict(result)
            except Exception as exc:
                last_error = exc
                _circuit_breaker.record_failure()
                logger.warning("SOAP call %s failed attempt %d: %s", operation, attempt + 1, exc)

        raise PolicySystemUnavailable(
            f"Policy system unavailable after retries: {last_error}"
        )

    def get_policy_details(self, policy_number: str) -> dict:
        """Maps to GetPolicyDetails SOAP operation."""
        raw = self._call("GetPolicyDetails", policyNumber=policy_number)
        return {
            "policy_number": policy_number,
            "policy_status": raw.get("status", "not_found"),
            "coverage_types": raw.get("coverageTypes", []),
            "coverage_limit": float(raw.get("coverageLimit", 0)),
            "deductible": float(raw.get("deductible", 0)),
        }

    def validate_coverage(
        self, policy_number: str, loss_type: str, claim_amount: Optional[float]
    ) -> dict:
        """Maps to ValidateCoverage SOAP operation."""
        raw = self._call(
            "ValidateCoverage",
            policyNumber=policy_number,
            lossType=loss_type,
            claimAmount=claim_amount or 0,
        )
        is_covered = raw.get("isCovered")
        return {
            "loss_type_covered": bool(is_covered) if is_covered is not None else None,
            "coverage_notes": raw.get("exclusionNotes"),
        }
