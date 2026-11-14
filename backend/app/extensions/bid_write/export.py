"""Approved bid-write revision → DOCX delivery package (批三十三).

The package is built only from the immutable revision approved in 批三十二:
AST → Markdown → one DOCX per top-level section, plus a ``manifest.json``.
Export re-runs the export gate on the frozen AST, so the file the user receives
is the same fact face the gate judged.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

from app.extensions.bid_write.approval import canonical_hash
from app.extensions.bid_write.precheck import run_export_gate

PACKAGE_FORMAT = "eai-bid-write-delivery/1"
ZIP_DATE = (2026, 1, 1, 0, 0, 0)
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ExportError(Exception):
    """Base class for export failures."""


class ExportConflict(ExportError):
    """The revision is not exportable (not approved / tampered / gate blocked)."""


@dataclass(frozen=True)
class Volume:
    name: str
    ast: dict


@dataclass(frozen=True)
class ExportBundle:
    filename: str
    payload: bytes
    sha256: str
    manifest: dict
    file_count: int
    total_bytes: int
    watermark: str | None


def _attrs(node: dict) -> dict:
    attrs = node.get("attrs")
    return attrs if isinstance(attrs, dict) else {}


def _inline_text(node: dict) -> str:
    kind = str(node.get("type") or "")
    if kind == "text":
        return str(node.get("text") or "")
    if kind == "attachment_ref":
        no = str(_attrs(node).get("attachment_no") or "").strip()
        return f"（附件 {no}）" if no else "（见附件）"
    if kind == "enum_cell":
        value = str(_attrs(node).get("current") or "").strip()
        if value:
            return value
    if kind in ("para", "locked_paragraph", "table_cell", "amount_cell", "enum_cell"):
        return "".join(_inline_text(child) for child in node.get("content") or [] if isinstance(child, dict))
    if kind in ("doc", "section", "deviation_note"):
        return "".join(_inline_text(child) for child in node.get("content") or [] if isinstance(child, dict))
    return ""


def _cell_text(node: dict) -> str:
    text = _inline_text(node).strip()
    return text.replace("|", "｜").replace("\n", " ")


def _table_markdown(node: dict) -> list[str]:
    rows = [row for row in node.get("content") or [] if isinstance(row, dict) and row.get("type") == "table_row"]
    if not rows:
        return []
    cells = [[_cell_text(cell) for cell in row.get("content") or [] if isinstance(cell, dict)] for row in rows]
    width = max(len(row) for row in cells)
    if width == 0:
        return []
    padded = [row + [""] * (width - len(row)) for row in cells]
    lines = ["| " + " | ".join(padded[0]) + " |", "| " + " | ".join("---" for _ in range(width)) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in padded[1:])
    return ["\n".join(lines)]


def _para_markdown(node: dict) -> list[str]:
    text = _inline_text(node).strip()
    label = str(_attrs(node).get("label") or "").strip()
    if not text and not label:
        return []
    if label:
        return [f"**{label}：**{text}"]
    return [text]


def _render_node(node: dict) -> list[str]:
    kind = str(node.get("type") or "")
    if kind == "section":
        attrs = _attrs(node)
        title = str(attrs.get("title") or "").strip()
        level = min(max(int(attrs.get("level") or 1), 1), 4)
        blocks: list[str] = []
        if title:
            blocks.append(f"{'#' * level} {title}")
        for child in node.get("content") or []:
            if isinstance(child, dict):
                blocks.extend(_render_node(child))
        return blocks
    if kind in ("para", "locked_paragraph"):
        return _para_markdown(node)
    if kind == "table":
        return _table_markdown(node)
    if kind == "todo_block":
        attrs = _attrs(node)
        level = str(attrs.get("level") or "D0")
        missing = str(attrs.get("missing") or "待补内容").strip()
        return [f"**【待补·{level}】** {missing}"]
    if kind == "deviation_note":
        row_id = str(_attrs(node).get("row_id") or "").strip()
        blocks = [f"**负偏离展开（行 {row_id}）**"] if row_id else ["**负偏离展开**"]
        for child in node.get("content") or []:
            if isinstance(child, dict):
                blocks.extend(_render_node(child))
        return blocks
    if kind == "toc_entry":
        attrs = _attrs(node)
        title = str(attrs.get("title") or "").strip()
        page = str(attrs.get("page_placeholder") or "—").strip()
        return [f"- {title} …… {page}"] if title else []
    if kind == "text":
        text = str(node.get("text") or "")
        return [text] if text else []
    if kind == "attachment_ref":
        return [_inline_text(node)]
    raise ValueError(f"不支持的 AST 节点: {kind or '<empty>'}")


def ast_to_markdown(ast: dict) -> str:
    """Project the frozen AST to the DOCX renderer's Markdown input.

    Marks (provenance/status_mark) are stripped: they are editor decoration, not
    document content.  Unknown node types fail loudly instead of silently
    dropping approved text.
    """

    if not isinstance(ast, dict) or ast.get("type") != "doc":
        raise ValueError('ast 根节点 type 必须为 "doc"')
    blocks: list[str] = []
    for node in ast.get("content") or []:
        if isinstance(node, dict):
            blocks.extend(_render_node(node))
    return "\n\n".join(block for block in blocks if block.strip()).strip() + "\n"


def split_volumes(ast: dict) -> list[Volume]:
    """Split at top-level level-1 sections; front matter joins the first volume."""

    if not isinstance(ast, dict) or ast.get("type") != "doc":
        raise ValueError('ast 根节点 type 必须为 "doc"')
    front: list[dict] = []
    volumes: list[dict] = []
    current: dict | None = None
    for node in ast.get("content") or []:
        if not isinstance(node, dict):
            continue
        attrs = _attrs(node)
        if node.get("type") == "section" and int(attrs.get("level") or 1) == 1:
            if current is not None:
                volumes.append(current)
            title = str(attrs.get("title") or "").strip() or f"第{len(volumes) + 1}册"
            current = {"name": title, "nodes": [node]}
            continue
        if current is None:
            front.append(node)
        else:
            current["nodes"].append(node)
    if current is not None:
        volumes.append(current)
    if not volumes:
        return [Volume(name="正文", ast={"type": "doc", "content": front})]
    volumes[0]["nodes"] = front + volumes[0]["nodes"]
    return [Volume(name=str(v["name"]), ast={"type": "doc", "content": v["nodes"]}) for v in volumes]


def _safe_name(value: str, fallback: str) -> str:
    cleaned = _INVALID_FILENAME.sub("_", value or "").strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned[:60] or fallback).strip(" .") or fallback


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    return buf.getvalue()


def _normalize_zip(data: bytes) -> bytes:
    """Re-pack a DOCX with fixed entry timestamps (python-docx uses wall clock)."""

    with zipfile.ZipFile(io.BytesIO(data)) as src:
        entries = [(info.filename, src.read(info.filename)) for info in src.infolist()]
    return _zip_bytes(entries)


def build_export_bundle(
    *,
    task,
    revision,
    gate: dict,
    now: datetime | None = None,
) -> ExportBundle:
    """Render the deterministic DOCX + manifest ZIP for an exportable revision."""

    from app.extensions.output.generator import generate_docx_simple

    generated_at = (now or datetime.now(UTC)).isoformat()
    watermark = gate.get("watermark")
    volumes = split_volumes(revision.ast or {})
    files: list[tuple[str, bytes]] = []
    manifest_files: list[dict] = []
    for index, volume in enumerate(volumes, start=1):
        markdown = ast_to_markdown(volume.ast)
        buf = io.BytesIO()
        generate_docx_simple(
            markdown,
            buf,
            template_data={"header_footer": {"showPageNumber": True}},
            watermark=watermark,
            toc_settings={"maxDepth": 3},
        )
        data = _normalize_zip(buf.getvalue())
        name = f"{index:02d}-{_safe_name(volume.name, f'第{index}册')}.docx"
        files.append((name, data))
        manifest_files.append({"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    manifest = {
        "format": PACKAGE_FORMAT,
        "task": {
            "id": task.id,
            "project_name": task.project_name or "",
            "lot_name": task.lot_name or "",
            "tender_no": task.tender_no or "",
        },
        "revision": {
            "id": revision.id,
            "revision_no": revision.revision_no,
            "doc_hash": revision.doc_hash,
            "schema_version": revision.schema_version or "",
            "decided_at": revision.decided_at.isoformat() if revision.decided_at else None,
        },
        "export": {
            "generated_at": generated_at,
            "watermark": watermark,
            "volume_count": len(files),
            "assertion_counts": gate.get("assertion_counts") or {},
            "rule_counts": gate.get("rule_counts") or {},
            "l1_fatal_fail": gate.get("l1_fatal_fail") or [],
            "reasons": gate.get("reasons") or [],
            "schema_version": gate.get("schema_version") or "",
            "scope_note": gate.get("scope_note") or "",
        },
        "files": manifest_files,
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    payload = _zip_bytes([("manifest.json", manifest_bytes), *files])
    filename = f"{_safe_name(task.project_name or '', '投标项目')}-商务正文-第{revision.revision_no}版-交付包.zip"
    return ExportBundle(
        filename=filename,
        payload=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
        manifest=manifest,
        file_count=len(files),
        total_bytes=len(payload),
        watermark=watermark,
    )


async def export_revision(
    db,
    *,
    task,
    revision,
    now: datetime | None = None,
) -> tuple[ExportBundle, object]:
    """Validate and export one approved revision, recording the audit row on success."""

    from app.extensions.bid_write import crud, worker

    if revision is None:
        raise ExportConflict("修订不存在")
    if revision.status != "approved":
        raise ExportConflict("正文尚未审批通过，不能导出")
    if canonical_hash(revision.ast or {}) != revision.doc_hash:
        raise ExportConflict("修订哈希校验失败（正文可能已被篡改），禁止导出")

    snapshot = revision.assertion_snapshot or {}
    if snapshot.get("status") == "ok" and snapshot.get("blocked"):
        raise ExportConflict("提交审批时 D0 断言已阻断，不能导出；请修订后重新提交审批")

    ctx = await worker.build_task_ctx(db, task, task.owner_id)
    try:
        gate = await run_export_gate(ctx, ast=revision.ast)
    except ValueError as exc:
        raise ExportConflict(f"导出前置校验失败：{exc}") from exc
    if gate.get("blocked"):
        reasons = "；".join(str(reason) for reason in (gate.get("reasons") or []) if str(reason).strip())
        raise ExportConflict(f"导出前置校验未通过：{reasons or '存在 D0 断言或 L1 fatal 规则失败'}")

    bundle = build_export_bundle(task=task, revision=revision, gate=gate, now=now)
    record = await crud.create_export(
        db,
        task_id=task.id,
        revision_id=revision.id,
        owner_id=task.owner_id,
        doc_hash=revision.doc_hash,
        bundle_sha256=bundle.sha256,
        file_count=bundle.file_count,
        total_bytes=bundle.total_bytes,
        watermark=bundle.watermark,
    )
    return bundle, record
