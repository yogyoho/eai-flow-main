#!/usr/bin/env python3
"""Auto-calibrate broken anchors after grounding check.

Input:  report.md + structure.json + mapping.json
Output: calibration proposal JSON → agent reviews → applies fixes → re-runs pipeline.

Algorithm: for each [⚠未找到] section, extract keywords from section name,
search structure (headings first, then paragraphs) for best match, generate
candidate anchors.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

MISSING_RE = re.compile(r"\[⚠未找到(?:锚|区间|表):\s*(.+?)(?:…|\])")
TOC_LINE_RE = re.compile(r"\t\d{1,3}$")  # TOC entries end with tab+page-number


def _is_toc_entry(text, idx, total_paras):
    """Heuristic: TOC entries are short, near document start, with page numbers."""
    if idx > total_paras * 0.15:  # only in first 15% of document
        return False
    if TOC_LINE_RE.search(text):
        return True
    # Also: very short lines with numbering in first 5% of doc
    if idx < total_paras * 0.05 and len(text) < 30 and re.match(r"^\d", text):
        return True
    return False


def _extract_keywords(section_name, source_label=""):
    """Extract search keywords from a fire-spec section name."""
    # Remove numbering prefix like "2.1 " or "5.1 "
    name = re.sub(r"^\d+(\.\d+)*\s*", "", section_name)
    # Split CJK text into 2-char bigrams for fuzzy matching
    bigrams = [name[i:i+2] for i in range(len(name)-1)]
    # Also keep full words
    words = [w for w in name.split("、") if len(w) >= 2]
    return list(set(bigrams + words))


def _score_paragraph(text, keywords):
    """Score a paragraph by keyword match density (0-1)."""
    if not text:
        return 0.0
    hits = sum(1 for kw in keywords if kw in text)
    return hits / max(len(keywords), 1)


def _find_best_paragraph(paras, headings, keywords, near_heading_text=None):
    """Find the best-matching paragraph for a set of keywords.

    Strategy:
    1. If a heading matches keywords, search paragraphs near that heading
    2. Otherwise, search all paragraphs by keyword density
    Skips TOC entries.
    """
    total = len(paras)
    # Filter out TOC entries
    body_paras = [p for p in paras if not _is_toc_entry(p["text"], p["i"], total)]

    # Strategy 1: heading-guided search
    if near_heading_text:
        heading_kw = _extract_keywords(near_heading_text)
    else:
        heading_kw = keywords

    best_heading_idx = None
    for h in headings:
        h_kw = _extract_keywords(h["text"])
        overlap = len(set(heading_kw) & set(h_kw))
        if overlap >= 1:
            best_heading_idx = h["para_i"]
            break

    if best_heading_idx is not None:
        window = 30
        candidates = [p for p in body_paras
                      if best_heading_idx <= p["i"] < best_heading_idx + window]
        if candidates:
            scored = [(p, _score_paragraph(p["text"], keywords)) for p in candidates]
            scored.sort(key=lambda x: -x[1])
            if scored[0][1] > 0:
                return scored[0][0]

    # Strategy 3: full search over body paragraphs
    scored = [(p, _score_paragraph(p["text"], keywords)) for p in body_paras]
    scored.sort(key=lambda x: -x[1])
    if scored and scored[0][1] > 0:
        return scored[0][0]
    return None


def calibrate(report_md, structure, mapping):
    """Analyze report and generate calibration proposals.

    Returns: list of {section, failed_kind, failed_label, proposal: {kind, paras|no, source_para_i, confidence}}
    """
    paras = structure["paras"]
    headings = structure.get("headings", [])
    tables = structure.get("tables", {})

    # Parse failed sections from report — match [⚠未找到段落: ...] and [⚠未找到表: ...]
    failures = []
    for line in report_md.splitlines():
        m = MISSING_RE.search(line)
        if m:
            failures.append(m.group(1))

    # Build mapping lookup
    mapping_sections = {s["fire"]: s for s in mapping.get("sections", [])}
    proposals = []

    for sec_name, sec in mapping_sections.items():
        sources = sec.get("sources", [])
        if not sources:
            continue

        for si, src in enumerate(sources):
            kind = src.get("kind", "")
            # backward-compat: "para_run" is old name for "range"
            resolved_kind = "range" if kind == "para_run" else kind

            # Check if this source failed — match by paras or no
            idxs = src.get("paras")
            no = src.get("no", "")
            failed_label = str(idxs) if resolved_kind in ("para", "range") else no
            failed = any(failed_label in f for f in failures)
            if not failed:
                continue

            keywords = _extract_keywords(sec_name, sec.get("source_label", ""))
            source_label = sec.get("source_label", sec_name)

            proposal = {
                "section": sec_name,
                "failed_kind": kind,
                "failed_label": failed_label,
            }

            if kind == "table":
                # Search tables by keyword in title or content
                best_table = None
                for tno, t in tables.items():
                    if any(kw in t.get("title", "") for kw in keywords):
                        best_table = tno
                        break
                if best_table:
                    proposal["proposal"] = {
                        "kind": "table",
                        "no": best_table,
                        "confidence": 0.7,
                        "note": f"matched by keywords: {keywords[:3]}",
                    }
                else:
                    best_no, best_score = None, 0
                    for tno, t in tables.items():
                        all_text = " ".join(" ".join(r) for r in t.get("rows", []))
                        score = _score_paragraph(all_text, keywords)
                        if score > best_score:
                            best_score = score
                            best_no = tno
                    if best_no and best_score > 0.1:
                        proposal["proposal"] = {
                            "kind": "table",
                            "no": best_no,
                            "confidence": round(best_score, 2),
                            "note": f"best table by content match (score={best_score:.2f})",
                        }

            elif resolved_kind in ("para", "range"):
                near_heading = source_label if source_label != sec_name else None
                best_p = _find_best_paragraph(paras, headings, keywords, near_heading)

                if best_p:
                    confidence = _score_paragraph(best_p["text"], keywords)
                    proposal["proposal"] = {
                        "kind": resolved_kind,
                        "paras": [best_p["i"]] if resolved_kind == "para" else [best_p["i"], best_p["i"]],
                        "source_para_i": best_p["i"],
                        "confidence": round(confidence, 2),
                        "note": best_p["text"][:80],
                    }

            proposals.append(proposal)

    return proposals


def apply_proposals(mapping, proposals, approved_indices):
    """Apply approved calibration proposals to the mapping contract.

    Writes new-format keys: "paras" for para/range, "no" for table.
    """
    mapping_sections = {s["fire"]: s for s in mapping["sections"]}
    for idx in approved_indices:
        if idx >= len(proposals):
            continue
        p = proposals[idx]
        prop = p.get("proposal")
        if not prop:
            continue
        sec = mapping_sections.get(p["section"])
        if not sec:
            continue
        for src in sec.get("sources", []):
            # Match by failed label
            kind = src.get("kind", "")
            idxs = src.get("paras")
            no = src.get("no", "")
            current_label = str(idxs) if kind in ("para", "range", "para_run") else no
            if current_label != p["failed_label"]:
                continue
            if prop["kind"] == "table":
                src["no"] = prop["no"]
            elif prop["kind"] in ("para", "range"):
                src["kind"] = prop["kind"]  # normalize para_run → range
                src["paras"] = prop["paras"]
                # Remove stale old-format keys if present
                src.pop("anchor", None)
                src.pop("from", None)
                src.pop("to", None)
            break
    return mapping


# ── CLI ────────────────────────────────────────────────────────────

def main(argv):
    if len(argv) < 2:
        print("usage: auto_calibrate.py <report.md> <structure.json> [mapping.json]", file=sys.stderr)
        print("  With mapping.json: outputs calibration proposals", file=sys.stderr)
        print("  Without: reads mapping from stdin", file=sys.stderr)
        return 2

    report = Path(argv[0]).read_text(encoding="utf-8")
    structure = json.loads(Path(argv[1]).read_text(encoding="utf-8"))

    if len(argv) >= 3:
        mapping = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    else:
        mapping = json.loads(sys.stdin.read())

    proposals = calibrate(report, structure, mapping)
    print(json.dumps(proposals, ensure_ascii=False, indent=2))
    return 0 if proposals else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
