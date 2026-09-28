"""
LLM extraction layer.

Design choice: cheap/fast model for section classification (if you add
that later), stronger model only for the actual metric + sentiment
extraction — this keeps cost down once you're processing real volume.

Uses Groq's free API by default for LLM extraction.
"""

import json
import os
import time

from groq import Groq

from app.parsing import chunk_text

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

EXTRACTION_MODEL = "openai/gpt-oss-120b"
CLASSIFICATION_MODEL = "openai/gpt-oss-20b"
EXTRACTION_INPUT_CHAR_LIMIT = 14000
EXTRACTION_MAX_OUTPUT_TOKENS = 3500

CLASSIFICATION_PROMPT = """Classify this financial filing text chunk. Return ONLY valid JSON in exactly this shape:
{{"contains_revenue_or_income_data": bool, "contains_balance_sheet_data": bool, "contains_cash_flow_data": bool, "contains_risk_factors": bool, "contains_management_discussion": bool}}
You MUST include all five boolean fields in your response, even if the value is false.

Use true only when the chunk contains the corresponding substantive content, not merely a table of contents reference.

TEXT:
{chunk}
"""

EXTRACTION_PROMPT = """You are a financial analyst extracting structured data from a company filing.

Extract every year of data available for each metric. Most 10-Ks show 2-3 years of comparison. Map company-specific terminology to these standardized field names, for example "net sales" or "total revenue" to "revenue", and "net income" or "net earnings" to "profit". If a metric has no data for a given year, omit that year's entry. If a metric has no data at all in the document, return an empty list []. Never guess or estimate a value that is not explicitly stated in the text.

Extract these 12 standardized financial metrics, plus management sentiment and risk factors:
- revenue
- gross_profit
- operating_income
- profit
- gross_margin
- operating_margin
- total_assets
- total_liabilities
- cash_and_equivalents
- operating_cash_flow
- free_cash_flow
- eps
- sentiment: label and a 1-2 sentence justification
- risk_factors: explicitly mentioned concerns

Respond with ONLY valid JSON, no preamble, no markdown fences, matching this exact shape:
{{
    "revenue": [{{"period": "string", "value": "string"}}],
    "gross_profit": [{{"period": "string", "value": "string"}}],
    "operating_income": [{{"period": "string", "value": "string"}}],
    "profit": [{{"period": "string", "value": "string"}}],
    "gross_margin": [{{"period": "string", "value": "string"}}],
    "operating_margin": [{{"period": "string", "value": "string"}}],
    "total_assets": [{{"period": "string", "value": "string"}}],
    "total_liabilities": [{{"period": "string", "value": "string"}}],
    "cash_and_equivalents": [{{"period": "string", "value": "string"}}],
    "operating_cash_flow": [{{"period": "string", "value": "string"}}],
    "free_cash_flow": [{{"period": "string", "value": "string"}}],
    "eps": [{{"period": "string", "value": "string"}}],
  "sentiment": {{
    "label": "positive | neutral | cautious | negative",
    "justification": "string"
  }},
  "risk_factors": ["string"]
}}

TEXT:
{text}
"""


def _call_llm(prompt: str) -> str:
    response = client.chat.completions.create(
        model=EXTRACTION_MODEL,
        max_tokens=EXTRACTION_MAX_OUTPUT_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def classify_chunk(chunk: str) -> dict[str, bool]:
    """Classify one document chunk using the fast Groq model."""
    started_at = time.perf_counter()
    response = client.chat.completions.create(
        model=CLASSIFICATION_MODEL,
        max_tokens=300,
        reasoning_effort="low",
        messages=[{"role": "user", "content": CLASSIFICATION_PROMPT.format(chunk=chunk)}],
    )
    print(f"Chunk classification call took {time.perf_counter() - started_at:.2f}s")
    content = response.choices[0].message.content
    if not content or not content.strip():
        print("Warning: empty classification response; skipping chunk")
        return {
            "contains_revenue_or_income_data": False,
            "contains_balance_sheet_data": False,
            "contains_cash_flow_data": False,
            "contains_risk_factors": False,
            "contains_management_discussion": False,
        }

    raw = content.strip()
    print(f"Raw classification response: {raw!r}")
    result = _parse_json_response(raw)
    return {
        "contains_revenue_or_income_data": bool(result.get("contains_revenue_or_income_data", False)),
        "contains_balance_sheet_data": bool(result.get("contains_balance_sheet_data", False)),
        "contains_cash_flow_data": bool(result.get("contains_cash_flow_data", False)),
        "contains_risk_factors": bool(result.get("contains_risk_factors", False)),
        "contains_management_discussion": bool(result.get("contains_management_discussion", False)),
    }


def classify_sections_with_llm(text: str) -> dict[str, str]:
    """Classify overlapping chunks and assemble content by semantic section."""
    started_at = time.perf_counter()
    chunks = chunk_text(text)
    sections = {
        "revenue_or_income_data": "",
        "balance_sheet_data": "",
        "cash_flow_data": "",
        "risk_factors": "",
        "management_discussion": "",
    }
    tag_names = {
        "contains_revenue_or_income_data": "revenue_or_income_data",
        "contains_balance_sheet_data": "balance_sheet_data",
        "contains_cash_flow_data": "cash_flow_data",
        "contains_risk_factors": "risk_factors",
        "contains_management_discussion": "management_discussion",
    }

    for index, chunk in enumerate(chunks):
        try:
            classifications = classify_chunk(chunk)
        except Exception as error:
            print(f"Warning: classification failed for chunk {index}: {error}")
            classifications = {}
        for classification_key, section_key in tag_names.items():
            if classifications.get(classification_key, False) and len(sections[section_key]) < 8000:
                remaining = 8000 - len(sections[section_key])
                sections[section_key] += chunk[:remaining]
        if index + 1 < len(chunks):
            time.sleep(0.3)

    elapsed = time.perf_counter() - started_at
    print(f"Classified {len(chunks)} chunks in {elapsed:.2f}s")
    return sections


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


def _metric_label(metric_name: str) -> str:
    labels = {
        "revenue": "Revenue",
        "gross_profit": "Gross Profit",
        "operating_income": "Operating Income",
        "profit": "Profit",
        "gross_margin": "Gross Margin",
        "operating_margin": "Operating Margin",
        "total_assets": "Total Assets",
        "total_liabilities": "Total Liabilities",
        "cash_and_equivalents": "Cash and Equivalents",
        "operating_cash_flow": "Operating Cash Flow",
        "free_cash_flow": "Free Cash Flow",
        "eps": "Earnings Per Share",
    }
    return labels.get(metric_name, metric_name.replace("_", " ").title())


def _metric_unit(metric_name: str) -> str:
    units = {
        "revenue": "reported currency",
        "gross_profit": "reported currency",
        "operating_income": "reported currency",
        "profit": "reported currency",
        "gross_margin": "percent",
        "operating_margin": "percent",
        "total_assets": "reported currency",
        "total_liabilities": "reported currency",
        "cash_and_equivalents": "reported currency",
        "operating_cash_flow": "reported currency",
        "free_cash_flow": "reported currency",
        "eps": "reported currency per share",
    }
    return units.get(metric_name, "reported value")


def format_extracted_metrics(payload: dict) -> dict:
    """Add human-readable labels and concise summary to the raw model output."""
    if not isinstance(payload, dict):
        return payload

    formatted = {}
    for metric_name, values in payload.items():
        if metric_name in {"sentiment", "risk_factors"}:
            formatted[metric_name] = values
            continue

        if not isinstance(values, list):
            formatted[metric_name] = values
            continue

        enriched = []
        for item in values:
            if not isinstance(item, dict):
                enriched.append(item)
                continue
            enriched.append({
                "metric": metric_name,
                "label": _metric_label(metric_name),
                "period": item.get("period"),
                "value": item.get("value"),
                "unit": _metric_unit(metric_name),
            })
        formatted[metric_name] = enriched

    summary_parts = []
    for metric_name in ["revenue", "gross_profit", "operating_income", "profit", "eps"]:
        values = formatted.get(metric_name, [])
        if not values:
            continue
        latest = values[0]
        period = latest.get("period")
        value = latest.get("value")
        label = latest.get("label", _metric_label(metric_name))
        summary_parts.append(f"{label} in {period} was {value}")

    formatted["summary"] = "; ".join(summary_parts) if summary_parts else "No summary metrics were extracted."
    return formatted


def extract_key_metrics(sections: dict[str, str]) -> dict:
    """
    Run extraction across the parsed sections. For v1, this
    concatenates the most relevant sections and does a single call.
    Once you're handling full 10-Ks, split this into per-section
    calls run in parallel (see README "scaling" notes).
    """
    priority_sections = [
        ("item_8", 12000),
        ("balance_sheets", 4000),
        ("income_statements", 4000),
        ("cash_flows", 4000),
        ("comprehensive_income", 1500),
        ("consolidated_balance_sheets", 4000),
        ("consolidated_statements_of_cash_flows", 4000),
        ("consolidated_statements_of_income", 4000),
        ("consolidated_statements_of_operations", 4000),
        ("condensed_consolidated_statements_of_operations", 4000),
        ("balance_sheet_data", 3000),
        ("cash_flow_data", 3000),
        ("net_sales", 2500),
        ("total_net_sales", 2500),
        ("results_of_operations", 2500),
        ("liquidity_and_capital_resources", 2000),
        ("revenue_or_income_data", 2500),
        ("management_discussion", 1500),
        ("item_1a", 1000),
        ("risk_factors", 1000),
        ("full_document", 1000),
    ]

    text_to_analyze = ""
    for key, section_limit in priority_sections:
        if key in sections and sections[key]:
            remaining = EXTRACTION_INPUT_CHAR_LIMIT - len(text_to_analyze)
            if remaining <= 0:
                break
            text_to_analyze += sections[key][:min(section_limit, remaining)] + "\n\n"

    if not text_to_analyze:
        # fall back to whatever sections exist
        text_to_analyze = "\n\n".join(list(sections.values()))[:EXTRACTION_INPUT_CHAR_LIMIT]

    prompt = EXTRACTION_PROMPT.format(text=text_to_analyze)
    raw = _call_llm(prompt)
    parsed = _parse_json_response(raw)
    return format_extracted_metrics(parsed)
