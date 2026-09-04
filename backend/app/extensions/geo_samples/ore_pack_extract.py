# EAI-CUSTOM (P5 T5, plan 2026-09-04-geo-p5-orepack, spec 2026-09-01 §5.3/§9 Phase 3):
# ore_pack 批量孵化抽取管线。ExtractionLLMClient 形态（knowledge_factory.llm）：
# create_chat_model 懒加载 + 6 级 JSON 容错解析（复用其 _extract_json 单源，勿复制）+
# Semaphore(3) 并发限流 + DB 默认模型（SystemConfigService.default_model → DEFAULT_MODEL
# env → config 首模型）。LLM 幻觉双兜底：未核实阈值必须 {"status": "【待核实】"} 形态 +
# validate_ore_pack 锚点守卫；errors 非空草稿仍落表供人审可见，approve 前置 = errors==[]。
"""ore_pack 批量孵化：LLM 抽草稿 → validate → 草稿表 → 人审 → ore_packs/ 落 repo。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.extensions.knowledge_factory.llm import ExtractionLLMClient
from deerflow.models import create_chat_model

from . import crud
from .ore_pack_schema import KNOWN_SLUGS, PENDING, validate_ore_pack

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
# 与 service._SKILL_DIR 同根：dev bind-mount 直写；离线生产 references 易失性见
# deploy/offline/MANUAL-UPGRADE.md（P3-T9 runbook）。
ORE_PACK_DIR = _REPO_ROOT / "skills" / "public" / "geological-report" / "references" / "ore_packs"

SLICE_MAX_CHARS = 8000  # 每片截断（plan T5 要点：用户消息=切片文本集合，每片 8000 字符）
MAX_SLICES = 20  # 单次抽取切片数上限（endpoints 的 Request 模型同值）
# 并发限流：同 kf pipeline（Semaphore 限 LLM 并发防供应商限流）——全模块共享，
# 并发 extract 请求共享 3 个槽位。
_SEM = asyncio.Semaphore(3)

_SYSTEM_PROMPT = """你是地质勘查报告矿种知识包（ore_pack）抽取器。
从给定的地质勘查报告切片中抽取 {mineral} 矿种知识包 JSON。schema 契约：
- 元数据键：version（固定 "2.0"）、ore（固定 "{mineral}"）、generated（YYYY-MM-DD）
- 业务键白名单（只允许这些键；切片无对应内容时该键省略，禁止自造键）：
  basic_analysis_items（数组）、phase_analysis（对象，必含 zone_split_rule 子对象）、
  ore_natural_types_anchored（对象）、byproduct_policy（串）、bulk_density_practice（对象）、
  green_exploration（串）、typical_deposit_models（对象数组）、reporting_notes（数组）、
  std_ref（串，规范出处）
- 全文必须引用 ≥1 个 DZ 标准估算链公式编号（L11/S1/B1/E3/E4），锚定到具体业务键的说明里
- 未核实的阈值禁止写成裸串断言，必须 {{"status": "【待核实】", "note": "…"}} 结构形态
- 只从切片原文抽取，禁编造；数值/专名须能在切片中找到出处
输出：仅一个 JSON 对象，不要多余文字。"""


def load_slices(slice_paths: list[str]) -> list[str]:
    """载入切片文本：非绝对路径按仓库根拼接；越界/缺失拒绝（LLM 输入信任边界）。

    每片截断 SLICE_MAX_CHARS。阻塞文件读——调用方负责 asyncio.to_thread。
    """
    texts: list[str] = []
    for raw in slice_paths:
        p = Path(raw)
        if not p.is_absolute():
            p = _REPO_ROOT / p
        p = p.resolve()
        if not p.is_relative_to(_REPO_ROOT):
            raise ValueError(f"切片路径越界（仓库根外）: {raw}")
        if not p.is_file():
            raise ValueError(f"切片不存在: {raw}")
        texts.append(p.read_text(encoding="utf-8")[:SLICE_MAX_CHARS])
    return texts


def slices_hash(texts: list[str]) -> str:
    """抽取输入指纹（sha256）：同输入可对账，换切片集即换指纹。"""
    return hashlib.sha256("\x00".join(texts).encode("utf-8")).hexdigest()


class OrePackExtractor:
    """ExtractionLLMClient 形态的矿种包抽取器（同步 invoke——调用方 to_thread + 限流）。

    模型解析序：显式 model_name → DB default_model（crud.get_default_model_name，调用方传）
    → DEFAULT_MODEL env → config 首模型。max_tokens=16384 同 kf bug-1243（8192 对结构化
    输出太紧，截断后 6 级解析必失败）。
    """

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name
        self._model = None  # 懒加载

    @property
    def model(self):
        if self._model is None:
            effective = self._model_name or os.getenv("DEFAULT_MODEL") or None
            self._model = create_chat_model(name=effective, thinking_enabled=False).bind(max_tokens=16384)
        return self._model

    def extract_sync(self, mineral: str, slice_texts: list[str]) -> dict:
        """切片集合 → ore_pack 草稿 dict（6 级 JSON 容错，复用 kf _extract_json 单源）。"""
        user = "\n\n".join(f"## 切片 {i + 1}\n{t}" for i, t in enumerate(slice_texts))
        response = self.model.invoke([SystemMessage(content=_SYSTEM_PROMPT.format(mineral=mineral)), HumanMessage(content=user)])
        raw = response.content if hasattr(response, "content") else str(response)
        result = ExtractionLLMClient._extract_json(raw)
        if not isinstance(result, dict):
            raise ValueError(f"LLM 输出非 JSON 对象（{type(result).__name__}）")
        return result


async def run_extract(db, mineral: str, slice_texts: list[str]) -> None:
    """后台抽取任务（BackgroundTasks，切片已由端点载入）：LLM → validate → 落草稿表。

    任何异常也落失败草稿行（draft_json=None, errors=["抽取失败: …"]）——后台静默失败
    会让人审页永远等不到草稿（gateway 重启杀 in-flight 后台任务同款盲区）。
    """
    h = slices_hash(slice_texts)
    try:
        model_name = await crud.get_default_model_name(db)
        async with _SEM:
            doc = await asyncio.to_thread(OrePackExtractor(model_name=model_name).extract_sync, mineral, slice_texts)
    except Exception as e:  # noqa: BLE001 —— 落账兜底，见 docstring
        logger.warning("[ore-pack] extract failed mineral=%s: %s", mineral, e)
        await crud.create_draft(db, mineral=mineral, slices_hash=h, draft_json=None, errors=[f"抽取失败: {e}"])
        return
    errors = validate_ore_pack(doc)
    await crud.create_draft(db, mineral=mineral, slices_hash=h, draft_json=doc, errors=errors)


def pending_obligations(doc: dict) -> list[str]:
    """【待核实】节点 → standards_index 人工录入义务清单（"路径 — note"）。

    approve 响应携带：过审落 repo ≠ 义务完成，阈值仍须对照规范原文录 standards_index。
    """
    out: list[str] = []

    def _walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            if node.get("status") == PENDING:
                note = node.get("note", "")
                out.append(f"{path} — {note}" if note else path)
            else:
                for k, v in node.items():
                    _walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _walk(v, f"{path}[{i}]")

    _walk(doc, "")
    return out


def write_ore_pack_file(mineral: str, doc: dict) -> str:
    """过审草稿 → repo ore_packs/<mineral>.json（dev bind-mount 直写；阻塞调用，调用方 to_thread）。

    mineral 须 ∈ KNOWN_SLUGS（other 不孵化——词表单源裁决）；ensure_ascii=False 保中文可读。
    """
    if mineral not in KNOWN_SLUGS:
        raise ValueError(f"mineral 非法: {mineral}（须 ∈ {sorted(KNOWN_SLUGS)}；other 不孵化）")
    ORE_PACK_DIR.mkdir(parents=True, exist_ok=True)
    path = ORE_PACK_DIR / f"{mineral}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)
