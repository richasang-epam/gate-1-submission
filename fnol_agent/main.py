"""Queue consumer entry point.

Reads FNOL claims from a message queue (SQS or equivalent — D5.A6) and spawns
one synchronous orchestrator loop per claim. Queue infrastructure must be
provisioned as part of deployment (the client has no AI infrastructure today).
"""
import json
import logging
import sys

from fnol_agent.config import config
from fnol_agent.orchestrator import run_claim

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def process_message(message: dict) -> dict:
    """Process a single queue message. Returns outcome dict."""
    raw_content = message.get("raw_content", "")
    source = message.get("source", "email")
    logger.info("Processing claim from source=%s length=%d", source, len(raw_content))
    return run_claim(raw_content=raw_content, source=source)


def run_sqs_consumer(queue_url: str) -> None:
    """Long-poll SQS queue and process messages one at a time."""
    import boto3
    sqs = boto3.client("sqs")
    logger.info("Starting SQS consumer on %s", queue_url)

    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
        )
        messages = resp.get("Messages", [])
        if not messages:
            continue

        for msg in messages:
            body = json.loads(msg["Body"])
            try:
                outcome = process_message(body)
                logger.info("Claim complete: %s", outcome.get("status"))
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
            except Exception:
                logger.exception("Claim processing failed — message left in queue for retry")


def run_stdin_consumer() -> None:
    """Read one JSON claim from stdin — useful for local testing."""
    raw = sys.stdin.read()
    message = json.loads(raw)
    outcome = process_message(message)
    print(json.dumps(outcome, indent=2))


if __name__ == "__main__":
    import os
    queue_url = os.environ.get("SQS_QUEUE_URL")
    if queue_url:
        run_sqs_consumer(queue_url)
    else:
        logger.info("No SQS_QUEUE_URL set — reading from stdin")
        run_stdin_consumer()
