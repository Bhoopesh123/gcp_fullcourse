"""Register the online-monitor quality pillars in Phoenix's Evaluators UI."""

import os

import httpx
from dotenv import load_dotenv
from phoenix.client import Client

from phoenix_online_monitor import METRICS, SYSTEM_PROMPT


PHOENIX_URL = os.getenv("PHOENIX_API_URL", "http://136.80.194.201:6006")
DATASET_NAME = "online-evaluation-pillars"

LIST_EVALUATORS = """
query ListEvaluators {
  evaluators(first: 100) {
    edges { node { id name } }
  }
}
"""

CREATE_EVALUATOR = """
mutation RegisterQualityPillar($input: CreateDatasetLLMEvaluatorInput!) {
  createDatasetLlmEvaluator(input: $input) {
    evaluator { id name evaluator { id name kind } }
  }
}
"""


def graphql(query: str, variables: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key := os.getenv("PHOENIX_API_KEY"):
        headers["Authorization"] = f"Bearer {api_key}"
    response = httpx.post(
        f"{PHOENIX_URL.rstrip('/')}/graphql",
        headers=headers,
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if errors := payload.get("errors"):
        raise RuntimeError(errors)
    return payload["data"]


def ensure_anchor_dataset(client: Client) -> str:
    try:
        dataset = client.datasets.get_dataset(dataset=DATASET_NAME, timeout=30)
    except (httpx.HTTPStatusError, ValueError) as error:
        if isinstance(error, httpx.HTTPStatusError) and error.response.status_code != 404:
            raise
        if isinstance(error, ValueError) and not str(error).startswith("Dataset not found:"):
            raise
        dataset = client.datasets.create_dataset(
            name=DATASET_NAME,
            inputs=[{"question": "Evaluator registration anchor"}],
            outputs=[{"response": "Evaluator registration anchor"}],
            dataset_description=(
                "Anchor dataset for reusable online-monitor evaluator definitions. "
                "Production results remain attached to spans and traces."
            ),
            timeout=30,
        )
    return dataset.id


def evaluator_input(dataset_id: str, name: str) -> dict:
    labels, positive_labels = METRICS[name]
    values = [
        {"label": label, "score": 1.0 if label in positive_labels else 0.0}
        for label in sorted(labels)
    ]
    description = f"Online quality pillar: {name.replace('_', ' ')}."
    return {
        "datasetId": dataset_id,
        "name": name,
        "description": description,
        "inputMapping": {
            "literalMapping": {},
            "pathMapping": {
                "input": "input.question",
                "output": "output.response",
            },
        },
        "outputConfigs": [
            {
                "categorical": {
                    "name": name,
                    "description": description,
                    "optimizationDirection": "MAXIMIZE",
                    "values": values,
                }
            }
        ],
        "promptVersion": {
            "modelProvider": "OPENAI",
            "modelName": os.getenv("JUDGE_MODEL", "gpt-4o-mini"),
            "templateFormat": "F_STRING",
            "template": {
                "messages": [
                    {
                        "role": "SYSTEM",
                        "content": [{"text": {"text": SYSTEM_PROMPT}}],
                    },
                    {
                        "role": "USER",
                        "content": [
                            {
                                "text": {
                                    "text": (
                                        "USER REQUEST:\n{input}\n\n"
                                        "ASSISTANT RESPONSE:\n{output}\n\n"
                                        f"Evaluate only {name.replace('_', ' ')}."
                                    )
                                }
                            }
                        ],
                    },
                ]
            },
            "invocationParameters": {"openai": {"temperature": 0}},
            "tools": {
                "tools": [
                    {
                        "function": {
                            "name": name,
                            "description": description,
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "label": {
                                        "type": "string",
                                        "enum": sorted(labels),
                                        "description": name,
                                    },
                                    "explanation": {
                                        "type": "string",
                                        "description": (
                                            f'Explanation for choosing the label "{name}"'
                                        ),
                                    },
                                },
                                "required": ["label", "explanation"],
                            },
                        }
                    }
                ],
                "toolChoice": {"oneOrMore": True},
            },
        },
    }


def main() -> None:
    load_dotenv(dotenv_path=".env")
    client = Client(base_url=PHOENIX_URL, api_key=os.getenv("PHOENIX_API_KEY"))
    dataset_id = ensure_anchor_dataset(client)
    existing = {
        edge["node"]["name"]
        for edge in graphql(LIST_EVALUATORS)["evaluators"]["edges"]
    }
    created = []
    skipped = []
    for name in METRICS:
        if name in existing:
            skipped.append(name)
            continue
        graphql(CREATE_EVALUATOR, {"input": evaluator_input(dataset_id, name)})
        created.append(name)
    print(f"dataset={DATASET_NAME} created={created} existing={skipped}")


if __name__ == "__main__":
    main()
