"""
LLM extraction layer.

Design choice: cheap/fast model for section classification (if you add
that later), stronger model only for the actual metric + sentiment
extraction — this keeps cost down once you're processing real volume.

Uses Groq's free API by default for LLM extraction.
"""

import json
import os

from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

EXTRACTION_MODEL = "openai/gpt-oss-20b"

EXTRACTION_PROMPT = """You are a financial analyst extracting structured data from a company filing.

Extract at most 12 of the most important metrics — prioritize revenue, net income, margins, EPS, and guidance over minor balance sheet line items.

Read the text below and extract:
1. Key financial metrics you can find (revenue, net income, gross margin, operating margin, EPS, guidance if mentioned) with their values and the period they refer to.
2. Overall management sentiment/tone (positive, neutral, cautious, negative) based on language used, with 1-2 sentences of justification.
3. Any notable risk factors or concerns explicitly mentioned.

Respond with ONLY valid JSON, no preamble, no markdown fences, matching this exact shape:
{{
  "metrics": [
    {{"name": "string", "value": "string", "period": "string"}}
  ],
  "sentiment": {{
    "label": "positive | neutral | cautious | negative",
    "justification": "string"
  }},
  "risk_factors": ["string"]
}}

If a field cannot be found in the text, omit it rather than guessing.

TEXT:
{text}
"""


def _call_llm(prompt: str) -> str:
    response = client.chat.completions.create(
        model=EXTRACTION_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def _parse_json_response(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]

    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError:
        repaired = cleaned.strip()
        if not repaired.endswith("}") and not repaired.endswith("]"):
            for suffix in ("}", "]", "}}", "]}"):
                try:
                    return json.loads(repaired + suffix)
                except json.JSONDecodeError:
                    pass

        if not repaired.endswith("}") and not repaired.endswith("]"):
            return {
                "error": "failed_to_parse",
                "likely_cause": "response_truncated",
                "raw_response": raw,
            }

        return {"error": "failed_to_parse", "raw_response": raw}


def extract_key_metrics(sections: dict[str, str]) -> dict:
    """
    Run extraction across the parsed sections. For v1, this
    concatenates the most relevant sections and does a single call.
    Once you're handling full 10-Ks, split this into per-section
    calls run in parallel (see README "scaling" notes).
    """
    priority_sections = [
        "net_sales",
        "total_net_sales",
        "results_of_operations",
        "liquidity_and_capital_resources",
        "item_1a",  # risk factors
        "full_document",
    ]

    text_to_analyze = ""
    for key in priority_sections:
        if key in sections:
            text_to_analyze += sections[key][:8000] + "\n\n"  # crude length cap for v1

    if not text_to_analyze:
        # fall back to whatever sections exist
        text_to_analyze = "\n\n".join(list(sections.values()))[:8000]

    prompt = EXTRACTION_PROMPT.format(text=text_to_analyze)
    raw = _call_llm(prompt)
    return _parse_json_response(raw)
