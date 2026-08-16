#!/usr/bin/env python3
"""score_simulate.py — 投标方案编写技能·阶段5 模拟评分(确定性骨架, 无 LLM)。

规格: docs/superpowers/specs/2026-08-16-bid-proposal-writing-skill-design.md
「阶段5 模拟评分」+ D2(重灌锚点契约)/D6(匹配器硬化四规则)/D7(状态一致性三防线)。
主观项 LLM 评审循环由 Agent 在上下文内执行(references/scoring_prompt.md 纪律)——
本脚本只组装证据包(assemble-evidence)并消费其评分结果(aggregate), 绝不调用 LLM。

用法(四个子命令):
    python score_simulate.py reingest --source <回传.md> --state-dir <dir> [--threshold 0.6] [--volume commercial|technical|both]
    python score_simulate.py assemble-evidence --state-dir <dir>
    python score_simulate.py aggregate --scores <主观评分JSON> --state-dir <dir>
    python score_simulate.py report --state-dir <dir>

重灌数据流(D2 锚点契约, 实现期落此):

    回传.docx ──uploads 自动转换──> 回传.md (--source 显式指定, 防多版并存灌旧版)
      │
      ├─ 商务卷: 标题链匹配 structure.json 树路径(章节标题=招标文件规定结构,
      │          改标题本身即形式违规 → 标题天然稳定, 无需额外标记)
      │          匹配前归一化: 全角→半角, 去全部空白, 去前导编号(D6②)
      │          同一标题链多命中(目录与正文同名)→ 不取首个, 整项进异常区(D6①)
      │
      ├─ 技术卷: clause_id 匹配 clauses.json(条目标题内嵌, build_output 渲染时埋定;
      │          边界感知: id 尾不得跟数字, "ZB-C-1"不算"ZB-C-12"的出现)
      │          clause_id 重复出现(按含 cid 的条目标题数判; 正文交叉引用合法,
      │          Word 修订模式重复标题文本才计)→ 异常区(D6③)
      │
      ├─ 未匹配槽/条款 → needs_human_verify(报告异常区, 不计 0 分不静默)
      │
      ├─ 命中率 < 阈值(默认 0.6, --threshold)→ 整体降级"人核覆盖率清单",
      │   不做部分计分, 不灌半套状态(D6④)
      │
      ├─ --volume commercial|technical = 单卷回传限定: 分母与锚点遍历只含该卷——
      │   另一卷锚点不计 hit_rate、不产 unmatched/duplicate 异常、权威态不动;
      │   卷内 D6 语义不变(该卷内多命中/重复id/未命中照旧全量异常)。
      │   默认 both = 双卷拼接文件按全量锚点(每卷单独回传必须显式 --volume,
      │   否则另一卷分母必把单卷文件拖进降级死路)
      │
      └─ 重灌后权威态(clauses.json response_status)──> aggregate:
            objective 项 = 确定性状态汇总(是汇总不是验证, 可信度取决于状态维护)
            subjective 项 = 消费 Agent 评分 JSON(evidence_pack 供其 grep 检索)
            price 项 = 标"无法模拟"(依赖竞对报价, 现库为 mock)
         ──> report: 评分模拟报告 version_N.md(version++ 留痕不覆盖历史)

重灌更新权威态的确定性映射(技术卷活条款: category=technical 且未 superseded/voided,
与 build_output 技术卷条目同口径):
    命中+条目有正文 → response_status=compliant(已响应)
    命中+空条目     → response_status=unassigned(未填写)
    已登记 deviation 的人裁不被静默覆盖 → 保留; 条目带偏离声明正文=自洽不报,
    仅偏差与回传事实矛盾(登记 deviation 但条目空)→ deviation_conflict 异常待人核
    未命中/重复 id  → 不动权威态, 仅记 needs_human_verify / duplicate_id
    structure.json 永不被改写: fill_status 等派生字段现算不落盘(D7)

objective 确定性汇总口径(如实声明边界): 不解析评分办法原文的分档算术——"每项扣5分"
之类的算式无法确定性解析, 按 已响应条款占比 折算, 分档算术由人工对齐; 报告逐项
列出条款状态供核对:
    score = round(max_score × compliant 数 / 关联活条款数, 2)
    关联条款含 needs_human_verify / duplicate_id(重灌不可信)→ 该项 needs_human,
    score=None——既不计 0 分也不静默通过(D6)
    关联条款为空 / 无活条款 → objective_no_linkage 异常, 无法确定性汇总

报告(version++ 留痕, 历史版本供二期评分校准闭环消费):
    逐项 得分/满分/理由/失分原因 + 改进建议清单(按 失分值×可改性 降序;
    可改性: 补内容可找回=1.0 / 偏离条款需实质变更或先人核=0.5 / price 不入清单)
    + 主观分一律标"模拟参考值" + 异常区(重灌失败/多命中/重复 id/降级清单/评审异常)

产物(全部落 --state-dir, 临时文件+os.replace 原子写盘):
    reingest_result.json   重灌事实(逐锚点 match/fill + 异常区)
    evidence_pack.json     逐 rubric 项证据包(grep 证据行, 供 Agent 主观评审)
    aggregate_result.json  汇总结果(逐项得分/状态 + totals + 异常)
    评分报告/version_N.md  评分模拟报告(或降级模式的人核覆盖率清单)

脚本纪律: 纯 Python 3.12; stdlib only; 不调用 LLM; 不 import app.*/deerflow.*;
    派生字段现算不落盘(D7); 产物不含时间戳 → 同输入重跑幂等。

退出码:
    0 = 干净完成(--help 亦为 0)
    1 = 用法/文件错误(状态文件缺失/不可解析/回传稿缺失/response_status 枚举非法/
        Σ 不一致中止/降级拒绝计分; argparse 用法错误统一改道 1——2 留给 ingest 的 OCR 分流语义)
    3 = 完成但有异常项(重灌多命中/重复 id/未匹配/孤儿标题/降级/证据源不可达/评审记录违规/未核条款等)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

# --- 退出码约定 -----------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ANOMALY = 3

# --- 契约常量(与其他脚本同款; 沙箱无 jsonschema, 内联同子集) ----------------------
RESPONSE_STATUSES = ("unassigned", "draft", "pending_confirm", "compliant", "deviation")
# 已响应口径(对齐 build_output: 已响应=compliant+deviation; 汇总满分口径=仅 compliant)
DEFAULT_THRESHOLD = 0.6
# 证据包单项证据行上限(防 Agent 上下文被打爆——SKILL.md 上下文纪律)
EVIDENCE_LINES_CAP = 20
# 单条证据行截断长度(证据是引用不是全文)
EVIDENCE_TEXT_CAP = 200

REPORT_DIR_NAME = "评分报告"
_REPORT_VERSION_RE = re.compile(r"^version_(\d+)\.md$")

# 条款复合 ID(与 references/clauses.schema.json·merge_addenda.CLAUSE_ID_RE 同一 pattern
# ^[A-Z]{2,4}-C-\d{1,6}$; 此处不加 ^$ 锚做标题内嵌检测——3-4 位文件代号/非 3 位序号同为
# 合法 id)。尾部 (?!\d) = 数字边界: 合法 id 域内 "ZB-C-1" 是 "ZB-C-12" 的前缀, 无边界
# 匹配会让 7 位超长数字串的前 6 位冒充合法 id 豁免镜像检查(见 _title_embeds_clause)。
CLAUSE_ID_RE = re.compile(r"[A-Z]{2,4}-C-\d{1,6}(?!\d)")

# 评审输出记录契约字段(references/scoring_prompt.md「评审输出记录」)
RECORD_FIELDS = ("rubric_id", "score", "max_score", "rationale", "evidence_quote", "missing_points", "improvement")

SCORE_TYPE_LABELS = {"objective": "客观·确定性汇总", "subjective": "主观·模拟参考值", "price": "报价·无法模拟"}
STATUS_LABELS = {"unassigned": "未分配", "draft": "草稿", "pending_confirm": "待确认", "compliant": "已响应", "deviation": "偏离"}

# 可改性系数(改进建议排序权重; 报告口径, 确定性规则见模块 docstring)
MODIFIABLE_CONTENT = 1.0  # 补写内容/补评审即可找回
MODIFIABLE_HARD = 0.5  # 偏离条款需实质变更, 或先人工核验才能定改法


class ScoreSimulateError(Exception):
    """用法/文件/中止错误 → 退出码 1。"""


# =============================================================================
# 基础件: JSON 装载 / 原子写盘 / 派生小函数
# =============================================================================


def _load_json_file(path: Path, what: str):
    """装载 UTF-8 JSON 文件; 缺失/不可解析 → ScoreSimulateError(退出码 1), 绝不静默。"""
    if not path.is_file():
        raise ScoreSimulateError(f"{what} 不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ScoreSimulateError(f"{what} 不可读/不可解析(需 UTF-8; 疑似截断或编码错): {path}: {exc}") from exc


def _load_optional_json(path: Path):
    """可选产物装载: 缺失返回 None(会话内填写态=尚未重灌/尚未汇总), 损坏仍报错。"""
    if not path.exists():
        return None
    return _load_json_file(path, path.name)


def _load_clauses(state_dir: Path) -> list[dict]:
    """装载 clauses.json + response_status 枚举复检(build_output.load_clauses 同款防线,
    RESPONSE_STATUSES 落地使用而非死常量)——枚举外值(手改错字)会在 objective 汇总中被
    静默按'未响应'计, 装载期拒绝(退出码 1)。"""
    path = state_dir / "clauses.json"
    clauses = _load_json_file(path, "clauses.json")
    if not isinstance(clauses, list) or not all(isinstance(c, dict) for c in clauses):
        raise ScoreSimulateError(f"clauses.json 结构异常(应为对象数组), 拒绝评分: {path}")
    for index, clause in enumerate(clauses):
        if clause.get("response_status") not in RESPONSE_STATUSES:
            raise ScoreSimulateError(f"clauses.json items[{index}]({clause.get('clause_id')}) response_status 枚举非法 {clause.get('response_status')!r}(合法: {list(RESPONSE_STATUSES)}): {path}")
    return clauses


def atomic_write_text(path: str | Path, text: str) -> None:
    """原子写盘: 临时文件 + os.replace(D7, 防中断留半截文件)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        # 成功路径 os.replace 后 tmp 已不存在; 异常路径清理残留。清理失败只吞掉——
        # 不得掩盖触发本 finally 的原始异常(Windows 文件占用场景)。
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def atomic_write_json(path: str | Path, data) -> None:
    """JSON 原子写盘(键序=构造序, 无时间戳 → 同输入重跑字节级幂等)。"""
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _is_active(clause: dict) -> bool:
    """活条款 = 未 superseded 且未 voided(与 build_output/merge_addenda 同口径)。"""
    return clause.get("superseded_by") is None and not clause.get("voided")


def _title_embeds_clause(cid: str, title: str) -> bool:
    """D2/D6③ 边界感知的条目标题内嵌检测: cid 后不得紧跟数字——合法 id 域
    [A-Z]{2,4}-C-\\d{1,6} 内 "ZB-C-1" 是 "ZB-C-12" 的无边界子串, 会把各自唯一出现的
    条目标题误判成重复(occurrences=2, 连带 权威态拒更/命中率虚降/D6④ 误降级); 反向则
    会让无条目的短 id 静默认领长 id 条目的正文(灌错)。"""
    return re.search(re.escape(cid) + r"(?!\d)", title) is not None


# =============================================================================
# D6② 匹配前文本归一化: 全角→半角 / 去空白 / 去前导编号 / casefold
# =============================================================================


def _to_halfwidth(text: str) -> str:
    """全角 ASCII(U+FF01-FF5E)→半角; 全角空格(U+3000)→半角空格。"""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif ch == "　":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


# 前导编号三类: 第X章/节、多级数字(2.1)、中文数字(一、); 分隔符可为空(空白已先去掉,
# "1、投标函"与"1 技术方案"必须归一为同一形态)。两侧同规则处理, 匹配口径保持一致。
_NUMBERING_RES = (
    re.compile(r"^第[0-9一二三四五六七八九十百]+[章节篇卷]"),
    re.compile(r"^[0-9]+(?:\.[0-9]+)*"),
    re.compile(r"^[一二三四五六七八九十百]+[、.．]?"),
)
# 编号剥离后残留的前导分隔符(、．（）等)
_LEADING_SEP_RE = re.compile(r"^[、.．,，:：;；()（）\-—]+")


def normalize_title(text: str) -> str:
    """标题归一化(D6②): 全角→半角 → 去全部空白 → 去前导编号(循环至稳, ≤4 轮) → casefold。

    防 Word 自动编号/全半角/样式空格差异导致精确匹配雪崩进人核洪泛。注意: 真以数字
    开头的标题(如"100%本地化")会被两侧同规则剥离编号——匹配方向不受影响; 若因此产生
    同链撞名, 会以 multi_hit 进异常区而非静默(D6①)。
    """
    s = re.sub(r"\s+", "", _to_halfwidth(text))
    for _ in range(4):
        stripped = s
        for pattern in _NUMBERING_RES:
            new = pattern.sub("", stripped, count=1)
            if new != stripped:
                stripped = new
                break
        stripped = _LEADING_SEP_RE.sub("", stripped)
        if stripped == s:
            break
        s = stripped
    return s.casefold()


# build_output 两处卷末合成标题(M2): "## {N} 未挂接格式槽的技术条款(清单驱动)" 与
# "## 扫描件清单(图片槽汇总)"——不在 structure.json 镜像里也不嵌 clause_id, 却是阶段4
# 渲染的法定产物, 阶段4→5 原样往返不豁免会每卷必产 unmatched_heading 噪音。豁免口径=
# 归一化全词等值(编号被 normalize_title 剥离, "## 4 未挂接…"同名豁免); 手改标题不再
# 全词等值, 仍走镜像检查报异常待人核。
SYNTHETIC_HEADING_NORMS = frozenset({normalize_title("未挂接格式槽的技术条款(清单驱动)"), normalize_title("扫描件清单(图片槽汇总)")})


# =============================================================================
# 回传 md 解析: ATX 标题树 + 节正文
# =============================================================================


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def parse_md_headings(text: str) -> list[dict]:
    """解析 ATX 标题树; 每标题带 level/title/norm/line(1-based)/chain(归一化祖先链含自身)。

    chain 是 D2 商务卷锚点的匹配单位: structure.json 树路径段链 ↔ 标题祖先链全等。
    """
    headings: list[dict] = []
    stack: list[tuple[int, str]] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        matched = _HEADING_RE.match(raw)
        if not matched:
            continue
        level = len(matched.group(1))
        title = matched.group(2).strip()
        norm = normalize_title(title)
        while stack and stack[-1][0] >= level:
            stack.pop()
        chain = [item_norm for _, item_norm in stack] + [norm]
        stack.append((level, norm))
        headings.append({"level": level, "title": title, "norm": norm, "chain": chain, "line": idx})
    return headings


def _section_body(text_lines: list[str], headings: list[dict], heading: dict) -> list[str]:
    """标题节正文: 到下一个 level≤自身 的标题行前(子节内容归子节, 不重复计入)。"""
    start = heading["line"]
    end = len(text_lines)
    for nxt in headings:
        if nxt["level"] <= heading["level"] and nxt["line"] > heading["line"]:
            end = min(end, nxt["line"] - 1)
            break
    return text_lines[start:end]  # text_lines 0-based; 正文从标题行后一行开始


# =============================================================================
# D7 第一防线: 装载三件套时校验 linked_clause_ids 存在且未 superseded/voided
# =============================================================================


def validate_foreign_keys(clauses: list[dict], structure: list[dict], rubric_items: list[dict]) -> list[dict]:
    """悬挂外键 → 异常项, 不静默(D7; extract/merge 同款防线在重灌/汇总处复检)。"""
    by_id = {c.get("clause_id"): c for c in clauses}
    anomalies: list[dict] = []
    for node in structure:
        for cid in node.get("linked_clause_ids") or []:
            clause = by_id.get(cid)
            if clause is None:
                anomalies.append({"kind": "dangling_fk", "message": f"structure 节点 {node.get('node_id')} linked_clause_ids 悬挂: {cid} 不在 clauses.json——先修链再重灌"})
            elif not _is_active(clause):
                anomalies.append({"kind": "dangling_fk", "message": f"structure 节点 {node.get('node_id')} 链接已失效条款 {cid}(superseded/voided)——请改链到替代条款"})
    for item in rubric_items:
        for cid in item.get("linked_clause_ids") or []:
            clause = by_id.get(cid)
            if clause is None:
                anomalies.append({"kind": "dangling_fk", "message": f"rubric 项 {item.get('rubric_id')} linked_clause_ids 悬挂: {cid} 不在 clauses.json"})
            elif not _is_active(clause):
                anomalies.append({"kind": "dangling_fk", "message": f"rubric 项 {item.get('rubric_id')} 链接已失效条款 {cid}(superseded/voided)——评分口径应指向替代条款"})
    return anomalies


# =============================================================================
# 子命令 1: reingest — 重灌(D2 锚点契约 + D6 匹配器硬化)
# =============================================================================


def _slot_fill(slot_type: str, has_content: bool, has_table: bool) -> tuple[str, str]:
    """商务卷槽位 fill 事实(现算不落盘, D7): 与 build_output.derive_fill_status 分型一致——
    image/format_check/table 天然含人核成分, 只记录事实不做确定性判定。"""
    if slot_type == "group":
        return "not_applicable", "结构组——纯章节容器, 无填写语义"
    if slot_type == "image":
        return "needs_human_verify", f"图片槽——扫描件人工核验(标题下正文{'已有' if has_content else '无'}内容; 图片不经 md 链路插入)"
    if slot_type == "table":
        fact = "检测到表格行" if has_table else "未检测到表格"
        return "needs_human_verify", f"表格槽[待人工复刻]——{fact}, 合并单元格/列宽需人工核验"
    if slot_type == "format_check":
        return "needs_human_verify", "格式核验槽(签字/盖章/份数/页码)——人核项, 不做确定性判定"
    if has_content:
        return "filled", "文字槽已有正文"
    return "unfilled", "文字槽无正文"


def run_reingest(source: Path, state_dir: Path, threshold: float, volume: str = "both") -> int:
    """回传稿确定性重灌: 锚点匹配 → 权威态更新(降级则不灌) → reingest_result.json。

    volume: both=默认(双卷拼接文件按全量锚点, 现行为); commercial/technical=单卷回传
    限定——分母与锚点遍历只含该卷, 另一卷不计 hit_rate/不产 unmatched 异常/权威态
    不动(R4: 每卷单独成文/单独回传是主流程, 若分母恒含另一卷, 单卷完美回传也必被
    拖进 D6④ 降级死路)。"""
    if not source.is_file():
        raise ScoreSimulateError(f"回传稿不存在: {source}(重灌输入必须显式指定, D2——防多版回传并存时灌了旧版)")
    try:
        # utf-8-sig: 回传 md 带 UTF-8 BOM 时剥掉, 防首标题失配(BOM 对 # 前缀的 ATX 匹配是硬伤)
        text = source.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError) as exc:
        raise ScoreSimulateError(f"回传稿不可读(需 UTF-8 md; docx 先经 uploads 自动转换): {source}: {exc}") from exc

    clauses = _load_clauses(state_dir)
    structure = _load_json_file(state_dir / "structure.json", "structure.json")
    rubric = _load_json_file(state_dir / "rubric.json", "rubric.json")
    anomalies = validate_foreign_keys(clauses, structure, rubric.get("items") or [])

    text_lines = text.splitlines()
    headings = parse_md_headings(text)

    # --- 商务卷: 标题链匹配 structure.json 树路径(D2; 多命中不取首个 D6①) ----------
    # --volume 限定单卷时只遍历该卷(R4): 另一卷锚点不计 hit_rate/不产 unmatched
    # 异常/权威态不动; 卷内 D6 语义(多命中/未命中)不变。
    commercial_nodes = [n for n in structure if n.get("volume") == "commercial"]
    node_records: list[dict] = []
    if volume in ("commercial", "both"):
        for node in commercial_nodes:
            segments = [normalize_title(seg) for seg in node.get("path", "").split("/")]
            candidates = [h for h in headings if h["chain"] == segments]
            base = {"node_id": node.get("node_id"), "volume": "commercial", "path": node.get("path"), "slot_type": node.get("slot_type")}
            if len(candidates) == 1:
                heading = candidates[0]
                body = _section_body(text_lines, headings, heading)
                has_content = any(ln.strip() for ln in body)
                has_table = any(ln.lstrip().startswith("|") for ln in body)
                fill, reason = _slot_fill(node.get("slot_type") or "", has_content, has_table)
                node_records.append({**base, "match": "matched", "hit_line": heading["line"], "fill": fill, "fill_reason": reason})
            elif len(candidates) > 1:
                hit_lines = [h["line"] for h in candidates]
                anomalies.append(
                    {
                        "kind": "heading_multi_hit",
                        "node_id": node.get("node_id"),
                        "path": node.get("path"),
                        "hit_lines": hit_lines,
                        "message": f"标题链「{node.get('path')}」命中 {len(candidates)} 处(行 {hit_lines})——不取首个, 整项进异常区待人核(防静默灌错)",
                    }
                )
                node_records.append({**base, "match": "multi_hit", "hit_line": None, "fill": None, "fill_reason": "多命中——人工核验取哪一处"})
            else:
                anomalies.append(
                    {"kind": "node_anchor_unmatched", "node_id": node.get("node_id"), "path": node.get("path"), "message": f"structure 节点 {node.get('node_id')} 标题链「{node.get('path')}」回传稿未命中——needs_human_verify, 不计 0 不静默"}
                )
                node_records.append({**base, "match": "needs_human_verify", "hit_line": None, "fill": None, "fill_reason": "标题链未命中——人工核验(改标题本身即形式违规, 疑似漏交该节)"})

    # --- 技术卷: clause_id 匹配条目标题(D2; 重复出现进异常区 D6③) ------------------
    tech_clauses = [c for c in clauses if _is_active(c) and c.get("category") == "technical"]
    clause_records: list[dict] = []
    pending_updates: list[tuple[dict, str]] = []
    if volume in ("technical", "both"):
        for clause in tech_clauses:
            cid = clause.get("clause_id")
            # D6③ 计数口径 = 含 cid 的条目标题数(D2 锚点载体=条目标题内嵌 clause_id)——
            # 条目正文合法交叉引用自身条款 id(如"满足ZB-C-001要求")不算重复, 不拦命中。
            # 边界感知(_title_embeds_clause): "ZB-C-1" 不是 "ZB-C-12" 标题的出现(T7-1 前缀污染)。
            entry_headings = [h for h in headings if _title_embeds_clause(cid, h["title"])]
            occurrences = len(entry_headings)
            heading_lines = [h["line"] for h in entry_headings]
            # 正文出现次数(仅信息披露, 不参与判重); 同边界口径统计, 防更长 id 的出现被算作本 id 的正文出现
            body_mentions = len(re.findall(re.escape(cid) + r"(?!\d)", text)) - occurrences
            before = clause.get("response_status")
            record = {"clause_id": cid, "occurrences": occurrences, "hit_line": None, "filled": None, "response_status_before": before, "response_status_after": before, "updated": False}
            if occurrences == 0:
                where = "仅出现在正文非标题处(条目标题未嵌 clause_id, D2 契约破坏)" if body_mentions else "条目标题未在回传稿出现"
                anomalies.append({"kind": "clause_anchor_unmatched", "clause_id": cid, "message": f"条款 {cid} {where}——needs_human_verify, 权威态不动, 不计 0 分不静默"})
                record["match"] = "needs_human_verify"
                clause_records.append(record)
                continue
            if occurrences >= 2:
                anomalies.append(
                    {
                        "kind": "duplicate_clause_id",
                        "clause_id": cid,
                        "occurrences": occurrences,
                        "lines": heading_lines,
                        "message": f"clause_id {cid} 在回传稿 {occurrences} 个条目标题重复出现(标题行 {heading_lines})——疑似 Word 修订模式 docx→md 重复文本, 进异常区待人核, 不重灌(正文交叉引用不计重复)",
                    }
                )
                record["match"] = "duplicate_id"
                clause_records.append(record)
                continue
            heading = entry_headings[0]
            body = _section_body(text_lines, headings, heading)
            filled = any(ln.strip() for ln in body)
            record.update({"match": "matched", "hit_line": heading["line"], "filled": filled})
            if before == "deviation":
                # 已登记偏离是人工裁决, 确定性重灌不得静默覆盖。条目带偏离声明正文=自洽,
                # 不制造异常噪音; 仅偏差与回传事实矛盾(登记 deviation 但条目空, 偏离声明
                # 无处对账)时进异常区待人核。
                record["response_status_after"] = "deviation"
                if not filled:
                    anomalies.append({"kind": "deviation_conflict", "clause_id": cid, "message": f"条款 {cid} 已登记 deviation, 但回传条目为空——偏离声明未见正文, 与人工裁决矛盾, 保留 deviation 待人核"})
            else:
                after = "compliant" if filled else "unassigned"
                record["response_status_after"] = after
                if after != before:
                    record["updated"] = True
                    pending_updates.append((clause, after))
            clause_records.append(record)

    # --- 镜像外标题(回传稿侧孤儿): 结构只镜像不自创, 不静默 ------------------------
    mirror_titles = {normalize_title(seg) for node in structure for seg in node.get("path", "").split("/")}
    known_clause_ids = {c.get("clause_id") for c in clauses}
    for heading in headings:
        embedded_ids = CLAUSE_ID_RE.findall(heading["title"])
        if embedded_ids:
            # 条目标题(嵌已知 clause_id)由技术卷锚点管辖, 豁免镜像检查; 但内嵌 id 不在
            # clauses.json(孤儿条目标题, 疑似手改回传稿)不得静默豁免——保留 unmatched
            # 异常待人核, 不因豁免而漏报。
            unknown = sorted({cid for cid in embedded_ids if cid not in known_clause_ids})
            if unknown:
                orphan_message = f"回传稿标题「{heading['title']}」(行 {heading['line']})内嵌未知 clause_id {unknown}——不在 clauses.json(孤儿条目标题, 疑似手改回传稿), 需人工核对"
                anomalies.append({"kind": "unmatched_heading", "line": heading["line"], "heading": heading["title"], "message": orphan_message})
            continue
        if heading["norm"] in SYNTHETIC_HEADING_NORMS:
            # build_output 卷末合成标题(孤儿条款节/扫描件清单, M2)——阶段4→5 法定往返产物,
            # 与条目标题 clause_id 豁免同层; 手改后的标题不再全词等值, 仍会被镜像检查拦下。
            continue
        if heading["norm"] not in mirror_titles:
            anomalies.append({"kind": "unmatched_heading", "line": heading["line"], "heading": heading["title"], "message": f"回传稿标题「{heading['title']}」(行 {heading['line']})不在 structure.json 镜像——结构只镜像不自创, 需人工核对"})

    # --- 命中率与整体降级(D6④) ---------------------------------------------------
    # 分母按 --volume 圈定(R4): 单卷回传只以该卷锚点为分母, 不被另一卷拖进降级死路。
    total_anchors = (len(commercial_nodes) if volume in ("commercial", "both") else 0) + (len(tech_clauses) if volume in ("technical", "both") else 0)
    if total_anchors == 0:
        raise ScoreSimulateError(f"无可重灌锚点(--volume {volume}: 商务卷 {len(commercial_nodes)} 槽位 + 活技术条款 {len(tech_clauses)})——先完成阶段2/4 再评分")
    matched = sum(1 for r in node_records if r["match"] == "matched") + sum(1 for r in clause_records if r["match"] == "matched")
    hit_rate = matched / total_anchors  # 不四舍五入: 阈值边界比较与摘要精度不受截断影响
    degraded = hit_rate < threshold
    updated_clauses = 0
    if degraded:
        # D6④: 匹配不可靠 → 整体退回人工模式, 不灌半套状态——权威态原样。
        for record in clause_records:
            record["updated"] = False
            record["response_status_after"] = record["response_status_before"]
        anomalies.append(
            {
                "kind": "reingest_degraded",
                "hit_rate": hit_rate,
                "matched": matched,
                "total": total_anchors,
                "threshold": threshold,
                "message": f"重灌命中率 {matched}/{total_anchors}={hit_rate} 低于阈值 {threshold}——整体降级为'人核覆盖率清单', 不做部分计分, 不灌半套状态(D6④)",
            }
        )
    else:
        for clause, after in pending_updates:
            clause["response_status"] = after
        updated_clauses = len(pending_updates)
        if pending_updates:
            atomic_write_json(state_dir / "clauses.json", clauses)

    anchors = {
        "total": total_anchors,
        "matched": matched,
        "needs_human_verify": sum(1 for r in node_records + clause_records if r["match"] == "needs_human_verify"),
        "multi_hit": sum(1 for r in node_records if r["match"] == "multi_hit"),
        "duplicate_id": sum(1 for r in clause_records if r["match"] == "duplicate_id"),
    }
    result = {"source": str(source), "threshold": threshold, "volume": volume, "hit_rate": hit_rate, "degraded": degraded, "anchors": anchors, "nodes": node_records, "clauses": clause_records, "anomalies": anomalies}
    atomic_write_json(state_dir / "reingest_result.json", result)

    summary = {"command": "reingest", "source": str(source), "threshold": threshold, "volume": volume, "hit_rate": hit_rate, "anchors": anchors, "updated_clauses": updated_clauses, "degraded": degraded, "anomalies": anomalies}
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK if not anomalies else EXIT_ANOMALY


# =============================================================================
# 子命令 2: assemble-evidence — 逐 rubric 项组装确定性证据包(供 Agent 主观评审)
# =============================================================================


def run_assemble_evidence(state_dir: Path) -> int:
    """evidence_pack.json: 每项 rubric + 关联条款 + 回传稿 grep 证据行(无 LLM, 纯检索)。"""
    rubric = _load_json_file(state_dir / "rubric.json", "rubric.json")
    clauses = _load_clauses(state_dir)
    reingest = _load_optional_json(state_dir / "reingest_result.json")
    if reingest and reingest.get("degraded"):
        raise ScoreSimulateError("重灌已降级(命中率低于阈值)——人核覆盖率清单模式不做评审循环(D6④); 先人工核验后重跑 reingest")

    source_path = reingest.get("source") if reingest else None
    source_lines: list[str] = []
    # T7-2: 重灌发生过(非降级)但 source 不可达(文件被移走/相对路径跨 cwd 调用)≠ 会话内
    # 填写态——两态混写会让"评审对象=会话内骨架"成为假陈述, 且评分纪律"无证据按空缺
    # 计分"会把路径失效这一技术原因误当内容空缺压主观分 → 进异常区, note 如实分立。
    source_unreachable = bool(reingest) and not (source_path and Path(source_path).is_file())
    if source_path and not source_unreachable:
        try:
            # utf-8-sig 同 reingest: BOM 剥除, 证据行号与重灌口径一致
            source_lines = Path(source_path).read_text(encoding="utf-8-sig").splitlines()
        except (UnicodeDecodeError, OSError) as exc:
            raise ScoreSimulateError(f"回传稿不可读: {source_path}: {exc}") from exc

    by_id = {c.get("clause_id"): c for c in clauses}
    items: list[dict] = []
    total_lines = 0
    for item in rubric.get("items") or []:
        linked = [by_id[cid] for cid in item.get("linked_clause_ids") or [] if cid in by_id]
        points = [p for c in linked for p in ((c.get("response_skeleton") or {}).get("points") or []) if p]
        # 检索键: clause_id(锚点命中行) + 条目响应要点 + 评分项名(逐项独立评审的定位线索)
        keys = {cid for cid in item.get("linked_clause_ids") or []} | {item.get("item") or ""} | set(points)
        keys.discard("")
        evidence = [{"line": i, "text": ln.strip()[:EVIDENCE_TEXT_CAP]} for i, ln in enumerate(source_lines, start=1) if any(k in ln for k in keys)][:EVIDENCE_LINES_CAP]
        total_lines += len(evidence)
        score_type = item.get("score_type")
        if score_type == "subjective":
            note = "逐项独立评审: 评分办法原文(scoring_method)为尺, 证据 grep 定位——无证据按空缺计分(scoring_prompt.md 纪律)"
        elif score_type == "objective":
            note = "objective 项由 aggregate 确定性汇总, 本包证据仅供人工核对条款状态"
        else:
            note = "price 项无法模拟(依赖竞对报价, 现库为 mock), 不参评"
        if source_unreachable:
            note += "|已重灌但回传稿不可达(source 路径失效: 文件被移走或相对路径跨 cwd)——证据行无法检索是技术性缺失而非内容空缺; 按此包评审会把路径失效误当空缺压分, 先恢复回传稿(建议绝对路径重跑 reingest)再组装"
        elif not reingest:
            note += "|未重灌(会话内填写态)——证据行为空, 评审对象=会话内骨架"
        items.append(
            {
                "rubric_id": item.get("rubric_id"),
                "item": item.get("item"),
                "max_score": item.get("max_score"),
                "score_type": score_type,
                "scoring_method": item.get("scoring_method"),
                "source_ref": item.get("source_ref"),
                "linked_clauses": [{"clause_id": c.get("clause_id"), "requirement": c.get("requirement"), "response_status": c.get("response_status"), "points": (c.get("response_skeleton") or {}).get("points") or []} for c in linked],
                "evidence_lines": evidence,
                "note": note,
            }
        )

    pack = {"source": source_path, "items": items}
    atomic_write_json(state_dir / "evidence_pack.json", pack)
    anomalies: list[dict] = []
    if source_unreachable:
        unreachable_message = (
            f"重灌记录的回传稿不可达: {source_path}(文件被移走或相对路径跨 cwd 调用)——evidence_lines 全空是技术性不可达, 不是会话内填写态; "
            "评分纪律'无证据按空缺计分'会把路径失效误当内容空缺压分, 先恢复回传稿路径(建议绝对路径重跑 reingest)再重跑 assemble-evidence"
        )
        anomalies.append({"kind": "source_unreachable", "source": source_path, "message": unreachable_message})
    summary = {"command": "assemble-evidence", "written": "evidence_pack.json", "items": len(items), "evidence_lines_total": total_lines, "anomalies": anomalies}
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK if not anomalies else EXIT_ANOMALY


# =============================================================================
# 子命令 3: aggregate — Σ 纵深复检 + objective 确定性汇总 + subjective 消费评分
# =============================================================================


def _check_rubric_sum(rubric: dict) -> int | float:
    """Σmax_score 与评分办法声称总分一致性纵深复检(extract 阶段2 前置拦截, 此处双检);
    不一致 → 异常中止(退出码 1), 不落任何汇总产物。返回真实求和值(sum 结果, 不抄写
    declared——float 项求和得 100.0 与 declared int 100 数值相等但序列化形态不同)。"""
    total = rubric.get("total_score")
    items = rubric.get("items") or []
    # 契约对齐 rubric.schema.json: max_score/total_score = number(int|float 非 bool)——
    # 合法小数满分不得在纵深复检层被拒; bool/str 仍拒(误按 0/1 计会让 Σ 失真)。
    if total is None:
        # null 是设计的过渡态而非类型违例(M3): extract merge 未带 --declared-total 时如实写
        # null(extract 侧异常 rubric_declared_total_missing 为 rc=3 非失败)——报错归因分立,
        # 指路补声明, 不混进下方"应为数值(number)"的类型错误口径。
        raise ScoreSimulateError("rubric.json total_score 为 null——评分办法总分尚未声明(extract merge 未带 --declared-total 的过渡态): 先跑 extract.py merge --declared-total <N> 重合并(或确认门1 补总分)后再 aggregate")
    if not isinstance(total, (int, float)) or isinstance(total, bool):
        raise ScoreSimulateError(f"rubric.json total_score 应为数值(number; int/float 非 bool, Σ 校验基准): {total!r}")
    for index, item in enumerate(items):
        max_score = item.get("max_score")
        if not isinstance(max_score, (int, float)) or isinstance(max_score, bool):
            raise ScoreSimulateError(f"rubric.json items[{index}]({item.get('rubric_id')}) max_score 应为数值(number; int/float 非 bool, 契约=rubric.schema.json; bool/缺失误按 0/1 计会让 Σ 失真): {max_score!r}")
    computed = sum(item["max_score"] for item in items)
    if computed != total:
        raise ScoreSimulateError(f"Σmax_score={computed} 与评分办法声称总分 {total} 不一致——评分报告异常项并中止(评分细则表抽取可能缺行/降级; extract 阶段2 应已前置拦截, 此处纵深复检)")
    return computed


def _load_score_records(scores_path: Path) -> list[dict]:
    """装载 Agent 主观评分 JSON: 接受 裸数组 或 {"records": [...]}; 顶层形状错 → 退出码 1。"""
    data = _load_json_file(scores_path, "主观评分 JSON")
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"]
    if isinstance(data, list):
        return data
    raise ScoreSimulateError(f'主观评分 JSON 形状不符: 应为记录数组或 {{"records": [...]}}(scoring_prompt.md 契约): {scores_path}')


def _validate_records(records: list[dict], rubric_by_id: dict) -> tuple[dict, list[dict]]:
    """逐条校验评审记录; 违规记录逐类拦截进异常区(不静默丢弃也不带病计入)。"""
    valid: dict[str, dict] = {}
    anomalies: list[dict] = []
    seen: set[str] = set()
    for index, rec in enumerate(records):
        where = f"records[{index}]"
        if not isinstance(rec, dict) or any(field not in rec for field in RECORD_FIELDS):
            anomalies.append({"kind": "malformed_record", "message": f"{where} 缺契约字段(需 {list(RECORD_FIELDS)}): {rec!r}"})
            continue
        rid = rec.get("rubric_id")
        item = rubric_by_id.get(rid)
        if item is None:
            anomalies.append({"kind": "unknown_rubric_id", "rubric_id": rid, "message": f"{where} rubric_id {rid} 不在 rubric.json——评审对象错位"})
            continue
        if rid in seen:
            # 重复记录=评审作废信号: 不可信, 此前已收的也一并排除待人核(不取首个)。
            valid.pop(rid, None)
            anomalies.append({"kind": "duplicate_record", "rubric_id": rid, "message": f"{where} rubric_id {rid} 重复记录——不可信, 全部排除待人核"})
            continue
        seen.add(rid)
        if item.get("score_type") != "subjective":
            anomalies.append({"kind": "record_not_subjective", "rubric_id": rid, "message": f"{where} rubric_id {rid} 为 {item.get('score_type')} 项——objective 由确定性汇总出分, price 无法模拟, 均不吃 Agent 记录"})
            continue
        score = rec.get("score")
        # isfinite: NaN 对一切比较为 False, 会同时逃过 score<0 与 score>max 两道越界检查,
        # 污染 totals 并把裸 NaN 落进 aggregate_result.json(严格 JSON 的非法值)——必须拦截。
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or score < 0 or score > item["max_score"]:
            anomalies.append({"kind": "score_out_of_range", "rubric_id": rid, "score": score, "message": f"{where} score={score!r} 越界/非有限值(NaN/Infinity 不可计分; 应为 0..{item['max_score']} 的有限数)——排除待人核"})
            continue
        if rec.get("max_score") != item["max_score"]:
            anomalies.append({"kind": "record_max_mismatch", "rubric_id": rid, "message": f"{where} max_score={rec.get('max_score')!r} 与 rubric {item['max_score']} 不一致——评审基准漂移, 排除待人核"})
            continue
        if not isinstance(rec.get("rationale"), str) or not rec["rationale"].strip() or not isinstance(rec.get("missing_points"), list):
            anomalies.append({"kind": "malformed_record", "rubric_id": rid, "message": f"{where} rationale 应为非空字符串且 missing_points 应为数组(给分理由+失分点是铁律7 评分纪律)"})
            continue
        valid[rid] = rec
    return valid, anomalies


def _aggregate_objective(item: dict, clauses_by_id: dict, reingest_clauses: dict | None) -> tuple[dict, list[dict]]:
    """objective 项确定性汇总: 按重灌后条款状态, 已响应占比折算(见模块 docstring 口径)。"""
    rid = item.get("rubric_id")
    anomalies: list[dict] = []
    linked = item.get("linked_clause_ids") or []
    clause_states: list[dict] = []
    unverified = False
    active: list[dict] = []
    for cid in linked:
        clause = clauses_by_id.get(cid)
        if clause is None:
            anomalies.append({"kind": "dangling_fk", "rubric_id": rid, "message": f"rubric 项 {rid} linked_clause_ids 悬挂: {cid} 不在 clauses.json——无法确定性汇总"})
            unverified = True
            clause_states.append({"clause_id": cid, "state": "dangling"})
            continue
        if not _is_active(clause):
            clause_states.append({"clause_id": cid, "state": "历史(已替代/作废, 不计)"})
            continue
        if reingest_clauses is not None:
            rec = reingest_clauses.get(cid)
            if rec is not None and rec.get("match") != "matched":
                # 重灌不可信(未命中/重复 id/仅正文出现)→ 该条款不参与计分: 不计 0 不静默。
                unverified = True
                clause_states.append({"clause_id": cid, "state": "needs_human_verify"})
                continue
        active.append(clause)
        clause_states.append({"clause_id": cid, "state": clause.get("response_status")})

    base = {"rubric_id": rid, "item": item.get("item"), "score_type": "objective", "max_score": item["max_score"], "clause_states": clause_states}
    if not linked:
        anomalies.append({"kind": "objective_no_linkage", "rubric_id": rid, "message": f"objective 项 {rid}({item.get('item')})无 linked_clause_ids——状态汇总无对象, 无法确定性计分, [待确认]关联条款"})
        item_out = {
            **base,
            "score": None,
            "status": "needs_human",
            "rationale": "无关联条款——无法确定性汇总",
            "evidence_quote": None,
            "missing_points": ["objective 项未关联条款(linked_clause_ids 为空)"],
            "improvement": "先在 rubric.json 为该项关联条款, 再重跑 aggregate",
        }
        return item_out, anomalies
    if unverified:
        anomalies.append({"kind": "objective_unverified_clause", "rubric_id": rid, "message": f"objective 项 {rid}({item.get('item')})关联条款重灌不可信(needs_human_verify/重复 id/悬挂)——该项不计 0 分也不静默通过, 进异常区待人核"})
        item_out = {
            **base,
            "score": None,
            "status": "needs_human",
            "rationale": "关联条款重灌不可信——先人工核验",
            "evidence_quote": None,
            "missing_points": ["关联条款重灌未核验(needs_human_verify/重复 id)"],
            "improvement": "人工核验锚点与条款状态后重跑 reingest+aggregate",
        }
        return item_out, anomalies
    if not active:
        anomalies.append({"kind": "objective_no_linkage", "rubric_id": rid, "message": f"objective 项 {rid}({item.get('item')})关联条款全部为历史条款(superseded/voided)——无可计分对象"})
        return {**base, "score": None, "status": "needs_human", "rationale": "关联条款均为历史条款", "evidence_quote": None, "missing_points": ["关联条款已全部被替代/作废"], "improvement": "改链到替代条款后重跑 aggregate"}, anomalies

    satisfied = [c for c in active if c.get("response_status") == "compliant"]
    unsatisfied = [c for c in active if c.get("response_status") != "compliant"]
    score = round(item["max_score"] * len(satisfied) / len(active), 2)
    detail = ", ".join(f"{c['clause_id']}={STATUS_LABELS.get(c.get('response_status'), c.get('response_status'))}" for c in active)
    missing = [f"条款 {c['clause_id']} 状态={STATUS_LABELS.get(c.get('response_status'), c.get('response_status'))}(未响应)" for c in unsatisfied]
    if unsatisfied:
        improvement = "补齐条款 " + ", ".join(c["clause_id"] for c in unsatisfied) + " 的响应内容" + ("(偏离条款需实质变更供应方案)" if all(c.get("response_status") == "deviation" for c in unsatisfied) else "")
    else:
        improvement = None
    rationale = f"确定性汇总: {len(satisfied)}/{len(active)} 已响应({detail})——按已响应占比折算; 分档算术(如'每项扣N分')由人工对齐"
    return {**base, "score": score, "status": "scored", "rationale": rationale, "evidence_quote": None, "missing_points": missing, "improvement": improvement}, anomalies


def run_aggregate(scores_path: Path, state_dir: Path) -> int:
    """Σ 复检 → 装载三件套外键复检(D7) → 评审记录校验 → 三类分项汇总 → aggregate_result.json。"""
    rubric = _load_json_file(state_dir / "rubric.json", "rubric.json")
    computed_total = _check_rubric_sum(rubric)
    clauses = _load_clauses(state_dir)
    structure = _load_json_file(state_dir / "structure.json", "structure.json")
    reingest = _load_optional_json(state_dir / "reingest_result.json")
    if reingest and reingest.get("degraded"):
        raise ScoreSimulateError(f"重灌已降级(命中率 {reingest.get('hit_rate')} < 阈值 {reingest.get('threshold')})——整体人核覆盖率清单模式, 不做部分计分(D6④); 先人工核验后重跑 reingest")
    reingest_clauses = {rec.get("clause_id"): rec for rec in (reingest or {}).get("clauses") or []} or None

    rubric_items = rubric.get("items") or []
    rubric_by_id = {item.get("rubric_id"): item for item in rubric_items}
    # D7 防线对称: 会话内填写态(无 reingest 产物)同样复跑外键校验——rubric/structure 链接
    # superseded/voided 条款不再是'历史(不计)'式静默剔出分母, 与 reingest 路径同款异常。
    anomalies = validate_foreign_keys(clauses, structure, rubric_items)
    records = _load_score_records(scores_path)
    valid, record_anomalies = _validate_records(records, rubric_by_id)
    anomalies.extend(record_anomalies)

    clauses_by_id = {c.get("clause_id"): c for c in clauses}
    items: list[dict] = []
    for item in rubric_items:
        rid = item.get("rubric_id")
        score_type = item.get("score_type")
        if score_type == "price":
            items.append(
                {
                    "rubric_id": rid,
                    "item": item.get("item"),
                    "score_type": "price",
                    "max_score": item["max_score"],
                    "score": None,
                    "status": "price_unsimulatable",
                    "rationale": "无法模拟——依赖竞对报价(bid-quote 现库为 mock), 报价公式分不可模拟",
                    "evidence_quote": None,
                    "missing_points": [],
                    "improvement": None,
                    "clause_states": [],
                }
            )
            continue
        if score_type == "subjective":
            rec = valid.get(rid)
            if rec is not None:
                items.append(
                    {
                        "rubric_id": rid,
                        "item": item.get("item"),
                        "score_type": "subjective",
                        "max_score": item["max_score"],
                        "score": rec["score"],
                        "status": "scored",
                        "rationale": rec["rationale"],
                        "evidence_quote": rec.get("evidence_quote"),
                        "missing_points": rec.get("missing_points") or [],
                        "improvement": rec.get("improvement"),
                        "clause_states": [],
                    }
                )
            else:
                if any(a.get("rubric_id") == rid for a in anomalies):
                    status = "review_invalid"
                    why = "评审记录违规被拦截(见汇总异常)"
                else:
                    status = "missing_review"
                    why = "无评审记录"
                anomalies.append({"kind": "subjective_missing_review", "rubric_id": rid, "message": f"subjective 项 {rid}({item.get('item')}){why}——该项不计 0 分不静默, [待确认]补评审"})
                items.append(
                    {
                        "rubric_id": rid,
                        "item": item.get("item"),
                        "score_type": "subjective",
                        "max_score": item["max_score"],
                        "score": None,
                        "status": status,
                        "rationale": why,
                        "evidence_quote": None,
                        "missing_points": [f"主观项{why}"],
                        "improvement": "按 scoring_prompt.md 纪律补齐逐项评审(证据 grep 定位+给分理由+失分点)后重跑 aggregate",
                        "clause_states": [],
                    }
                )
            continue
        # objective: 确定性汇总(重灌后状态; 是汇总不是验证)
        obj_item, obj_anomalies = _aggregate_objective(item, clauses_by_id, reingest_clauses)
        anomalies.extend(obj_anomalies)
        items.append(obj_item)

    simulatable_max = sum(item["max_score"] for item in rubric_items if item.get("score_type") != "price")
    simulated = round(sum(it["score"] for it in items if isinstance(it.get("score"), (int, float)) and not isinstance(it.get("score"), bool)), 2)
    totals = {"full": rubric.get("total_score"), "simulatable_max": simulatable_max, "simulated": simulated}
    result = {"rubric_sum": {"computed": computed_total, "declared": rubric.get("total_score")}, "items": items, "totals": totals, "anomalies": anomalies}
    atomic_write_json(state_dir / "aggregate_result.json", result)
    summary = {"command": "aggregate", "written": "aggregate_result.json", "rubric_sum": result["rubric_sum"], "totals": result["totals"], "items": len(items), "anomalies": anomalies}
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK if not anomalies else EXIT_ANOMALY


# =============================================================================
# 子命令 4: report — 评分模拟报告渲染(version++ 留痕不覆盖历史)
# =============================================================================


def _next_report_version(report_dir: Path) -> int:
    """version++ 留痕: 扫描既有 version_N.md 取 max+1, 不覆盖历史(二期评分校准闭环消费)。"""
    highest = 0
    if report_dir.is_dir():
        for path in report_dir.iterdir():
            matched = _REPORT_VERSION_RE.match(path.name)
            if matched:
                highest = max(highest, int(matched.group(1)))
    return highest + 1


def _md_cell(value) -> str:
    """markdown 表格单元格转义: 文本内 "|" 会割裂表格列, 统一转义为 "\\|"
    (CommonMark/GFM 行内转义写法); 非表格上下文(小节标题/列表)不经过本函数。"""
    return str(value).replace("|", "\\|")


def improvement_entries(items: list[dict]) -> list[tuple]:
    """改进建议条目: 按 失分值×可改性 降序(平手按失分值降序, 再按 rubric_id 升序)。

    可改性(确定性规则, 报告口径):
        1.0 = 补写内容/补评审即可找回(未响应条款、主观项失分、缺评审)
        0.5 = 需实质变更(偏离条款)或先人工核验才能定改法(needs_human 项)
        price 项不入清单(无法模拟, 改进动作不在写作侧)
    """
    entries: list[tuple] = []
    for it in items:
        if it.get("score_type") == "price":
            continue
        score = it.get("score")
        if it.get("status") == "scored" and isinstance(score, (int, float)) and score >= it["max_score"]:
            continue
        loss = it["max_score"] if score is None else round(it["max_score"] - score, 2)
        if loss <= 0:
            continue
        if it.get("score_type") == "subjective":
            modifiable = MODIFIABLE_CONTENT
            if it.get("status") == "scored":
                advice = it.get("improvement") or "按失分原因补齐内容后重评"
            else:
                advice = "先补齐主观评审(scoring_prompt.md 纪律)或修复违规记录, 再重跑 aggregate"
        else:  # objective
            if it.get("status") == "needs_human":
                modifiable = MODIFIABLE_HARD
                advice = "先人工核验锚点/条款状态(needs_human_verify), 核验后重跑 reingest+aggregate"
            else:
                unsat = [c for c in it.get("clause_states") or [] if c.get("state") in ("unassigned", "draft", "pending_confirm", "deviation")]
                if any(c["state"] != "deviation" for c in unsat):
                    modifiable = MODIFIABLE_CONTENT
                    advice = "补齐未响应条款的响应内容: " + ", ".join(f"{c['clause_id']}({STATUS_LABELS.get(c['state'], c['state'])})" for c in unsat)
                else:
                    modifiable = MODIFIABLE_HARD
                    advice = "偏离条款需实质变更供应方案(或谈判豁免): " + ", ".join(c["clause_id"] for c in unsat)
        weight = round(loss * modifiable, 2)
        entries.append((weight, loss, it.get("rubric_id"), it.get("item"), modifiable, advice))
    entries.sort(key=lambda e: (-e[0], -e[1], e[2]))
    return entries


def _stale_state_files(state_dir: Path) -> list[str]:
    """report 侧 stale 复检: 权威态/重灌产物 mtime 晚于 aggregate_result.json 的文件名清单。

    混渲染 新重灌事实+旧汇总数字 是状态一致性风险(D7)——mtime 只用于本次渲染的警示
    判断, 产物本身仍不含时间戳(同输入重跑幂等纪律不变)。stat 失败按无警示处理(不阻断)。
    """
    agg = state_dir / "aggregate_result.json"
    if not agg.is_file():
        return []
    try:
        agg_mtime = agg.stat().st_mtime
        return sorted(name for name in ("clauses.json", "structure.json", "rubric.json", "reingest_result.json") if (state_dir / name).is_file() and (state_dir / name).stat().st_mtime > agg_mtime)
    except OSError:
        return []


def render_scoring_report(aggregate: dict, reingest: dict | None, version: int, stale_sources: list[str] | None = None) -> str:
    """评分模拟报告主体: 总览 / 逐项(得分·满分·理由·失分原因) / 改进建议 / 异常区。"""
    totals = aggregate.get("totals") or {}
    lines: list[str] = []
    lines.append(f"# 投标方案模拟评分报告(version {version})")
    lines.append("")
    lines.append('> 主观分一律为**模拟参考值**(skill 不承诺与真实评审一致); price 项如实标"无法模拟"; objective 分为重灌后状态的确定性汇总(是汇总不是验证)。')
    if reingest:
        anchors = reingest.get("anchors") or {}
        lines.append(f"> 重灌源: {reingest.get('source')}; 命中率 {anchors.get('matched')}/{anchors.get('total')}={reingest.get('hit_rate')}(阈值 {reingest.get('threshold')})。")
    else:
        lines.append("> 会话内填写态(未重灌)——objective 按当前 clauses.json 状态汇总。")
    if stale_sources:
        lines.append(f"> 警示: 以下产物在 aggregate 之后有更新({', '.join(stale_sources)})——上述汇总数字可能过期, 建议重跑 aggregate 再出报告。")
    lines.append("")

    lines.append("## 一、总览")
    lines.append("")
    lines.append(f"- 评分办法总分: {totals.get('full')}")
    lines.append(f"- 可模拟口径(除 price): {totals.get('simulated')} / {totals.get('simulatable_max')}")
    price_max = (totals.get("full") or 0) - (totals.get("simulatable_max") or 0)
    lines.append(f"- price 项(无法模拟): {price_max}")
    lines.append("")

    lines.append("## 二、逐项评分")
    lines.append("")
    lines.append("| rubric_id | 评分项 | 类型 | 得分/满分 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for it in aggregate.get("items") or []:
        score = it.get("score")
        shown = f"{score} / {it['max_score']}" if isinstance(score, (int, float)) else ("无法模拟" if it.get("score_type") == "price" else "未计分(needs_human)")
        lines.append(f"| {_md_cell(it.get('rubric_id'))} | {_md_cell(it.get('item'))} | {_md_cell(it.get('score_type'))} | {_md_cell(shown)} | {_md_cell(it.get('status'))} |")
    lines.append("")
    for it in aggregate.get("items") or []:
        lines.append(f"### {it.get('rubric_id')} {it.get('item')} —— {SCORE_TYPE_LABELS.get(it.get('score_type'), it.get('score_type'))}")
        lines.append("")
        score = it.get("score")
        shown = f"{score} / {it['max_score']}" if isinstance(score, (int, float)) else ("无法模拟" if it.get("score_type") == "price" else "未计分(needs_human——不计 0 分不静默)")
        lines.append(f"- 得分/满分: {shown}")
        lines.append(f"- 理由: {it.get('rationale')}")
        evidence = it.get("evidence_quote")
        lines.append(f"- 成稿证据: {evidence if evidence else '(无——objective 为状态汇总/price 不参评/评审未给出证据则按空缺计分)'}")
        missing = it.get("missing_points") or []
        lines.append("- 失分原因: " + ("; ".join(missing) if missing else "无(满分或未计分)"))
        if it.get("improvement"):
            lines.append(f"- 改进: {it.get('improvement')}")
        for state in it.get("clause_states") or []:
            lines.append(f"  - 条款 {state.get('clause_id')}: {state.get('state')}")
        lines.append("")

    lines.append("## 三、改进建议清单(按 失分值×可改性 降序)")
    lines.append("")
    entries = improvement_entries(aggregate.get("items") or [])
    if entries:
        lines.append("| 优先序 | rubric_id | 评分项 | 失分值 | 可改性 | 失分值×可改性 | 建议 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for rank, (weight, loss, rid, item_name, modifiable, advice) in enumerate(entries, start=1):
            lines.append(f"| {rank} | {_md_cell(rid)} | {_md_cell(item_name)} | {loss} | {modifiable} | {weight} | {_md_cell(advice)} |")
    else:
        lines.append("(无可改进项——全部满分或仅剩 price 项)")
    lines.append("")

    lines.append("## 四、异常区")
    lines.append("")
    if reingest and reingest.get("anomalies"):
        lines.append("### 重灌异常(阶段5)")
        lines.append("")
        for anomaly in reingest["anomalies"]:
            lines.append(f"- [{anomaly.get('kind')}] {anomaly.get('message')}")
        lines.append("")
    if aggregate.get("anomalies"):
        lines.append("### 汇总异常")
        lines.append("")
        for anomaly in aggregate["anomalies"]:
            lines.append(f"- [{anomaly.get('kind')}] {anomaly.get('message')}")
        lines.append("")
    if not (reingest and reingest.get("anomalies")) and not aggregate.get("anomalies"):
        lines.append("(无异常——重灌与汇总全绿)")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_degraded_report(reingest: dict, version: int) -> str:
    """降级模式报告: 人核覆盖率清单(D6④——匹配不可靠时退回人工模式, 不做部分计分)。"""
    anchors = reingest.get("anchors") or {}
    lines: list[str] = []
    lines.append(f"# 投标方案模拟评分报告(version {version})——降级: 人核覆盖率清单")
    lines.append("")
    lines.append(f"> 重灌命中率 {anchors.get('matched')}/{anchors.get('total')}={reingest.get('hit_rate')} 低于阈值 {reingest.get('threshold')}: 匹配不可靠, 整体降级(D6④)——**不做部分计分**, 逐锚点人工核验后重跑 reingest。")
    lines.append("")
    lines.append("## 人核覆盖率清单(逐锚点)")
    lines.append("")
    lines.append("| 锚点 | 类型 | 匹配 | 说明 |")
    lines.append("| --- | --- | --- | --- |")
    for node in reingest.get("nodes") or []:
        reason = node.get("fill_reason") or ""
        lines.append(f"| {_md_cell(node.get('node_id'))} {_md_cell(node.get('path'))} | 商务卷·{_md_cell(node.get('slot_type'))} | {_md_cell(node.get('match'))} | {_md_cell(reason)} |")
    for rec in reingest.get("clauses") or []:
        lines.append(f"| {_md_cell(rec.get('clause_id'))} | 技术卷·条目 | {_md_cell(rec.get('match'))} | 出现 {rec.get('occurrences')} 次; 重灌前状态 {_md_cell(rec.get('response_status_before'))} |")
    lines.append("")
    if reingest.get("anomalies"):
        lines.append("## 异常区")
        lines.append("")
        for anomaly in reingest["anomalies"]:
            lines.append(f"- [{anomaly.get('kind')}] {anomaly.get('message')}")
        lines.append("")
    return "\n".join(lines) + "\n"


def run_report(state_dir: Path) -> int:
    """渲染评分模拟报告 → 评分报告/version_N.md(version++ 留痕不覆盖历史)。"""
    report_dir = state_dir / REPORT_DIR_NAME
    version = _next_report_version(report_dir)
    reingest = _load_optional_json(state_dir / "reingest_result.json")
    if reingest and reingest.get("degraded"):
        md = render_degraded_report(reingest, version)
        stale_sources: list[str] = []
    else:
        aggregate = _load_json_file(state_dir / "aggregate_result.json", "aggregate_result.json(降级模式外, report 前必须先跑 aggregate)")
        stale_sources = _stale_state_files(state_dir)
        md = render_scoring_report(aggregate, reingest, version, stale_sources=stale_sources)
    path = report_dir / f"version_{version}.md"
    atomic_write_text(path, md)
    summary = {"command": "report", "written": f"{REPORT_DIR_NAME}/version_{version}.md", "version": version, "stale_aggregate": bool(stale_sources)}
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK


# =============================================================================
# CLI
# =============================================================================


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回进程退出码(见模块 docstring 退出码约定)。"""
    parser = argparse.ArgumentParser(
        prog="score_simulate.py",
        description="投标方案编写·阶段5 模拟评分: reingest 回传稿锚点重灌(D2/D6) / assemble-evidence 证据包 / aggregate Σ复检+客观汇总+主观消费 / report 评分报告 version++(无 LLM)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_reingest = sub.add_parser("reingest", help="回传 md 锚点重灌: 商务卷=标题链, 技术卷=clause_id; 多命中/重复 id→异常区; 命中率低于阈值整体降级(D6)")
    p_reingest.add_argument("--source", required=True, help="回传 .md 路径(必须显式指定, D2——防多版回传并存时灌了旧版; docx 先经 uploads 自动转换)")
    p_reingest.add_argument("--state-dir", required=True, help="状态目录(clauses.json/structure.json/rubric.json; 重灌只更新权威态 clauses.json)")
    p_reingest.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help=f"重灌命中率降级阈值, 默认 {DEFAULT_THRESHOLD}(低于即整体降级人核覆盖率清单)")
    p_reingest.add_argument("--volume", choices=("commercial", "technical", "both"), default="both", help="单卷回传限定: 只以该卷为锚点分母(另一卷不计 hit_rate/不产 unmatched/权威态不动); both=默认, 双卷拼接文件按全量锚点")

    p_evidence = sub.add_parser("assemble-evidence", help="逐 rubric 项组装证据包(grep 回传稿证据行), 供 Agent 主观评审循环")
    p_evidence.add_argument("--state-dir", required=True, help="状态目录(读 rubric/clauses/reingest_result, 写 evidence_pack.json)")

    p_aggregate = sub.add_parser("aggregate", help="Σ 纵深复检 + objective 确定性汇总 + price 标无法模拟 + subjective 消费 Agent 评分 JSON")
    p_aggregate.add_argument("--scores", required=True, help='Agent 主观评分 JSON(scoring_prompt.md 评审输出记录: 数组或 {"records": [...]})')
    p_aggregate.add_argument("--state-dir", required=True, help="状态目录(写 aggregate_result.json)")

    p_report = sub.add_parser("report", help="渲染评分模拟报告 → 评分报告/version_N.md(version++ 留痕不覆盖历史)")
    p_report.add_argument("--state-dir", required=True, help="状态目录(读 aggregate_result/reingest_result)")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse 用法错误默认 SystemExit(2), 与 ingest 的 OCR 分流退出码撞号——统一改道
        # EXIT_ERROR; --help 等正常退出(code 0)原样放行(同 build_output/merge_addenda 约定)。
        if not exc.code:
            return EXIT_OK
        print(f"[score_simulate] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}); 用法错误归退出码 1, 2 已保留给 ingest 的 OCR 分流(用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR

    try:
        if args.command == "reingest":
            if not (0 < args.threshold <= 1):
                raise ScoreSimulateError(f"--threshold 须在 (0,1] 区间: {args.threshold}")
            return run_reingest(Path(args.source), Path(args.state_dir), args.threshold, args.volume)
        if args.command == "assemble-evidence":
            return run_assemble_evidence(Path(args.state_dir))
        if args.command == "aggregate":
            return run_aggregate(Path(args.scores), Path(args.state_dir))
        return run_report(Path(args.state_dir))
    except ScoreSimulateError as exc:
        print(f"[score_simulate] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
