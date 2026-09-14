"""
Document parsing: PDF -> raw text -> rough section split.

10-Ks are inconsistently formatted across companies, so this is
intentionally simple (keyword-based) to start. Swap in a smarter
approach (e.g. a cheap LLM classification pass per page) once you've
tested this against a few real filings and see where it breaks.
"""

import re

import pdfplumber

# Common 10-K / 10-Q / earnings call section headers to split on.
# Extend this list as you test against real filings.
SECTION_MARKERS = [
    "management's discussion and analysis",
    "management's discussion and analysis of financial condition and results of operations",
    "item 2. management's discussion and analysis of financial condition and results of operations",
    "item 7. management's discussion and analysis of financial condition and results of operations",
    "item 2",
    "item 1a",
    "item 3",
    "item 4",
    "part ii",
    "md&a",
    "risk factors",
    "financial statements",
    "condensed consolidated statements of operations",
    "consolidated statements of operations",
    "notes to consolidated financial statements",
    "liquidity and capital resources",
    "results of operations",
    "net sales",
    "total net sales",
    "forward-looking statements",
]


def extract_text_from_pdf(file_path: str) -> str:
    """Extract raw text from a PDF, page by page."""
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts)


def split_into_sections(text: str) -> dict[str, str]:
    """
    Rough split of the document into named sections based on
    known header phrases. Falls back to putting everything under
    'full_document' if no markers are found, so the pipeline never
    breaks on an unfamiliar format — it just loses precision.
    """
    text_lower = text.lower()
    found_positions = []
    matched_markers = []

    for marker in SECTION_MARKERS:
        pattern = r"\n\s*" + re.escape(marker)
        matches = []
        for match in re.finditer(pattern, text_lower):
            match_start = match.start() + match.group(0).find(marker)
            matches.append(match_start)

        if matches:
            matched_markers.append((marker, matches))
            print(f"Matched marker: {marker!r} at positions {matches}")
            for pos in matches:
                found_positions.append((pos, marker))

    if not found_positions:
        print("No section markers matched; falling back to full_document.")
        return {"full_document": text}

    print(f"Total matched markers: {len(matched_markers)}")

    found_positions.sort(key=lambda x: x[0])

    # TOC structure varies across filings, but its many markers tend to be
    # packed together near the start while real section headers are spread out.
    toc_indices = {
        index
        for index, (position, _) in enumerate(found_positions)
        if sum(
            1
            for other_index, (other_position, _) in enumerate(found_positions)
            if other_index != index and abs(other_position - position) <= 3000
        ) >= 3
    }

    fallback_indices = set()
    marker_indices: dict[str, list[int]] = {}
    for index, (_, marker) in enumerate(found_positions):
        key = marker.replace(" ", "_").replace("'", "").replace("&", "and")
        marker_indices.setdefault(key, []).append(index)
    for indices in marker_indices.values():
        if all(index in toc_indices for index in indices):
            fallback_indices.add(indices[-1])

    considered_positions = [
        entry
        for index, entry in enumerate(found_positions)
        if index not in toc_indices or index in fallback_indices
    ]

    sections: dict[str, str] = {}
    for i, (start, marker) in enumerate(considered_positions):
        end = considered_positions[i + 1][0] if i + 1 < len(considered_positions) else len(text)
        key = marker.replace(" ", "_").replace("'", "").replace("&", "and")
        # Keep the longest chunk found for a given marker (avoids tiny
        # fragments when a header phrase appears more than once, e.g.
        # in a table of contents)
        chunk = text[start:end].strip()
        if key not in sections or len(chunk) > len(sections[key]):
            sections[key] = chunk

    return sections
