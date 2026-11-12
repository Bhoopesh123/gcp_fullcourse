"""Export Phoenix span evaluations as structured Dynatrace log records."""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Iterable

import httpx
from dotenv import load_dotenv
from phoenix.client import Client


EVALUATION_NAMES = (
    "correctness",
    "hallucination",
    "relevance",
    "response_clarity",
    "response_relevance",
    "response_safety",
    "task_completion",
    "tool_groundedness",
    "tool_use_correctness",
    "trajectory_efficiency",
)


def dynatrace_endpoint(environment_url: str) -> str:
    base = environment_url.rstrip("/")
    if base.endswith("/api/v2/logs/ingest"):
        return base
    return f"{base}/api/v2/logs/ingest"


def grafana_loki_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/loki/api/v1/push"):
        return base
    return f"{base}/loki/api/v1/push"


def record_from_span(
    span: dict,
    evaluations: dict[str, dict],
    project: str,
    judge_model: str | None = None,
) -> dict:
    context = span.get("context") or {}
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content": "Phoenix LLM evaluation completed",
        "log.source": "arize.phoenix.evaluations",
        "service.name": "streamlit-openai-chatbot",
        "phoenix.project": project,
        "phoenix.span.start_time": span.get("start_time"),
        "phoenix.span.end_time": span.get("end_time"),
        "trace.id": context.get("trace_id"),
        "span.id": context.get("span_id"),
        "span.name": span.get("name"),
        "evaluation.judge_model": judge_model or os.getenv("JUDGE_MODEL", "gpt-4o-mini"),
    }
    for name in EVALUATION_NAMES:
        result = evaluations[name]
        record[f"evaluation.{name}.label"] = result.get("label")
        record[f"evaluation.{name}.score"] = result.get("score")
        record[f"evaluation.{name}.explanation"] = result.get("explanation")
        # Loki queries work most reliably with identifier-safe JSON field names.
        # Preserve the dotted fields above for Dynatrace compatibility.
        record[f"evaluation_{name}_label"] = result.get("label")
    return record


def build_records(phoenix: Client, project: str, limit: int = 100) -> list[dict]:
    spans = phoenix.spans.get_spans(
        project_identifier=project,
        span_kind="LLM",
        sort="start_time",
        order="desc",
        limit=limit,
        timeout=30,
    )
    annotations = phoenix.spans.get_span_annotations(
        spans=spans,
        project_identifier=project,
        include_annotation_names=list(EVALUATION_NAMES),
        limit=max(100, len(spans) * len(EVALUATION_NAMES)),
        timeout=30,
    )
    by_span: dict[str, dict[str, dict]] = {}
    for annotation in annotations:
        data = annotation if isinstance(annotation, dict) else annotation.model_dump(mode="json")
        by_span.setdefault(data["span_id"], {})[data["name"]] = data["result"]

    records = []
    for span in spans:
        context = span.get("context") or {}
        span_id = context.get("span_id")
        evaluations = by_span.get(span_id, {})
        if not all(name in evaluations for name in EVALUATION_NAMES):
            continue
        records.append(record_from_span(span, evaluations, project))
    return records


def send_records(
    records: Iterable[dict],
    environment_url: str,
    token: str,
    attempts: int = 4,
) -> int:
    payload = list(records)
    if not payload:
        return 0
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.post(
                dynatrace_endpoint(environment_url),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                content=json.dumps(payload),
                timeout=30,
            )
            response.raise_for_status()
            return len(payload)
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == attempts:
                raise
            logging.warning(
                "Dynatrace delivery failed; retrying in %ds (%d/%d)",
                attempt,
                attempt,
                attempts,
            )
            time.sleep(attempt)
    return 0


def send_records_to_grafana(
    records: Iterable[dict],
    loki_url: str,
    user: str,
    token: str,
    attempts: int = 4,
) -> int:
    payload_records = list(records)
    if not payload_records:
        return 0
    timestamp = time.time_ns()
    payload = {
        "streams": [
            {
                "stream": {
                    "job": "phoenix-evaluations",
                    "service_name": "streamlit-openai-chatbot",
                    "phoenix_project": str(
                        payload_records[0].get("phoenix.project", "unknown")
                    ),
                },
                "values": [
                    [str(timestamp + index), json.dumps(record, separators=(",", ":"))]
                    for index, record in enumerate(payload_records)
                ],
            }
        ]
    }
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.post(
                grafana_loki_endpoint(loki_url),
                auth=(user, token),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return len(payload_records)
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == attempts:
                raise
            logging.warning(
                "Grafana Loki delivery failed; retrying in %ds (%d/%d)",
                attempt,
                attempt,
                attempts,
            )
            time.sleep(attempt)
    return 0


def main() -> None:
    load_dotenv(dotenv_path=".env")
    phoenix = Client(
        base_url="http://136.80.194.201:6006/",
        api_key=os.getenv("PHOENIX_API_KEY"),
    )
    records = build_records(phoenix, project="test-eval", limit=100)
    count = send_records(
        records,
        environment_url=os.environ["DT_ENV_URL"],
        token=os.environ["DT_PLATFORM_TOKEN"],
    )
    print(f"sent={count}")


if __name__ == "__main__":
    main()
