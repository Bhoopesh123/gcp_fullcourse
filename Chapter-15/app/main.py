import base64
import json
import logging
import os
from typing import Any

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def _ingest_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/api/v2/logs/ingest"):
        return url
    return f"{url}/api/v2/logs/ingest"


METRIC_NAMES = {
    "multi_turn_trajectory_quality_v1": "multi_turn_trajectory",
    "multi_turn_task_success_v1": "task_success",
    "multi_turn_tool_use_quality_v1": "tool_use_quality",
    "tool_use_quality_v1": "tool_use_quality",
    "safety_v1": "safety",
    "hallucination_v1": "hallucination",
}


def _dynatrace_record(entry: dict[str, Any], message_id: str) -> dict[str, Any] | None:
    """Return a compact metric record, or None for non-metric log entries."""
    labels = entry.get("labels", {})
    source_name = labels.get("gen_ai.evaluation.name")
    metric_name = METRIC_NAMES.get(source_name)
    if metric_name is None:
        return None

    payload = entry.get("jsonPayload", {})
    score = payload.get("candidateResult", {}).get("score")
    if score is None:
        score = labels.get("gen_ai.evaluation.score.value")
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        return None

    resource_labels = entry.get("resource", {}).get("labels", {})
    record: dict[str, Any] = {
        "content": f"{source_name}={numeric_score:g}",
        "event.kind": "metric",
        "evaluation.metric": source_name,
        "evaluation.metric_key": metric_name,
        "evaluation.score": numeric_score,
        "evaluation.result_id": entry.get("insertId", message_id),
        "evaluation.source_name": source_name,
        "evaluation.conversation_id": labels.get("gen_ai.conversation.id", "unknown"),
        "evaluation.online_evaluator_id": resource_labels.get("online_evaluator_id", "unknown"),
        "evaluation.agent_resource": labels.get("agent_resource", "unknown"),
        "gcp.project.id": resource_labels.get("resource_container", "unknown"),
        "gcp.region": resource_labels.get("location", "unknown"),
        "gcp.pubsub.message_id": message_id,
        "cloud.provider": "gcp",
    }
    if entry.get("timestamp"):
        record["timestamp"] = entry["timestamp"]
    return record


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.post("/")
def receive_pubsub():
    envelope = request.get_json(silent=True)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("message"), dict):
        return jsonify(error="invalid Pub/Sub envelope"), 400

    message = envelope["message"]
    encoded = message.get("data")
    if not encoded:
        return jsonify(error="Pub/Sub message has no data"), 400

    try:
        entry = json.loads(base64.b64decode(encoded, validate=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("Discarding malformed message id=%s: %s", message.get("messageId"), exc)
        # A malformed message will never become valid, so acknowledge it.
        return jsonify(status="discarded", reason="malformed log entry"), 204

    message_id = str(message.get("messageId", "unknown"))
    record = _dynatrace_record(entry, message_id)
    if record is None:
        logger.info("Skipped non-metric Pub/Sub message id=%s", message_id)
        return "", 204

    token = os.environ["DT_PLATFORM_TOKEN"]
    url = _ingest_url(os.environ["DT_URL"])

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=[record],
            timeout=(5, 25),
        )
    except requests.RequestException:
        logger.exception("Dynatrace request failed for Pub/Sub message id=%s", message_id)
        return jsonify(error="Dynatrace request failed"), 503

    if not 200 <= response.status_code < 300:
        logger.error(
            "Dynatrace rejected message id=%s status=%s body=%s",
            message_id,
            response.status_code,
            response.text[:500],
        )
        # Retry authentication and rate-limit failures too; this retains the message
        # while configuration is corrected.
        return jsonify(error="Dynatrace rejected the log", status=response.status_code), 503

    logger.info("Forwarded Pub/Sub message id=%s to Dynatrace", message_id)
    return "", 204


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
