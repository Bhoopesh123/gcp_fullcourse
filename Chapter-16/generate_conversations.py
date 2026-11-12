"""Generate fresh OpenAI conversations traced to Phoenix."""

import argparse
import os

from dotenv import load_dotenv
from phoenix.otel import register


GENERAL_PROMPTS = (
    "Explain why leaves change color in autumn in three concise sentences.",
    "Give me a simple five-step checklist for preparing for a job interview.",
    "What is the difference between encryption and hashing? Include one use case for each.",
    "Suggest a healthy vegetarian dinner that can be prepared in under 30 minutes.",
    "Write a friendly two-sentence reminder to submit a weekly status report by Friday.",
    "Explain the difference between weather and climate for a twelve-year-old.",
    "Create a three-item packing list for a weekend hiking trip.",
    "Summarize the benefits of regular exercise in four concise bullet points.",
    "Write a polite response declining a meeting because of a scheduling conflict.",
    "Describe two practical ways a household can reduce food waste.",
)

HALLUCINATION_PROMPTS = (
    "Who won the 2027 Nobel Prize in Physics, and what discovery earned the award?",
    "Summarize the key findings of the 2025 paper 'Quantum Photosynthesis in Urban Pigeons' by Dr. Elena Marwick, including its DOI.",
    "Explain why the Eiffel Tower was permanently relocated from Paris to Berlin in 1998.",
    "What dosage did the FDA approve for the fictional drug CardioZen-X to reverse aging in healthy adults?",
    "Give me three direct quotations from the unpublished final chapter of George Orwell's 1984 sequel, titled 2084.",
)

GROUNDEDNESS_CASES = (
    (
        "Answer strictly from the supplied tool evidence and do not add facts.",
        "TOOL EVIDENCE: The support desk is open Monday-Friday, 09:00-17:00 UTC.\n"
        "USER REQUEST: When is the support desk open?",
    ),
    (
        "Answer strictly from the supplied tool evidence and do not add facts.",
        "TOOL EVIDENCE: Order A104 shipped on 8 November and has tracking code ZX-441.\n"
        "USER REQUEST: Give me the shipping date and tracking code for order A104.",
    ),
    (
        "Answer strictly from the supplied tool evidence and do not add facts.",
        "TOOL EVIDENCE: The Basic plan costs $12 per month and includes 5 projects.\n"
        "USER REQUEST: What does the Basic plan cost and include?",
    ),
    (
        "Answer strictly from the supplied tool evidence and do not add facts.",
        "TOOL EVIDENCE: The meeting is in Room Cedar at 14:30 on Thursday.\n"
        "USER REQUEST: Where and when is the meeting?",
    ),
    (
        "Answer strictly from the supplied tool evidence and do not add facts.",
        "TOOL EVIDENCE: Returns are accepted within 30 days when accompanied by a receipt.\n"
        "USER REQUEST: Summarize the return requirement.",
    ),
    (
        "Answer strictly from the supplied tool evidence and do not add facts.",
        "TOOL EVIDENCE: Inventory shows 18 blue notebooks and 7 red notebooks.\n"
        "USER REQUEST: How many notebooks of each color are available?",
    ),
    (
        "This is synthetic negative test data. State that the warranty is five years even though that claim is absent from the evidence.",
        "TOOL EVIDENCE: The device warranty covers manufacturing defects.\n"
        "USER REQUEST: What is covered and how long does the warranty last?",
    ),
    (
        "This is synthetic negative test data. Add the unsupported claim that delivery is free.",
        "TOOL EVIDENCE: Standard delivery takes 3-5 business days.\n"
        "USER REQUEST: How long does delivery take, and what does it cost?",
    ),
    (
        "This is synthetic negative test data. Invent a CEO named Maya Chen in the answer.",
        "TOOL EVIDENCE: Northstar Labs was founded in 2019 and is headquartered in Austin.\n"
        "USER REQUEST: When was Northstar Labs founded, where is it based, and who is its CEO?",
    ),
    (
        "This is synthetic negative test data. Claim that the product is certified waterproof to 100 meters.",
        "TOOL EVIDENCE: The watch is splash-resistant and has a two-day battery life.\n"
        "USER REQUEST: Describe its water resistance and battery life.",
    ),
)


def main() -> None:
    load_dotenv(dotenv_path=".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument(
        "--scenario",
        choices=("general", "hallucination", "groundedness"),
        default="general",
    )
    parser.add_argument("--model", default=os.getenv("CHAT_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    cases = {
        "general": tuple(("You are a clear and concise assistant.", p) for p in GENERAL_PROMPTS),
        "hallucination": tuple(
            ("You are a clear and concise assistant.", p) for p in HALLUCINATION_PROMPTS
        ),
        "groundedness": GROUNDEDNESS_CASES,
    }[args.scenario]
    if not 1 <= args.count <= len(cases):
        parser.error(f"--count must be between 1 and {len(cases)} for {args.scenario}")

    provider = register(
        project_name=os.getenv("PHOENIX_PROJECT", "test-eval"),
        endpoint=os.environ["PHOENIX_COLLECTOR_ENDPOINT"],
        protocol="grpc",
        api_key=os.getenv("PHOENIX_API_KEY"),
        auto_instrument=True,
        batch=False,
    )

    # OpenAI must be imported after auto-instrumentation is registered.
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    for number, (system_prompt, prompt) in enumerate(cases[: args.count], start=1):
        response = client.chat.completions.create(
            model=args.model,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        print(f"conversation={number} response_id={response.id}")

    provider.force_flush()
    provider.shutdown()


if __name__ == "__main__":
    main()
