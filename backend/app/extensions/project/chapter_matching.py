"""Match Markdown headings to template chapter titles using fuzzy matching.

Key design: headings are normalized (whitespace collapsed, punctuation stripped,
common stop words removed) before comparison.  Both H2 (##) and H3 (###)
headings are extracted.  The match threshold is intentionally low (0.45) because
AI-generated headings often differ from template titles in word order or phrasing
while referring to the same logical chapter.
"""

import re
from difflib import SequenceMatcher

# Match H1 (#) and H2 (##) headings — these correspond to chapter/section levels.
# H3 (###) headings are sub-sections too granular for chapter matching.
HEADING_PATTERN = re.compile(r"^#{1,2}\s+(.+)$", re.MULTILINE)
MIN_MATCH_RATIO = 0.55

# Common Chinese stop words removed during normalization so they don't
# artificially lower the similarity score.
_STOP_WORDS_RE = re.compile(r"[的、，。；：（）\(\)\s]+")


def _normalize(text: str) -> str:
    """Normalize heading text: lowercase, strip punctuation, collapse whitespace.

    Public so the finalize-doc endpoint can use it to build chapter title lookups.
    """
    # Remove common stop words and punctuation; collapse whitespace
    cleaned = _STOP_WORDS_RE.sub("", text.lower().strip())
    # Collapse any remaining multiple spaces
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def extract_headings(markdown_content: str) -> list[str]:
    """Extract all H2/H3 heading text from markdown content."""
    if not markdown_content:
        return []
    return [m.group(1).strip() for m in HEADING_PATTERN.finditer(markdown_content)]


def split_by_headings(markdown_content: str) -> dict[str, str]:
    """Split markdown into sections keyed by heading text."""
    if not markdown_content:
        return {}
    sections: dict[str, str] = {}
    parts = re.split(r"^#{1,2}\s+", markdown_content, flags=re.MULTILINE)
    for part in parts[1:]:  # skip content before first heading
        lines = part.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections[heading] = body
    return sections


def match_headings_to_chapters(
    headings: list[str],
    chapter_titles: list[dict],  # [{"id": uuid, "title": str}, ...]
) -> list[dict]:
    """Fuzzy-match extracted headings to template chapter titles.

    Headings and chapter titles are both normalized before comparison.
    Returns a list of matched chapters sorted by match quality (best first).
    Each entry: {"chapter_id": str, "title": str, "matched_heading": str, "ratio": float}
    """
    # Pre-normalize chapter titles
    norm_chapters = [(i, ch, _normalize(ch["title"])) for i, ch in enumerate(chapter_titles)]
    matches: list[dict] = []
    used_indices: set[int] = set()

    for heading in headings:
        norm_heading = _normalize(heading)
        if not norm_heading:
            continue

        best_ratio = 0.0
        best_idx = -1
        for i, ch, norm_title in norm_chapters:
            if i in used_indices:
                continue
            ratio = SequenceMatcher(None, norm_heading, norm_title).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i

        if best_ratio >= MIN_MATCH_RATIO and best_idx >= 0:
            used_indices.add(best_idx)
            matches.append(
                {
                    "chapter_id": str(chapter_titles[best_idx]["id"]),
                    "title": chapter_titles[best_idx]["title"],
                    "matched_heading": heading,
                    "ratio": round(best_ratio, 3),
                }
            )

    # Sort by match quality, best first
    matches.sort(key=lambda m: m["ratio"], reverse=True)
    return matches
