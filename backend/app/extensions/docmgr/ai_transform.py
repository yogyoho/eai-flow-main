"""EAI-CUSTOM: docmgr 全文操作 M1 + 审查 M2（spec: docs/superpowers/specs/2026-10-29-docmgr-ai-fulltext-ops-design.md §4/§5）。

- 服务端零读盘：content 请求体直传，thread_id/rel_path 仅审计日志用（无越权读通道、无 PUT-read 竞态）。
- 模型装配走 create_chat_model（同 routers.py ai-edit 先例），max_tokens 显式 8192 防 provider 默认 4096 截断。
- M1 产出永远是 DocOperation[]（新增 replace_section）；分节引擎为确定性纯函数，同 content 必得同边界。
- 无损性（T0 bug-3600）：split("\\n") 分桶后每非末桶/非末段补回边界换行符，"".join(各节) == 原文。
- M2 审查（/ai/review）：只报告不改文，产出 findings（契约 contracts/docmgr_findings.v1.json）；
  consistency/numbering 两遍法（全文扫描建全局对照表→逐节携表审查），units/custom 单遍逐节；
  findings 过滤（severity 白名单外降级 warn / 缺字段丢条 / excerpt 截断 120 字）在服务端权威收口，
  fixed_section → fix_op（replace_section）复用既有 applyOperations 回灌，零新应用机制。
- I2 铁律（审查侧同样覆盖）：每个模型调用（含两遍法的扫描第一遍）都 wait_for + except，
  provider 挂起不得变成 200 + 零事件 + 永久悬挂。
- 升级注意：collab_ai_chat.py 的裸 httpx 装配是反面教材（无 override / 无 max_tokens / 错误静默），勿回抄。
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.extensions.auth.middleware import require_permission
from app.extensions.docmgr.routers import _extract_ai_response_text
from app.extensions.schemas import CurrentUser  # 与 routers.py 同源（routers.py:26 同一 import）
from deerflow.models import create_chat_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/docmgr", tags=["docmgr-ai"])  # EAI-CUSTOM: 独立模块 router，gateway app.py 挂载区注册
_doc_perm = require_permission("doc:upload")  # EAI-CUSTOM: 模块级命名依赖（同 ai-edit 的 doc:upload 门），测试可 dependency_overrides

SECTION_CHAR_LIMIT = 4000  # T0 实测 section p99=2864，23/5287 节超限走再切
MAX_SECTIONS = 300  # T0 实测单文档节数 max=261（真实地质报告），200 会截断故取 300
MAX_CONTENT_CHARS = 400_000  # T0 实测 doc max=337k，>400k 文档数 0
SECTION_TIMEOUT_SECONDS = 120
SUMMARY_TIMEOUT_SECONDS = 180

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


# ── 分节引擎（纯函数） ────────────────────────────────────────────────


def _is_structured(text: str) -> bool:
    """节内含公式($$)/表格/图片/折叠块 → v1 整节跳过（不做块级穿引，spec §8）。"""
    if "$$" in text:
        return True
    if re.search(r"^!\[.*\]\(.*\)", text, re.M):
        return True
    if "<details" in text.lower():
        return True
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 1:
            return True
    return False


def _segments(text: str) -> list[str]:
    """节文本 → 最小不可切单元序列（代码围栏 / $$..$$ / 表格 / <details> / 空行分段）。

    依序拼接 == text（无损；split("\\n") 吞掉的段边界换行符补回非末段段尾，bug-3600）。
    已知天花板：围栏/公式区内的 `#` 行不影响本函数；顶层标题切分在 split_sections
    也不感知围栏（围栏内 `# ` 行会被当标题切节）——v1 按 spec §4.2 字面行为，暂不处理。
    """
    lines = text.split("\n")
    buckets: list[list[str]] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf  # 闭包重绑外层 buf；缺 nonlocal 会 UnboundLocalError
        if buf:
            buckets.append(buf)
            buf = []

    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush()
            j = i + 1
            while j < n and not lines[j].strip().startswith("```"):
                j += 1
            j = min(j + 1, n)
            buckets.append(lines[i:j])
            i = j
            continue
        if s.startswith("$$"):
            flush()
            if s.endswith("$$") and len(s) > 2:
                buckets.append([line])  # 单行 $$...$$ 数学，自含原子
                i += 1
                continue
            j = i + 1
            while j < n and "$$" not in lines[j]:
                j += 1
            j = min(j + 1, n)
            buckets.append(lines[i:j])
            i = j
            continue
        if s.lower().startswith("<details"):
            flush()
            j = i + 1
            while j < n and "</details>" not in lines[j].lower():
                j += 1
            j = min(j + 1, n)
            buckets.append(lines[i:j])
            i = j
            continue
        if s.startswith("|"):
            flush()
            j = i
            while j < n and lines[j].strip().startswith("|"):
                j += 1
            buckets.append(lines[i:j])
            i = j
            continue
        if not s:
            flush()
            buckets.append([line])  # 空行独立成段（无损拼接由边界补 \\n 保证）
            i += 1
            continue
        buf.append(line)
        i += 1
    flush()
    last = len(buckets) - 1
    return ["\n".join(b) + ("\n" if k < last else "") for k, b in enumerate(buckets)]


_SENTENCE_END_RE = re.compile(r"[。．.!?！？；;\n]")


def _hard_cut(text: str, limit: int) -> list[str]:
    """单原子段仍超限 → 句号边界硬切（保底不丢字；依序拼接 == text）。"""
    out: list[str] = []
    start, n = 0, len(text)
    while n - start > limit:
        bound = start + limit
        last_end = -1
        for m in _SENTENCE_END_RE.finditer(text, start, bound + 1):
            last_end = m.end()
        cut = last_end if last_end > start else bound
        out.append(text[start:cut])
        start = cut
    if start < n:
        out.append(text[start:])
    return out or [text]


def _split_long(text: str, limit: int = SECTION_CHAR_LIMIT) -> list[str]:
    """超长节按原子段聚合再切；依序拼接 == text。"""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for seg in _segments(text):
        if len(seg) > limit:
            if cur:
                chunks.append("".join(cur))
                cur, size = [], 0
            s = seg.strip()
            # I4: 超长原子桶（围栏/$$/折叠/表格，分支开与 _segments 严格对应；buf 桶不可能以这些开头）
            # 句号硬切会腰斩围栏/表格原子性（多数片 ``` 计数为奇），分片输出重拼还会静默腐坏代码
            # → 整段保留为单 chunk，交由 split_sections 的超长 piece 规则整节跳过
            if s.startswith("```") or s.startswith("$$") or s.lower().startswith("<details") or s.startswith("|"):
                chunks.append(seg)
            else:
                chunks.extend(_hard_cut(seg, limit))
            continue
        if size + len(seg) > limit and cur:
            chunks.append("".join(cur))
            cur, size = [], 0
        cur.append(seg)
        size += len(seg)
    if cur:
        chunks.append("".join(cur))
    return chunks


def split_sections(content: str) -> list[dict]:
    """按 ATX 标题切节（确定性纯函数）。

    返回 [{"title", "level", "content", "structured", "pieces"}]；无标题文档 = 单节
    （title=""）；空文档 = []；各节 content 依序拼接 == 原文（无损划分，bug-3600 修复：
    每非末桶补回 split 吞掉的边界换行符）。
    """
    if not content.strip():
        return []
    raw: list[tuple[str, int | None, list[str]]] = []
    cur_title: str = ""
    cur_level: int | None = None
    buf: list[str] = []
    for line in content.split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            if buf:
                raw.append((cur_title, cur_level, buf))
            cur_title, cur_level, buf = m.group(2).strip(), len(m.group(1)), [line]
        else:
            buf.append(line)
    if buf:
        raw.append((cur_title, cur_level, buf))

    last = len(raw) - 1
    # 无损重建：非末桶补回边界换行符（末桶的行列表自带一切尾部内容，包括末尾换行或其缺失）
    texts = ["\n".join(ls) + ("\n" if k < last else "") for k, (_t, _l, ls) in enumerate(raw)]

    sections: list[dict] = []
    lead = ""
    for k, (title, level, _ls) in enumerate(raw):
        text = texts[k]
        if not text.strip():
            if sections:
                sections[-1]["content"] += text  # 空白块并入前节，保持无损
            else:
                lead += text
            continue
        if lead:
            text = lead + text
            lead = ""
        structured = _is_structured(text)
        # pieces 与 structured 无关地按长度再切：端点对 structured 节在消费 pieces 前已跳过，
        # 而表/公式节同样需要原子分片能力（test_table_atomic 语义），留 pieces 才不损失信息
        pieces = [text] if len(text) <= SECTION_CHAR_LIMIT else _split_long(text)
        if any(len(p) > SECTION_CHAR_LIMIT + 1 for p in pieces):
            # I4: 存在超长原子段（>4000 的围栏/$$/表格桶）无法安全逐片处理，v1 整节跳过。
            # +1 容差：_hard_cut 合法上限 4001（句末符恰落扫描窗末位），>4001 才必是原子桶整段保留；
            # 恰 4001 的原子桶不判跳过也无害（单 piece 直接进模型，安全）——否则纯 prose 节被随机误跳
            structured = True
        sections.append(
            {
                "title": title,
                "level": level,
                "content": text,
                "structured": structured,
                "pieces": pieces,
            }
        )
    return sections


# ── 预设 prompt ───────────────────────────────────────────────────────

_REWRITE_PRESETS: dict[str, dict] = {
    "polish": {"rules": "任务=全文润色：使语句更流畅、专业，不改变原意，不增删信息。"},
    "proofread": {"rules": "任务=全文校对：仅修正错别字、标点误用、单位符号格式；没有错误的原句原样保留，禁止改写措辞。"},
    "format": {"rules": "任务=格式规范：修正标题层级跳级、序号不连续、中英文之间缺空格；不改动句子措辞与内容。"},
    "terminology": {"rules": "任务=术语统一：按术语表把变体术语替换为标准术语，其余内容一字不改。"},
}

_REWRITE_PROMPT = """你是文档编辑器中的全文处理助手。下面是一篇文档中的一节，请对这一节执行指定任务。

**任务**：{rules}

**硬性约束**：
1. 只输出处理后的这一节 markdown 正文；不要任何解释、前言、结语，也不要用 ```markdown 围栏包裹全文
2. 除任务明确要求外，保持标题层级、列表/引用结构、加粗斜体不变；代码块内容一字不改
3. 保留所有数字、单位、公式、图表引用标号不变
4. 输出语言与原文一致
{terminology_block}
**本节内容**：
{section}"""

_TERMINOLOGY_SCAN_PROMPT = """你是术语审校助手。扫描下方文档全文，找出「同一概念使用了多个不同名称」的术语变体组（例如「给水系统」与「供水系统」混用）。

只输出 JSON 数组，格式：[{{"canonical": "应统一采用的标准术语", "variants": ["变体1", "变体2"]}}]
没有发现任何变体时输出 []。不要输出解释。

**文档全文**：
{doc}"""

_SUMMARY_MAP_PROMPT = """你是摘要助手。请用 3-5 句话概括以下文档片段的要点，保留关键数据。只输出概括文本。

**片段**：
{section}"""

_SUMMARY_REDUCE_PROMPT = """你是摘要助手。以下是一篇长文档各部分的要点概括，请整合成一篇 200-400 字的全文摘要，保留关键数据与结论。只输出摘要正文（可含一个「## 全文摘要」标题）。

**各部分要点**：
{digest}"""

_ALL_OPERATIONS = set(_REWRITE_PRESETS) | {"toc", "summary"}


# ── 工具 ──────────────────────────────────────────────────────────────


def _ndjson(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _norm(t: str) -> str:
    return re.sub(r"\s+", "", t)


def _norm_lines(t: str) -> str:
    """仅归一换行周边空白。format 的「中英文之间加空格」是纯行内空白差异，
    _norm 的全空白归一会把它误判为无变更（I1）——format 预设改用本函数做 unchanged 判定。"""
    return re.sub(r"\s*\n\s*", "\n", t).strip()


def _strip_markdown_fence(text: str) -> str:
    """仅剥 ```markdown 包裹（模型无视约束时的兜底）；正文自身以代码围栏开头则不动。"""
    t = text.strip()
    if t.startswith("```markdown"):
        body = t[t.find("\n") + 1 :] if "\n" in t[:20] else t[len("```markdown") :]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: body.rstrip().rfind("```")]
        return body.strip("\n")
    return text.strip("\n")


def _build_toc(content: str) -> str | None:
    """纯机械生成目录（不调模型）：扫 ATX 标题产缩进列表；无标题返回 None。"""
    items: list[tuple[int, str]] = []
    for line in content.split("\n"):
        m = _HEADING_RE.match(line)
        if m and m.group(2).strip():
            items.append((len(m.group(1)), m.group(2).strip()))
    if not items:
        return None
    lines = ["## 目录", ""]
    for level, title in items:
        if title == "目录":
            continue
        lines.append(f"{'  ' * (level - 1)}- {title}")
    return "\n".join(lines) + "\n"


async def _scan_terminology(model, doc: str) -> list[dict]:
    """术语统一第一遍：全文扫变体，返回 [{canonical, variants}]；超时/异常/解析失败一律按无变体处理（调用方空表短路）。"""
    try:
        # I2: 唯一在首个 yield 之前执行的模型调用——无超时无兜底时 provider 挂起会变成
        # 200 + 零事件 + 永久悬挂，必须与各节调用同规格地上 wait_for + except
        resp = await asyncio.wait_for(model.ainvoke(_TERMINOLOGY_SCAN_PROMPT.format(doc=doc)), timeout=SUMMARY_TIMEOUT_SECONDS)
    except Exception:
        logger.warning("docmgr terminology scan failed, treated as no variants", exc_info=True)
        return []
    m = re.search(r"\[[\s\S]*\]", _extract_ai_response_text(resp.content))
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and isinstance(item.get("canonical"), str) and isinstance(item.get("variants"), list):
            if item["canonical"] in seen:
                continue  # M4: 重复 canonical 保首组
            variants = list(dict.fromkeys(v for v in item["variants"] if isinstance(v, str) and v and v != item["canonical"]))
            if variants:
                seen.add(item["canonical"])
                out.append({"canonical": item["canonical"], "variants": variants})
    return out


def _terminology_block(table: list[dict]) -> str:
    if not table:
        return ""
    rows = "\n".join(f"- 「{t['canonical']}」 ← {'、'.join('「' + v + '」' for v in t['variants'])}" for t in table)
    return f"\n**术语表（必须执行替换）**：\n{rows}\n"


async def _rewrite_section(model, operation: str, section: dict, terminology_block: str) -> str:
    """单节改写：超长节分片逐片调模型，输出按片序拼接。"""
    preset = _REWRITE_PRESETS[operation]
    outs: list[str] = []
    for piece in section["pieces"]:
        prompt = _REWRITE_PROMPT.format(rules=preset["rules"], terminology_block=terminology_block, section=piece)
        resp = await asyncio.wait_for(model.ainvoke(prompt), timeout=SECTION_TIMEOUT_SECONDS)
        outs.append(_strip_markdown_fence(_extract_ai_response_text(resp.content)))
    return "\n\n".join(outs)


# ── 端点 ──────────────────────────────────────────────────────────────


class AITransformRequest(BaseModel):
    thread_id: str = Field(..., description="仅审计日志；服务端零读盘")
    rel_path: str = Field(..., description="仅审计日志；服务端零读盘")
    operation: str = Field(..., description="polish | proofread | terminology | format | toc | summary")
    content: str = Field(..., min_length=1, description="面板当前全文 markdown（请求体直传）")
    model_name: str | None = Field(None, description="模型覆盖，缺省走 Settings 默认")
    sections: list[int] | None = Field(None, description="全量切分后的节下标，部分重跑；仅改写预设有效，toc/summary 忽略此参数全量处理")


@router.post("/ai/transform")
async def ai_transform(
    request: AITransformRequest,
    current_user: CurrentUser = Depends(_doc_perm),  # EAI-CUSTOM: 权限门同 ai-edit 先例
):
    if request.operation not in _ALL_OPERATIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown operation: {request.operation}. Must be one of: {sorted(_ALL_OPERATIONS)}")
    if len(request.content) > MAX_CONTENT_CHARS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"文档过长（>{MAX_CONTENT_CHARS} 字符），请分段处理")
    model = create_chat_model(name=request.model_name, thinking_enabled=False, model_overrides={"max_tokens": 8192})
    sections = split_sections(request.content)
    if len(sections) > MAX_SECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"分节数超过上限 {MAX_SECTIONS}，请分段处理")
    chosen = list(range(len(sections))) if request.sections is None else sorted({i for i in request.sections if 0 <= i < len(sections)})
    logger.info(
        "docmgr ai_transform user=%s op=%s thread=%s rel=%s sections=%d/%d chars=%d",
        getattr(current_user, "id", "?"),
        request.operation,
        request.thread_id,
        request.rel_path,
        len(chosen),
        len(sections),
        len(request.content),
    )

    async def generate() -> AsyncIterator[str]:
        failed: list[int] = []
        skipped: list[int] = []
        message: str | None = None

        if request.operation == "toc":
            # EAI-CUSTOM (全文操作 M1, 终审 I-1b): 生成目录前防重插——content 已含
            # 「目录」标题时直接跳过，避免 TOC 块重复插入（终审 I-1 撞锚点链路的前置防线）。
            if re.search(r"^#{1,6}\s*目录\s*$", request.content, re.MULTILINE):
                yield _ndjson({"type": "done", "total": 0, "failed": [], "skipped": [], "message": "文档已含目录，跳过生成"})
                return
            toc_md = _build_toc(request.content)
            if toc_md is None:
                message = "文档没有标题，无法生成目录"
            else:
                yield _ndjson({"type": "section_start", "index": 0, "total": 1, "title": "目录"})
                yield _ndjson({"type": "ops", "index": 0, "ops": [{"op": "prepend", "content": toc_md}]})
            done: dict = {"type": "done", "total": 0 if toc_md is None else 1, "failed": [], "skipped": []}
            if message:
                done["message"] = message
            yield _ndjson(done)
            return

        if request.operation == "summary":
            digest: list[str] = []
            for i, sec in enumerate(sections):
                if sec["structured"]:
                    skipped.append(i)
                    continue
                yield _ndjson({"type": "section_start", "index": i, "total": len(sections), "title": sec["title"] or f"第 {i + 1} 节"})
                try:
                    resp = await asyncio.wait_for(model.ainvoke(_SUMMARY_MAP_PROMPT.format(section=sec["content"])), timeout=SECTION_TIMEOUT_SECONDS)
                    digest.append(_extract_ai_response_text(resp.content).strip())
                    # EAI-CUSTOM (全文操作 M1, 终审 M-1): 成功节补空 ops 事件——
                    # reducer 空 ops → unchanged 终态，卡片不再永久「生成中…」。
                    yield _ndjson({"type": "ops", "index": i, "ops": []})
                except Exception as e:
                    failed.append(i)
                    logger.warning("docmgr summary map section %s failed: %s", i, e, exc_info=True)
                    yield _ndjson({"type": "section_error", "index": i, "message": "本节概括失败，已跳过"})
            if digest:
                try:
                    resp = await asyncio.wait_for(model.ainvoke(_SUMMARY_REDUCE_PROMPT.format(digest="\n\n".join(digest))), timeout=SUMMARY_TIMEOUT_SECONDS)
                    yield _ndjson({"type": "summary", "content": _extract_ai_response_text(resp.content).strip()})
                except Exception as e:
                    logger.warning("docmgr summary reduce failed: %s", e, exc_info=True)
                    message = "摘要整合失败，请重试"
            done = {"type": "done", "total": len(sections), "failed": failed, "skipped": skipped}
            if message:
                done["message"] = message
            yield _ndjson(done)
            return

        # 逐节改写预设（polish / proofread / terminology / format）
        terminology_block = ""
        if request.operation == "terminology":
            table = await _scan_terminology(model, request.content)
            if not table:
                # I2 配套短路：空术语表逐节喂「按术语表替换」是无意义 N 次模型调用
                yield _ndjson({"type": "done", "total": 0, "failed": [], "skipped": [], "message": "未发现术语变体，无需统一"})
                return
            terminology_block = _terminology_block(table)
        for i in chosen:
            sec = sections[i]
            start_ev: dict = {"type": "section_start", "index": i, "total": len(chosen), "title": sec["title"] or f"第 {i + 1} 节"}
            if sec["structured"]:
                start_ev["skipped"] = True
                skipped.append(i)
                yield _ndjson(start_ev)
                continue
            yield _ndjson(start_ev)
            if not sec["title"]:
                failed.append(i)
                yield _ndjson({"type": "section_error", "index": i, "message": "文档无标题（全文单节），无法按节定位；请先给文档加标题，或改用对话模式"})
                continue
            try:
                new_md = await _rewrite_section(model, request.operation, sec, terminology_block)
            except Exception as e:
                failed.append(i)
                logger.warning("docmgr ai_transform section %s failed: %s", i, e, exc_info=True)
                yield _ndjson({"type": "section_error", "index": i, "message": "本节处理失败，可稍后单独重试本节"})
                continue
            # I1: format 的交付含行内空白调整（中英文加空格），_norm 全空白归一会误判无变更；
            # 仅 format 用 _norm_lines（保行内空白、归一折行），其余预设折行/空白忽略语义不变
            _checker = _norm_lines if request.operation == "format" else _norm
            if _checker(new_md) == _checker(sec["content"]):
                yield _ndjson({"type": "ops", "index": i, "ops": []})
                continue
            yield _ndjson({"type": "ops", "index": i, "ops": [{"op": "replace_section", "anchor": sec["title"], "content": new_md}]})
        done = {"type": "done", "total": len(chosen), "failed": failed, "skipped": skipped}
        if message:
            done["message"] = message
        yield _ndjson(done)

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 审查（M2）─────────────────────────────────────────────────────────


# EAI-CUSTOM (全文操作 M2): 审查类型与 severity 白名单；excerpt 契约上限 120 字（服务端截断）
_ALL_REVIEW_TYPES = {"consistency", "numbering", "units", "custom"}
_REVIEW_SEVERITIES = ("error", "warn", "info")
_REVIEW_EXCERPT_MAX = 120

_NUMBERING_SCAN_PROMPT = """你是编号审校助手。扫描下方文档全文，提取标题编号与正文中的显式编号序列（章节号如 1 / 1.1、中文序号如 一、（一）、条款号、图表编号等），按所在章节分组。

只输出 JSON 数组，格式：[{{"title": "编号所在章节标题", "numbers": ["1", "1.1", "1.2"]}}]
没有发现任何编号序列时输出 []。不要输出解释。

**文档全文**：
{doc}"""

_REVIEW_FOCUS: dict[str, str] = {
    "consistency": "术语一致性",
    "numbering": "编号连续性",
    "units": "公式单位规范",
    "custom": "用户指定关注点",
}

_REVIEW_RULES: dict[str, str] = {
    "consistency": "对照下方术语表，逐句检查本节是否仍残留术语表右列的变体术语；残留即报，术语表之外的措辞差异不报。",
    "numbering": "对照下方全文编号清单，检查本节标题与正文中的编号：跳号、断档、重复、层级错乱均报。",
    "units": "检查本节公式与数值的单位使用规范：单位缺失、同一物理量前后单位不统一、量纲或单位符号书写不一致均报；只报告问题，不要为改格式而改文。",
}

# EAI-CUSTOM (全文操作 M2): fixed_section 鼓励语仅 consistency/units 注入；numbering/custom 的 prompt 不给该字段提示
_REVIEW_FIX_HINT = """
   - 可选 "fixed_section"：仅当你确能给出该节的完整修正版 markdown 全文时提供；给不出完整修正节就不要提供该字段；只修问题本身，不要为改格式而改文"""

_REVIEW_SECTION_PROMPT = """你是文档审校助手。下面是一篇文档中的一节，请只审查这一节中的「{focus}」问题。

**审查要求**：{rules}
{context_block}
**输出约束**：
1. 只输出 JSON 数组；未发现任何问题时输出 []
2. 数组每个元素是一个 JSON 对象，字段如下（id 由服务端生成，不要输出 id 字段）：
   - "severity"："error"=确定错误/歧义；"warn"=疑似不一致；"info"=建议级
   - "anchor"：问题所在节标题，固定填下方给出的「本节标题」
   - "excerpt"：问题原文片段，从原文逐字摘录，≤120 字，不得改写
   - "problem"：问题描述（一句话）
   - "suggestion"：修改建议（一句话）{fix_hint}
3. 不要输出解释、前言、结语，也不要用 ``` 围栏包裹

**本节标题**：{title}
**本节内容**：
{section}"""


class AIReviewRequest(BaseModel):
    thread_id: str = Field(..., description="仅审计日志；服务端零读盘")
    rel_path: str = Field(..., description="仅审计日志；服务端零读盘")
    review_type: str = Field(..., description="consistency | numbering | units | custom")
    instruction: str | None = Field(None, description="custom 审查指令；review_type=custom 时必填")
    model_name: str | None = Field(None, description="模型覆盖，缺省走 Settings 默认")
    content: str = Field(..., min_length=1, description="面板当前全文 markdown（请求体直传）")


def _numbering_block(table: list[dict]) -> str:
    if not table:
        return ""
    rows = "\n".join(f"- 「{t['title']}」：{'、'.join(t['numbers'])}" for t in table)
    return f"\n**全文编号清单（审查对照基准）**：\n{rows}\n"


async def _scan_numbering(model, doc: str) -> list[dict]:
    """编号审查第一遍：全文提编号清单，返回 [{title, numbers}]；超时/异常/解析失败一律按空表处理（调用方空表短路）。

    手法与 _scan_terminology 同款（regex 提取 + json.loads + 防御过滤）；I2：首个 yield 之前的
    模型调用必须 wait_for + except，否则 provider 挂起会变成 200 + 零事件 + 永久悬挂。
    """
    try:
        resp = await asyncio.wait_for(model.ainvoke(_NUMBERING_SCAN_PROMPT.format(doc=doc)), timeout=SUMMARY_TIMEOUT_SECONDS)
    except Exception:
        logger.warning("docmgr numbering scan failed, treated as empty", exc_info=True)
        return []
    m = re.search(r"\[[\s\S]*\]", _extract_ai_response_text(resp.content))
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: list[dict] = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and isinstance(item.get("title"), str) and isinstance(item.get("numbers"), list):
            numbers = [str(v) for v in item["numbers"] if isinstance(v, (str, int)) and str(v).strip()]
            if numbers:
                out.append({"title": item["title"], "numbers": numbers})
    return out


def _parse_findings(text: str) -> list | None:
    """模型输出 → JSON 数组（复用 _scan_terminology 手法：regex 提取 + json.loads）；解析失败/非 list 返回 None（调用方按节失败处理）。"""
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _normalize_finding(item, review_type: str, section_index: int, n: int, section_title: str) -> dict | None:
    """契约过滤（EAI-CUSTOM 全文操作 M2，contracts/docmgr_findings.v1.json）：

    - 缺任一 required 字段（severity/anchor/excerpt/problem/suggestion；id 服务端生成不要求模型给）→ 丢整条 + warning
    - severity 白名单外降级 warn
    - excerpt 截断到 120 字
    - anchor 服务端权威覆写为节标题（契约定义 anchor=节标题；模型回显不可靠，覆写保证 scrollToAnchor 与 fix_op 同源）
    - fixed_section 非空字符串 → 附 fix_op（replace_section；content 走 _strip_markdown_fence 兜 fence 包裹）
    - 返回 None = 该条被丢弃
    """
    if not isinstance(item, dict):
        logger.warning("docmgr ai_review finding dropped: not a dict (section %s #%s)", section_index, n)
        return None
    missing = [k for k in ("severity", "anchor", "excerpt", "problem", "suggestion") if not isinstance(item.get(k), str)]
    if missing:
        logger.warning("docmgr ai_review finding dropped: missing %s (section %s #%s)", missing, section_index, n)
        return None
    severity = item["severity"] if item["severity"] in _REVIEW_SEVERITIES else "warn"
    finding: dict = {
        "id": f"{review_type}-{section_index}-{n}",
        "severity": severity,
        "anchor": section_title,
        "excerpt": item["excerpt"][:_REVIEW_EXCERPT_MAX],
        "problem": item["problem"],
        "suggestion": item["suggestion"],
    }
    fixed = item.get("fixed_section")
    if isinstance(fixed, str) and fixed.strip():
        # EAI-CUSTOM (全文操作 M2): 整节修正 → DocOperation 复用（修复 = applyOperations 原样回灌，spec §5）
        finding["fix_op"] = {"op": "replace_section", "anchor": section_title, "content": _strip_markdown_fence(fixed)}
    return finding


@router.post("/ai/review")
async def ai_review(
    request: AIReviewRequest,
    current_user: CurrentUser = Depends(_doc_perm),  # EAI-CUSTOM: 权限门同 transform
):
    if request.review_type not in _ALL_REVIEW_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown review_type: {request.review_type}. Must be one of: {sorted(_ALL_REVIEW_TYPES)}")
    if request.review_type == "custom" and not (request.instruction or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="custom 审查必须提供 instruction")
    if len(request.content) > MAX_CONTENT_CHARS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"文档过长（>{MAX_CONTENT_CHARS} 字符），请分段处理")
    model = create_chat_model(name=request.model_name, thinking_enabled=False, model_overrides={"max_tokens": 8192})
    sections = split_sections(request.content)
    if len(sections) > MAX_SECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"分节数超过上限 {MAX_SECTIONS}，请分段处理")
    logger.info(
        "docmgr ai_review user=%s type=%s thread=%s rel=%s sections=%d chars=%d",
        getattr(current_user, "id", "?"),
        request.review_type,
        request.thread_id,
        request.rel_path,
        len(sections),
        len(request.content),
    )

    async def generate() -> AsyncIterator[str]:
        failed: list[int] = []
        skipped: list[int] = []
        summary = {"error": 0, "warn": 0, "info": 0}
        # EAI-CUSTOM (全文操作 M2): 两遍法先全文扫描建全局对照表；空表短路 done total=0
        # （同 transform terminology 短路先例——逐节空转审查是无意义 N 次模型调用）
        context_block = ""
        if request.review_type == "consistency":
            table = await _scan_terminology(model, request.content)
            if not table:
                yield _ndjson({"type": "done", "total": 0, "failed": [], "skipped": [], "message": "未发现术语变体"})
                return
            context_block = _terminology_block(table)
        elif request.review_type == "numbering":
            numbering = await _scan_numbering(model, request.content)
            if not numbering:
                yield _ndjson({"type": "done", "total": 0, "failed": [], "skipped": [], "message": "未提取到编号清单"})
                return
            context_block = _numbering_block(numbering)
        rules = _REVIEW_RULES.get(request.review_type) or f"按用户指令审查本节，只报告指令关注的问题。用户指令：{request.instruction}"
        fix_hint = _REVIEW_FIX_HINT if request.review_type in ("consistency", "units") else ""
        for i, sec in enumerate(sections):
            start_ev: dict = {"type": "section_start", "index": i, "total": len(sections), "title": sec["title"] or f"第 {i + 1} 节"}
            if sec["structured"]:
                start_ev["skipped"] = True
                skipped.append(i)
                yield _ndjson(start_ev)
                continue
            yield _ndjson(start_ev)
            if not sec["title"]:
                failed.append(i)
                yield _ndjson({"type": "section_error", "index": i, "message": "文档无标题（全文单节），无法按节定位；请先给文档加标题，或改用对话模式"})
                continue
            prompt = _REVIEW_SECTION_PROMPT.format(
                focus=_REVIEW_FOCUS[request.review_type],
                rules=rules,
                context_block=context_block,
                fix_hint=fix_hint,
                title=sec["title"],
                section=sec["content"],
            )
            try:
                # I2 铁律：每个模型调用 wait_for + except，provider 挂起不得变成 200+零事件悬挂
                resp = await asyncio.wait_for(model.ainvoke(prompt), timeout=SECTION_TIMEOUT_SECONDS)
                items = _parse_findings(_extract_ai_response_text(resp.content))
            except Exception as e:
                failed.append(i)
                logger.warning("docmgr ai_review section %s failed: %s", i, e, exc_info=True)
                yield _ndjson({"type": "section_error", "index": i, "message": "本节审查失败，可稍后重试"})
                continue
            if items is None:
                failed.append(i)
                logger.warning("docmgr ai_review section %s findings not parseable", i)
                yield _ndjson({"type": "section_error", "index": i, "message": "本节审查输出无法解析，可稍后重试"})
                continue
            for n, item in enumerate(items):
                finding = _normalize_finding(item, request.review_type, i, n, sec["title"])
                if finding is None:
                    continue
                summary[finding["severity"]] += 1
                yield _ndjson({"type": "finding", "index": i, "finding": finding})
        # EAI-CUSTOM (全文操作 M2): summary 按 severity 实际发出（过滤后）条数计；total = 全量节数
        yield _ndjson({"type": "done", "total": len(sections), "failed": failed, "skipped": skipped, "summary": dict(summary)})

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
