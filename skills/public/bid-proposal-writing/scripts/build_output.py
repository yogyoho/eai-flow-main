#!/usr/bin/env python3
"""build_output.py — 投标方案编写技能·阶段4 交付渲染(无 LLM)。

规格: docs/superpowers/specs/2026-08-16-bid-proposal-writing-skill-design.md
「阶段4 build」+ D2(重灌锚点载体在渲染时埋定)/D7(派生字段现算不落盘/原子写盘)
+ v4 分册架构(docs/designs/bid-proposal-writing-v4-volume-architecture.md Revision 4)。
本脚本只做确定性渲染, 产出两文档册集 md 即止; **不做 Word 转换**——排版与 .docx
导出由用户在文档空间完成(present_files 交付后自动同步)。

用法:
    python build_output.py --state-dir <dir> --out <dir>

输出两文档册集(--out 目录, v4 Revision 4 两文档拓扑):
    整体方案-NN-首章短名.md(商务章全量+技术章占位页, 零技术正文内联)
    技术卷-NN-首章短名.md(技术章全量, 卷尾件挂末册)
    0-总目录索引.md(确定性投影, 分册导航/合并导出序)
    偏离表.md / 覆盖率报表.md / 人核清单.md / 实体lint报告.md(全局副表)
    delivery_manifest.json(交付凭据: skill/version/deliverables, 清场依据)

职责(设计文档锁定, 不缺不漏不加):
    ① 商务卷 = structure.json 镜像渲染: path 标题链 → # 层级章节树, 层级完整,
       只镜像不自创; 正文只含交付内容——template_text 纯正文段落/表格列头+
       fixed_rows 逐字+剩余待填行/image 槽干净占位; 槽位编排元数据(类型/格式
       要求/填写状态/关联条款)全部迁覆盖率报表"槽位编排表"sidecar 节(回放实证
       2026-08-18 线程 1a80a1d8: 槽位 bullet 被当正文写进交付物/转换进 docx);
       image 槽在卷末汇总扫描件清单(图片不经 md 链路插入)。
    ② 技术卷 = 格式章节规定结构部分按镜像渲染 + 逐条款条目: 条目标题嵌 clause_id
       (如 "2.1 响应[ZB-C-001]"——clause_id 入标题是阶段5 重灌唯一可存活的锚点
       载体, 交付物中保留不删, D2); mandatory 条款条目标题整体**加粗**;
       条目节号优先取槽位标题前导数字, 撞号/无号顺延(全卷 N 唯一, 观感去重——
       锚点是 clause_id, 编号不承担契约职责);
       条目体正文 = responses.json(阶段4a 三模式生成)的 response_text(+points
       要点列表); 无响应条目骨架回退为待填占位; 锚点/满足状态等编排元数据迁
       覆盖率报表 sidecar; 活条款(technical/service 类)无挂接槽时入卷末
       "其他技术要求响应"节(标题中性化, 出处 sidecar 标注), 零遗漏。
    ③ 偏离表 = 仅 class=mandatory 或 response_status=deviation 的活条款。
    ④ 覆盖率报表 = 清单总数/已响应/待确认/未分配(已响应=compliant+deviation,
       待确认=draft+pending_confirm, 未分配=unassigned; superseded/voided 是
       历史条款, 除外列示不计入总数)+ 槽位编排表 sidecar(双卷净化后的槽位
       元数据归属地, 含关联条款悬挂外键标注)。
    ⑤ 实体 lint = 白名单 diff 全部 evidence_ref 与引用片段(source_ref.quote):
       确定性候选提取——company 先掩蔽白名单值再按全部工商后缀位置扫描(同一
       结束位置取最长后缀, 前导连接词仅修剪显示值; 防贪婪正则把白名单公司连同
       前导散文吸成污染候选/相邻两公司合并), spec_version 用型号+V版本正则;
       候选与白名单比对按归一化(去空白+casefold, "S7-1500V2.3"≡"S7-1500 V2.3");
       白名单外 → 报告[待核对] + 摘要异常; person/project 无确定性提取模式,
       只做白名单命中统计(按出现次数计, 无法被动发现)——报告显著标注
       "LLM辅助抽取白名单，非确定性"(白名单本身由 LLM 抽取+人工确认, lint 是
       确定性 diff 但覆盖受白名单与模式能力限制)。
    ⑥ 人核清单 = format_check 槽(签字/盖章/份数/页码)全部入清单不进确定性判定
       + [待人工复刻]表格槽(管道表格无法表达合并单元格/列宽——如实声明渲染
       边界, 所有表格槽均标[待人工复刻]并列头骨架照渲染)
       + 生成内容人核节(needs_human_verify/web 引用逐条核实)。

脚本纪律: 纯 Python 3.12; stdlib only; 不调用 LLM; 不 import app.*/deerflow.*;
    状态目录只读(D7: fill_status 等派生字段渲染时现算不落盘); 输出文件临时
    文件+os.replace 原子写盘; 渲染不含时间戳 → 重跑字节级幂等。

退出码:
    0 = 干净完成(--help 亦为 0)
    1 = 用法/文件错误(状态文件缺失/不可解析/结构损坏、输出目录不可写; argparse 用法错误统一
        改道 1——2 留给 ingest 的 OCR 分流语义, 防编排方误路由)
    3 = 完成但有异常项(lint 待核对实体/白名单缺失/悬挂外键, 摘要 anomalies 列出)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import booklets  # v4 分册: 页数估算/贪心切册/册命名/索引卷(纯函数, 同目录兄弟模块)
import state_guard

# --- 退出码约定 -----------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ANOMALY = 3

# --- 契约常量(references/*.schema.json 同款约束; 沙箱无 jsonschema, 内联同子集) ---
CLAUSE_CLASSES = ("mandatory", "scoring", "normal")
CLAUSE_CATEGORIES = ("technical", "commercial", "qualification", "format", "service")
RESPONSE_STATUSES = ("unassigned", "draft", "pending_confirm", "compliant", "deviation")
SLOT_TYPES = ("text", "table", "image", "format_check", "group")
VOLUMES = ("commercial", "technical")
# 技术卷条目承载口径(v2): technical+service——与 responses.py RESPONSE_CATEGORIES
# 对齐(服务承诺响应同走生成管线; 商务/资格/格式条款走模板镜像管线, 不产条目)。
ENTRY_CATEGORIES = ("technical", "service")

# v4 两文档册集(Revision 4): 册文件动态生成(整体方案-NN-*.md / 技术卷-NN-*.md),
# 静态件 = 索引卷 + 四张副表(全局单份, 跨册聚合); delivery_manifest 为交付凭据
# (skill/version/deliverables, 通用化契约见 WP-2.3)——清场与白名单新鲜度都依赖它。
DOC_OVERALL = "整体方案"
DOC_TECH = "技术卷"
INDEX_FILE = booklets.INDEX_FILENAME
SIDECAR_FILES = ("偏离表.md", "覆盖率报表.md", "人核清单.md", "实体lint报告.md")
MANIFEST_NAME = "delivery_manifest.json"
MANIFEST_VERSION = 1
LEGACY_OUTPUT_FILES = ("商务卷.md", "技术卷.md")  # v3 遗留双卷——清场对象(11A 目录幂等)

SLOT_TYPE_LABELS = {"text": "文字槽", "table": "表格槽", "image": "图片槽", "format_check": "格式核验槽", "group": "结构组"}
CLASS_LABELS = {"mandatory": "强制条款", "scoring": "评分条款", "normal": "普通条款"}
STATUS_LABELS = {"unassigned": "未分配", "draft": "草稿", "pending_confirm": "待确认", "compliant": "已响应", "deviation": "偏离"}
# 口径桶: 已响应=compliant+deviation 待确认=draft+pending_confirm 未分配=unassigned
RESPONDED_STATUSES = ("compliant", "deviation")
PENDING_STATUSES = ("draft", "pending_confirm")

# 模板原文预填(用户决策 2026-08-16): 所有商务类格式模板——投标响应函/法定代表人
# 授权委托书/报价一览表/分项价格表/投标货物分项报价明细表/商务偏离表(项目要求及
# 报价响应表)/技术偏离表(技术条款响应/偏离表)等, 不限于——的固定文字原文照抄进
# required_format.template_text。渲染为**纯正文段落**(v2: 引用块前缀与标记行是管线
# 元数据, 不进交付物——回放实证曾连同 bullet 一起被当正文转进 docx); 照抄非确定性
# → 人核清单第三节比对兜底。

# 技术卷兜底节标题(v2 中性化): 内部标签"未挂接格式槽的技术条款(清单驱动)"是管线
# 词汇, 不进交付物; 出处口径在覆盖率报表 sidecar 标注。
ORPHAN_SECTION_TITLE = "其他技术要求响应"

# 实体 lint 可确定性提取的候选(白名单外 → [待核对]);
# person/project 无确定性模式, 由白名单命中统计覆盖——报告如实声明此边界。
# company 不用单条贪婪正则: \w 在中文(无空格分隔)里会把白名单公司连同前导散文吸成
# 单一污染候选("见东智装备制造有限公司"), 相邻两公司也合并为一个候选——改为
# "白名单掩蔽 + 按全部后缀位置扫描"(见 _extract_entity_candidates)。
COMPANY_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司", "集团公司")  # 同一结束位置取最长后缀
COMPANY_MAX_PREFIX = 30  # 字号前缀 \w 上限(对齐原正则 {2,30} 的量级约束)
# 前导连接/引介词修剪——仅影响候选显示值, 不改变命中方向(白名单值已被掩蔽, 修剪
# 不可能把残留候选修成白名单命中)。多字词在前, 循环修剪至无可再剪。
COMPANY_LEADING_TRIM = ("参照", "参考", "以及", "包括", "由", "见", "按", "据", "向", "从", "受", "经", "把", "被", "让", "给", "即", "系", "与", "及", "或")
SPEC_VERSION_RE = re.compile(r"[A-Z][A-Z0-9]*[0-9][A-Z0-9-]*\s*V\d+(?:\.\d+)+")
_WORD_CHAR_RE = re.compile(r"\w")
_MASK_SENTINEL = "\x00"  # 非 \w 字符: 掩蔽白名单值, 阻断贪婪前缀吸收/相邻合并


class BuildOutputError(Exception):
    """用法/文件错误 → 退出码 1。"""


# =============================================================================
# 基础件: JSON 装载 / 原子写盘 / 派生小函数
# =============================================================================


def _load_json_file(path: Path, what: str):
    """装载 UTF-8 JSON 文件; 缺失/不可解析 → BuildOutputError(退出码 1), 绝不静默。"""
    if not path.is_file():
        raise BuildOutputError(f"{what} 不存在: {path}")
    try:
        # utf-8-sig: Windows 记事本"带 BOM 的 UTF-8"产物剥掉 BOM(对齐 extract 装载器口径; 无 BOM 行为不变)
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise BuildOutputError(f"{what} 不可读/不可解析(需 UTF-8; 疑似截断或编码错): {path}: {exc}") from exc


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


def _is_active(clause: dict) -> bool:
    """活条款 = 未 superseded 且未 voided(条目/偏离表/覆盖率都以活条款为口径)。"""
    return clause.get("superseded_by") is None and not clause.get("voided")


def _cell(value) -> str:
    """markdown 表格单元格转义: 竖线/换行不得破坏表格。"""
    return str(value).replace("|", "\\|").replace("\n", " ")


def derive_fill_status(node: dict) -> tuple[str, str]:
    """fill_status 现算不落盘(D7): 骨架渲染时 text=unfilled, 其余均含人核成分。"""
    slot_type = node["slot_type"]
    if slot_type == "image":
        return "needs_human_verify", "图片槽——扫描件由用户提供, 不经 md 链路插入"
    if slot_type == "format_check":
        return "needs_human_verify", "format_check——人核项, 不做确定性判定"
    if slot_type == "table":
        return "needs_human_verify", "合并单元格/列宽管道表格无法表达, 标[待人工复刻]"
    return "unfilled", "骨架待填"


def template_text_of(node: dict) -> str | None:
    """节点携带的模板原文(非空字符串或 None); 空串/非字符串属装载期校验职责。"""
    template_text = (node.get("required_format") or {}).get("template_text")
    return template_text if isinstance(template_text, str) and template_text.strip() else None


def template_body_lines(node: dict) -> list[str]:
    """模板原文 → 纯正文段落(v2 净化: 引用块前缀与标记行是管线元数据, 不进交付物)。

    无模板返回空列表; 适用于全部槽位类型。空行保留(模板段落的排版语义)。
    """
    template_text = template_text_of(node)
    if template_text is None:
        return []
    return [ln.rstrip() for ln in template_text.splitlines()]


# =============================================================================
# 状态装载(状态目录只读, 本脚本不写任何状态文件)
# =============================================================================


def load_clauses(state_dir: Path) -> list[dict]:
    """装载并轻校验 clauses.json(枚举错/缺 clause_id → 拒绝渲染, 退出码 1)。"""
    path = state_dir / "clauses.json"
    data = _load_json_file(path, "clauses.json")
    if not isinstance(data, list) or not all(isinstance(c, dict) for c in data):
        raise BuildOutputError(f"clauses.json 结构异常(应为对象数组), 拒绝渲染(先人工核查): {path}")
    for index, clause in enumerate(data):
        if not isinstance(clause.get("clause_id"), str) or not clause["clause_id"]:
            raise BuildOutputError(f"clauses.json items[{index}] 缺非空字符串 clause_id, 拒绝渲染: {path}")
        if clause.get("class") not in CLAUSE_CLASSES:
            raise BuildOutputError(f"clauses.json items[{index}] class 枚举非法 {clause.get('class')!r}(合法: {list(CLAUSE_CLASSES)}): {path}")
        if clause.get("category") not in CLAUSE_CATEGORIES:
            raise BuildOutputError(f"clauses.json items[{index}] category 枚举非法 {clause.get('category')!r}(合法: {list(CLAUSE_CATEGORIES)}): {path}")
        if clause.get("response_status") not in RESPONSE_STATUSES:
            raise BuildOutputError(f"clauses.json items[{index}] response_status 枚举非法 {clause.get('response_status')!r}(合法: {list(RESPONSE_STATUSES)}): {path}")
        if clause.get("response_skeleton") is not None and not isinstance(clause.get("response_skeleton"), dict):
            raise BuildOutputError(f"clauses.json items[{index}] response_skeleton 应为对象或 null, 拒绝渲染: {path}")
    return data


def load_structure(state_dir: Path) -> list[dict]:
    """装载并轻校验 structure.json(卷/槽位枚举、path 非空 → 拒绝渲染)。"""
    path = state_dir / "structure.json"
    data = _load_json_file(path, "structure.json")
    if not isinstance(data, list) or not all(isinstance(n, dict) for n in data):
        raise BuildOutputError(f"structure.json 结构异常(应为对象数组), 拒绝渲染(先人工核查): {path}")
    for index, node in enumerate(data):
        if not isinstance(node.get("node_id"), str) or not node["node_id"]:
            raise BuildOutputError(f"structure.json items[{index}] 缺非空字符串 node_id, 拒绝渲染: {path}")
        if node.get("volume") not in VOLUMES:
            raise BuildOutputError(f"structure.json items[{index}] volume 枚举非法 {node.get('volume')!r}(合法: {list(VOLUMES)}): {path}")
        if node.get("slot_type") not in SLOT_TYPES:
            raise BuildOutputError(f"structure.json items[{index}] slot_type 枚举非法 {node.get('slot_type')!r}(合法: {list(SLOT_TYPES)}): {path}")
        if not isinstance(node.get("path"), str) or not node["path"].strip():
            raise BuildOutputError(f"structure.json items[{index}] path 应为非空字符串: {path}")
        if not isinstance(node.get("linked_clause_ids") or [], list):
            raise BuildOutputError(f"structure.json items[{index}] linked_clause_ids 应为数组: {path}")
        template_text = (node.get("required_format") or {}).get("template_text")
        if template_text is not None and (not isinstance(template_text, str) or not template_text.strip()):
            # schema minLength:1 的消费侧收口(同 table_spec 形状校验先例): 空串=半成品照抄, 拒绝渲染
            raise BuildOutputError(f"structure.json items[{index}] {node['node_id']} required_format.template_text 应为非空字符串或 null(模板原文照抄): {path}")
        if node["slot_type"] == "table":
            table_spec = (node.get("required_format") or {}).get("table_spec")
            if table_spec is not None:
                # 形状校验(schema 层 table_spec 为自由对象, 消费侧约束在此收口):
                # rows 字符串曾以未捕获 ValueError 裸崩, columns 字符串曾按字符迭代
                # 静默渲染逐字列头——装载期拒绝, 走 BuildOutputError 干净退出(退出码 1)。
                if not isinstance(table_spec, dict):
                    raise BuildOutputError(f"structure.json items[{index}] {node['node_id']} table_spec 应为对象: {path}")
                columns = table_spec.get("columns")
                if not isinstance(columns, list) or not columns or not all(isinstance(c, (str, int, float)) and not isinstance(c, bool) for c in columns):
                    raise BuildOutputError(f"structure.json items[{index}] {node['node_id']} table_spec.columns 应为非空标量数组(列头骨架渲染前提): {path}")
                if "rows" in table_spec:  # 缺省容忍(按 1 渲染); 显式 null/非法类型拒绝
                    rows = table_spec["rows"]
                    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 1:
                        raise BuildOutputError(f"structure.json items[{index}] {node['node_id']} table_spec.rows 应为 >=1 的整数(缺省按 1): {path}")
    return data


def load_whitelist(state_dir: Path) -> dict | None:
    """装载实体白名单(确认门1 锁定); 缺失 → None(浮出 whitelist_missing 异常, 按空集 diff)。"""
    path = state_dir / "entities_whitelist.json"
    if not path.is_file():
        return None
    data = _load_json_file(path, "entities_whitelist.json")
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
        raise BuildOutputError(f"entities_whitelist.json 结构异常(应为含 entities 数组的对象), 拒绝渲染(先人工核查): {path}")
    for index, entity in enumerate(data["entities"]):
        if not isinstance(entity, dict) or not isinstance(entity.get("type"), str) or not entity["type"].strip() or not isinstance(entity.get("value"), str) or not entity["value"].strip():
            raise BuildOutputError(f"entities_whitelist.json entities[{index}] 应为含非空 type/value 的对象, 拒绝渲染: {path}")
    return data


def load_responses(state_dir: Path) -> list[dict]:
    """装载 responses.json(阶段4a 技术响应权威态, responses.py merge 落账+签名)。

    缺失 → [](骨架模式回退: 条目体渲染待填占位); 在盘但形态异常/缺必填 → 拒绝渲染
    (退出码 1, 先跑 responses.py merge 而不是带病渲染)。签名校验由 state_guard 前置
    覆盖(responses.json 在 AUTHORITATIVE_FILES 五元组内, 脚本外直写会在读盘前被拦)。
    """
    path = state_dir / "responses.json"
    if not path.is_file():
        return []
    data = _load_json_file(path, "responses.json")
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise BuildOutputError(f"responses.json 结构异常(应为对象数组), 拒绝渲染(先人工核查): {path}")
    for index, item in enumerate(data):
        for field in ("clause_id", "response_text", "source_mode"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise BuildOutputError(f"responses.json items[{index}] 缺非空字符串 {field}, 拒绝渲染(先重跑 responses.py merge): {path}")
    return data


# =============================================================================
# ② 条目渲染(技术卷逐条款条目, D2 锚点载体)
# =============================================================================


def render_clause_entry(clause: dict, num: str, level: int = 3, response: dict | None = None) -> list[str]:
    """条目 = 标题(N.M 响应[clause_id], mandatory 整体加粗) + 正文(response_text)。

    正文只含交付内容: 有响应 → response_text(+points 要点列表); 无响应 → 骨架回退
    待填占位。锚点/满足状态/证据引用等编排元数据不进双卷正文(回放实证 2026-08-18
    线程 1a80a1d8: 五字段 bullet 被当正文写进交付物/转换进 docx)——条款原文锚点在
    偏离表可查, 状态在覆盖率报表逐条款附录 sidecar 可查。
    """
    title = f"{num} 响应[{clause['clause_id']}]"
    if clause["class"] == "mandatory":
        title = f"**{title}**"  # mandatory 条款是废标级风险, 加粗是唯一强调载体
    lines = ["#" * level + " " + title, ""]
    if response is not None:
        points = response.get("points") or []
        if points:
            lines.extend(f"- {_cell(p)}" for p in points)
            lines.append("")
        lines.extend(ln.rstrip() for ln in response["response_text"].splitlines())
        lines.append("")
    else:
        lines.extend(["(响应正文待生成或待填写)", ""])
    return lines


# =============================================================================
# ①② 双卷渲染(structure.json 镜像 + 技术卷条目挂接)
# =============================================================================


def _table_rows(table_spec: dict) -> int:
    """表格行数口径(双卷骨架与人核清单共用): 缺省/无效一律 1——装载期已校验 int>=1,
    此处兜底保证两处渲染口径一致(人核清单曾对缺省 rows 渲染空单元格)。"""
    rows = table_spec.get("rows")
    return rows if isinstance(rows, int) and not isinstance(rows, bool) and rows >= 1 else 1


def _fixed_row_count(node: dict) -> int:
    """节点表格槽的固定行数(非表格/无 fixed_rows → 0); 摘要 fixed_rows_replicated 计数用。"""
    table_spec = (node.get("required_format") or {}).get("table_spec")
    fixed = table_spec.get("fixed_rows") if isinstance(table_spec, dict) else None
    return len(fixed) if isinstance(fixed, list) else 0


def _next_free_number(claimed: set[int]) -> int:
    """下一个未占用节号(从已占用最大值 +1 起顺延)。"""
    number = max(claimed) + 1 if claimed else 1
    while number in claimed:
        number += 1
    return number


def _allocate_section_numbers(nodes: list[dict]) -> tuple[dict[str, str], set[int]]:
    """技术卷条目节号分配(观感去撞; clause_id 锚点 D2 不受编号影响)。

    优先认领槽位标题前导数字; 撞号或无数字时顺延取未占用号——原实现两槽同前导
    数字(或无数字回退计数与带号槽重合)会产出重复"N.1 响应[...]"标题, 卷末孤儿节
    max(titled)+1 也可能与顺延号撞号。镜像 group 不占号; origin=self_created 的
    自拟挂接位(responses.py 建)承载条目, 必须占号。返回 (node_id → 节号, 已占用
    集合——供孤儿节续号)。
    """
    claimed: set[int] = set()
    numbers: dict[str, str] = {}
    for node in nodes:
        if node["slot_type"] == "group" and node.get("origin") != "self_created":
            continue
        matched = re.match(r"\s*(\d+)", node["path"].split("/")[-1])
        number = int(matched.group(1)) if matched else _next_free_number(claimed)
        if number in claimed:
            number = _next_free_number(claimed)
        claimed.add(number)
        numbers[node["node_id"]] = str(number)
    return numbers, claimed


def _linked_clause_labels(node: dict, clauses_by_id: dict[str, dict]) -> list[str]:
    """关联条款标注(覆盖率报表"槽位编排表"专用): 缺失→异常标注; superseded/voided→历史状态。"""
    parts = []
    for cid in node.get("linked_clause_ids") or []:
        clause = clauses_by_id.get(cid)
        if clause is None:
            parts.append(f"{cid}(不存在——异常, 不静默)")
        elif clause.get("superseded_by") is not None:
            parts.append(f"{cid}(已被 {clause['superseded_by']} 取代)")
        elif clause.get("voided"):
            parts.append(f"{cid}(已作废)")
        else:
            parts.append(f"{cid}({clause['response_status']})")
    return parts


def _volume_ctx(volume: str, structure: list[dict], clauses: list[dict], responses: list[dict] | None) -> dict:
    """单卷渲染共享上下文(每卷预计算一次, 章分组渲染复用——v4 分册改造)。"""
    responses_by_id = {r["clause_id"]: r for r in (responses or [])}
    clauses_by_id = {c["clause_id"]: c for c in clauses}
    nodes = [n for n in structure if n["volume"] == volume]
    active_tech = [c for c in clauses if _is_active(c) and c.get("category") in ENTRY_CATEGORIES]
    section_numbers: dict[str, str] = {}
    claimed: set[int] = set()
    if volume == "technical":
        section_numbers, claimed = _allocate_section_numbers(nodes)
    # 活条款 → 首个挂接它的可承载节点(镜像 group 不承载; origin=self_created 自拟
    # 挂接位承载——多处挂接以首处为准渲染, 零遗漏优先)
    linked_map: dict[str, str] = {}
    for node in nodes:
        if node["slot_type"] == "group" and node.get("origin") != "self_created":
            continue
        for cid in node.get("linked_clause_ids") or []:
            linked_map.setdefault(cid, node["node_id"])
    return {
        "nodes": nodes,
        "responses_by_id": responses_by_id,
        "clauses_by_id": clauses_by_id,
        "active_tech": active_tech,
        "section_numbers": section_numbers,
        "claimed": claimed,
        "linked_map": linked_map,
    }


def _render_nodes(nodes: list[dict], volume: str, ctx: dict) -> tuple[list[str], list[dict]]:
    """渲染一组节点(v4 分册改造: 原整卷循环体提取为节点组渲染, 章分组复用)。

    v2 双卷净化纪律不变: 正文只含交付内容(模板原文纯段落/表格列头+固定行逐字+
    待填行/image 干净占位/条目 response_text), 槽位编排元数据迁覆盖率报表 sidecar。
    """
    responses_by_id = ctx["responses_by_id"]
    clauses_by_id = ctx["clauses_by_id"]
    active_tech = ctx["active_tech"]
    section_numbers = ctx["section_numbers"]
    linked_map = ctx["linked_map"]

    lines: list[str] = []
    anomalies: list[dict] = []

    def _ensure_blank() -> None:
        """块与块之间保证空行分隔(md 解析器对紧跟列表/表格的标题敏感)。"""
        if lines and lines[-1] != "":
            lines.append("")

    for node in nodes:
        segments = [s.strip() for s in node["path"].split("/")]
        title = segments[-1]
        _ensure_blank()
        lines.append("#" * min(len(segments), 6) + " " + title)
        lines.append("")
        required_format = node.get("required_format") or {}
        desc = required_format.get("desc")
        # 模板原文预填(用户决策): 所有商务类格式模板固定文字原文带入骨架——单调用点
        # 在 group 早退之前, 全部槽位类型(含 group 格式章节说明)统一生效; v2 渲染为
        # 纯正文段落(引用块前缀与标记行是管线元数据, 不进交付物)
        template_lines = template_body_lines(node)
        if template_lines:
            lines.extend(template_lines)
            lines.append("")
        slot_type = node["slot_type"]
        if slot_type == "group" and node.get("origin") != "self_created":
            continue  # 镜像结构组无正文; desc(编排说明)迁覆盖率报表槽位编排表 sidecar。
            # 自拟挂接位(responses.py 建)是 group 但承载条目——不得在此早退, 否则其
            # 挂接条款既不出条目也不落卷末兜底节, 静默丢失(与 linked_map 跳过条件对齐)。
        if slot_type == "image":
            # 干净占位: 终稿由用户在文档空间排版时插入扫描件(图片不经 md 链路插入)
            lines.append(f"[此处插入:{desc or title}]")
            lines.append("")

        # 悬挂外键(缺失→异常不静默; 标注进覆盖率报表槽位编排表, 不进交付正文)
        for cid in node.get("linked_clause_ids") or []:
            if cid not in clauses_by_id:
                message = f"structure {node['node_id']} 悬挂外键 {cid}(reason=missing)——异常不静默, 待人工改链(D7)"
                anomalies.append({"kind": "clause_fk_invalid", "source": "structure", "item_id": node["node_id"], "clause_id": cid, "reason": "missing", "message": message})

        # 表格槽: 列头 + fixed_rows 逐字复刻 + 剩余空白待填行 + [待人工复刻] 边界声明
        table_spec = required_format.get("table_spec")
        if slot_type == "table":
            if isinstance(table_spec, dict) and table_spec.get("columns"):
                columns = [str(c) for c in table_spec["columns"]]
                fixed_rows = table_spec.get("fixed_rows") if isinstance(table_spec.get("fixed_rows"), list) else []
                lines.extend(["", "| " + " | ".join(_cell(c) for c in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"])
                for row in fixed_rows:  # 模板固定行逐字复刻(反馈2: 表格也要 1:1)
                    lines.append("| " + " | ".join(_cell("" if c is None else c) for c in row) + " |")
                for _ in range(max(0, _table_rows(table_spec) - len(fixed_rows))):
                    lines.append("| " + " | ".join("(待填)" for _ in columns) + " |")
                lines.append("")
            lines.append("> [待人工复刻] 合并单元格/列宽等原表格式 markdown 管道无法表达, 须人工按招标文件原样复刻——已入人核清单。")
            lines.append("")
        if slot_type == "format_check":
            lines.append("> 人核项(签字/盖章/份数/页码), 不做确定性判定——已入人核清单, 终稿人工核签。")
            lines.append("")

        # 技术卷: 活条款挂接本槽位 → 渲染条目(标题 N.M 响应[clause_id], D2;
        # N 取预分配节号——撞号/无号已顺延去重, 全卷唯一; 正文=阶段4a 响应,
        # 无响应骨架回退待填占位)
        if volume == "technical":
            entries = [c for c in active_tech if linked_map.get(c["clause_id"]) == node["node_id"]]
            if entries:
                parent_num = section_numbers[node["node_id"]]
                for index, clause in enumerate(entries, 1):
                    _ensure_blank()
                    lines.extend(render_clause_entry(clause, f"{parent_num}.{index}", response=responses_by_id.get(clause["clause_id"])))

    return lines, anomalies


def _render_volume_tails(nodes: list[dict], volume: str, ctx: dict, lines: list[str]) -> None:
    """卷尾件——分册时挂在各文档最后一册末尾。

    孤儿条款兜底节: 仅 technical(活条款条目属技术正文); 扫描件清单: 两卷都渲染
    (image 槽在商务卷同样存在——回放实证 S-003 身份证扫描件挂商务卷, v4 重构曾
    误锁 technical-only, 该回归由 test_image_slot_scan_list 抓住)。
    """
    claimed = ctx["claimed"]
    active_tech = ctx["active_tech"]
    linked_map = ctx["linked_map"]
    responses_by_id = ctx["responses_by_id"]

    def _ensure_blank() -> None:
        if lines and lines[-1] != "":
            lines.append("")

    # 卷末兜底: 未挂接任何槽位的活条款 → 卷末专节渲染(逐条款条目零遗漏);
    # 节号在已占用集合之后顺延, 不与既有编号节撞号; 标题中性化(出处 sidecar 标注)
    if volume == "technical":
        orphans = [c for c in active_tech if c["clause_id"] not in linked_map]
        if orphans:
            parent_num = str(_next_free_number(claimed))
            _ensure_blank()
            lines.append(f"## {parent_num} {ORPHAN_SECTION_TITLE}")
            lines.append("")
            for index, clause in enumerate(orphans, 1):
                lines.extend(render_clause_entry(clause, f"{parent_num}.{index}", response=responses_by_id.get(clause["clause_id"])))

    # 扫描件清单(image 槽汇总; 图片不经 md 链路插入)
    image_nodes = [n for n in nodes if n["slot_type"] == "image"]
    if image_nodes:
        _ensure_blank()
        lines.extend(["## 扫描件清单(图片槽汇总)", "", "图片不经 md 链路插入: 终稿由用户在文档空间排版时插入扫描件。", "", "| 槽位 | 位置 | 要求 |", "| --- | --- | --- |"])
        lines.extend(f"| {n['node_id']} | {_cell(n['path'])} | {_cell((n.get('required_format') or {}).get('desc') or '')} |" for n in image_nodes)
        lines.append("")


def _chapter_groups(structure: list[dict], volume: str) -> list[list[dict]]:
    """镜像序章分组: structure 原序下连续同章键(path 首段)的同卷节点聚为一组。

    连续分组(非全局 groupby)保持招标大纲交错序——整体方案的商务章与技术占位章
    按招标文件原始顺序渲染(Revision 4 两文档拓扑, 用户域规则)。
    """
    nodes = [n for n in structure if n["volume"] == volume]
    groups: list[list[dict]] = []
    for node in nodes:
        key = booklets.chapter_of(node["path"])
        if not groups or booklets.chapter_of(groups[-1][-1]["path"]) != key:
            groups.append([node])
        else:
            groups[-1].append(node)
    return groups


def render_chapters_md(volume: str, structure: list[dict], clauses: list[dict], responses: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """按章渲染(volume 的章分组, v4 分册基础): 返回 ([{chapter, text}], anomalies)。

    技术卷卷尾件(孤儿节+扫描件清单)挂最后一章; 章文本字节级拼接 == 整卷渲染
    (render_volume_md 兼容包装依赖此性质)。
    """
    ctx = _volume_ctx(volume, structure, clauses, responses)
    out: list[dict] = []
    anomalies: list[dict] = []
    groups = _chapter_groups(structure, volume)
    for i, group in enumerate(groups):
        lines, group_anomalies = _render_nodes(group, volume, ctx)
        if i == len(groups) - 1:
            _render_volume_tails(group, volume, ctx, lines)
        anomalies.extend(group_anomalies)
        out.append({"chapter": booklets.chapter_of(group[0]["path"]), "text": "\n".join(lines).rstrip() + ("\n" if lines else "")})
    return out, anomalies


def render_volume_md(volume: str, structure: list[dict], clauses: list[dict], responses: list[dict] | None = None) -> tuple[str, list[dict]]:
    """整卷渲染(兼容包装): 章文本顺序拼接 == 原整卷单循环输出(字节级)。"""
    chapters, anomalies = render_chapters_md(volume, structure, clauses, responses)
    return "".join(c["text"] for c in chapters), anomalies


# ── 槽位注入(v4 T6c, 四类硬围栏域 P2: 报价数字/资质证号/招标原文——数字与证号
#    经 {{SLOT:key}} 占位由 build_output 从冻结态注入, 不经过 LLM 之手; geo D5
#    收窄移植, 畸形归一化+未知键硬错为 geo bug-3043 防线) ─────────────────────────
SLOTS_STATE_FILE = "slots.json"
# 槽位键含中文(业务键如"报价总额")——字符集 = 字母数字下划线连字符 + CJK
_SLOT_KEY = r"[A-Za-z0-9_\-一-鿿]+"
SLOT_TOKEN_RE = re.compile(r"\{\{SLOT:(" + _SLOT_KEY + r")\}\}")
# 畸形收形(geo bug-3043: 93 处穿透教训)——少一个闭括号且后面跟非}字符: {{SLOT:key}单位}
SLOT_DEFORM_CLOSE_RE = re.compile(r"\{\{SLOT:(" + _SLOT_KEY + r")\}(?!\})")
# 单开括号穿透: {SLOT:key}
SLOT_DEFORM_OPEN_RE = re.compile(r"(?<!\{)\{SLOT:(" + _SLOT_KEY + r")\}")


def load_slots(state_dir: Path) -> dict[str, str]:
    """装载槽位冻结值(state/slots.json, 形态 {"key": "显示值"}; 缺失→空表——
    槽位与 entities_whitelist 同类: 用户/业务确认数据, Agent 写入不签名)。"""
    path = state_dir / SLOTS_STATE_FILE
    if not path.is_file():
        return {}
    data = _load_json_file(path, SLOTS_STATE_FILE)
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise BuildOutputError(f"{SLOTS_STATE_FILE} 形态错误: 需为 {{\"key\": \"显示值\"}} 平面字典")
    return data


def normalize_slot_deformities(text: str) -> str:
    """畸形 SLOT 归一化(注入前): 收形后未知键才能走正常 unknown-key FAIL,
    畸形形态不得既不注入也不报错地静默穿透进交付物(geo bug-3043)。"""
    text = SLOT_DEFORM_CLOSE_RE.sub(r"{{SLOT:\1}}", text)
    text = SLOT_DEFORM_OPEN_RE.sub(r"{{SLOT:\1}}", text)
    return text


def inject_slots(text: str, slots: dict[str, str], source: str) -> str:
    """槽位注入+宽匹配残留防线: 未知键 → BuildOutputError(D5 硬错, 绝不静默);
    注入后残留任何 SLOT 形态(理论上不可能)同样硬错——围栏域文本零静默通道。"""
    working = normalize_slot_deformities(text)
    unknown = sorted({m.group(1) for m in SLOT_TOKEN_RE.finditer(working) if m.group(1) not in slots})
    if unknown:
        raise BuildOutputError(
            f"{source} 含未知槽位键 {unknown}——请在 state/{SLOTS_STATE_FILE} 补充冻结值(或修正占位键名); "
            "围栏域数值必须经槽位注入, 不得由 LLM 直写"
        )
    working = SLOT_TOKEN_RE.sub(lambda m: slots[m.group(1)], working)
    if "SLOT:" in working:
        raise BuildOutputError(f"{source} 槽位注入后仍残留 SLOT 形态——疑似畸形变体未收形, 请检查占位写法(唯一合法形态 {{{{SLOT:key}}}})")
    return working


def _chapter_stats(text: str) -> dict:
    """章级页数统计量(从渲染文本直接测得, 确定性): 字符/表格数/图片占位/表格行。"""
    rows = 0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and not set(s) <= set("|-: "):
            rows += 1
    return {
        "chars": len(text),
        "tables": text.count("\n| --- |") + text.count("\n| ---"),
        "images": text.count("[此处插入:"),
        "table_rows": rows,
    }


def _tech_placeholder_md(title: str, tech_ref: dict | None) -> str:
    """整体方案技术章占位页(Revision 4, 用户域规则): 逐字章标题 + 技术卷分册目录 +
    指引——零技术正文内联; 合并导出时按技术卷册组顺序拼装。"""
    lines = [
        f"# {title}",
        "",
        "> 本章为《技术卷》占位页: 技术标单独成卷交付(招标大纲中技术仅占一章, 其余",
        "> 为商务部分)。本卷不内联技术正文, 内容见《技术卷》各分册; 合并导出时按",
        "> 技术卷册组顺序拼装于本章位置。",
        "",
    ]
    if tech_ref and tech_ref["files"]:
        lines.extend(["技术卷分册目录:", "", "| 册 | 文件 | 章节范围 |", "| --- | --- | --- |"])
        for i, (filename, booklet) in enumerate(zip(tech_ref["files"], tech_ref["booklets"]), 1):
            span = " → ".join(booklet["chapters"])
            lines.append(f"| {i:02d} | {filename} | {span} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_doc_booklets(doc: str, structure: list[dict], clauses: list[dict], responses: list[dict] | None = None, tech_ref: dict | None = None, slots: dict[str, str] | None = None) -> dict:
    """两文档册集渲染(v4 Revision 4): 整体方案(商务全量+技术占位) / 技术卷(全量)。

    - 技术卷: technical 章全量渲染(卷尾件挂末册), 切册=booklets.plan_booklets。
    - 整体方案: structure 原序章分组(招标大纲交错序, 不重排)——commercial 组全量,
      technical 组渲染占位页(逐字章标题+技术卷分册目录+指引, **零技术正文内联**;
      卷尾件不进整体方案——孤儿节/扫描件清单属技术正文, 只在技术卷)。
    - slots(v4 T6c): 围栏域冻结值注入(未知键硬错, 畸形归一化先行)。
    返回 {"doc", "files", "contents"(文件名→md), "booklets", "warnings", "anomalies"}。
    """
    anomalies: list[dict] = []
    chapters: list[dict] = []
    if doc == "技术卷":
        groups, chapter_anomalies = render_chapters_md("technical", structure, clauses, responses)
        anomalies.extend(chapter_anomalies)
        chapters = [{"title": g["chapter"], "text": g["text"], **_chapter_stats(g["text"])} for g in groups]
    elif doc == "整体方案":
        ctx_comm = _volume_ctx("commercial", structure, clauses, responses)
        current_key: str | None = None
        bucket: list[dict] = []

        def _flush_bucket() -> None:
            nonlocal bucket
            if not bucket:
                return
            volume = bucket[0]["volume"]
            if volume == "commercial":
                lines, group_anomalies = _render_nodes(bucket, "commercial", ctx_comm)
                anomalies.extend(group_anomalies)
                text = "\n".join(lines).rstrip() + ("\n" if lines else "")
            else:
                # 技术章占位(Revision 4): 零正文内联; 卷尾件(孤儿节/扫描件清单)属
                # 技术正文, 不进整体方案
                text = _tech_placeholder_md(booklets.chapter_of(bucket[0]["path"]), tech_ref)
            chapters.append({"title": booklets.chapter_of(bucket[0]["path"]), "text": text, "volume": volume, **_chapter_stats(text)})
            bucket = []

        for node in structure:
            key = booklets.chapter_of(node["path"])
            if key != current_key:
                _flush_bucket()
                current_key = key
            bucket.append(node)
        _flush_bucket()
        # 商务卷尾件(扫描件清单)挂最后一个商务章——整体方案里商务 image 槽的清单
        # 不因分册丢失(v4 重构回归教训: test_image_slot_scan_list)
        comm_chapters = [c for c in chapters if c.get("volume") == "commercial"]
        if comm_chapters:
            tail_lines: list[str] = []
            _render_volume_tails(ctx_comm["nodes"], "commercial", ctx_comm, tail_lines)
            if tail_lines:
                last = comm_chapters[-1]
                glue = "" if last["text"].endswith("\n\n") else ("\n" if last["text"].endswith("\n") else "\n\n")
                last["text"] = last["text"] + glue + "\n".join(tail_lines).rstrip() + "\n"
                last.update(_chapter_stats(last["text"]))
    else:
        raise ValueError(f"未知文档: {doc}(合法: 整体方案/技术卷)")

    # 槽位注入(v4 T6c): 畸形归一化 → 未知键硬错 → 注入冻结值; 统计重算(注入改变字数)
    slot_map = slots or {}
    for c in chapters:
        c["text"] = inject_slots(c["text"], slot_map, f"{doc}/{c['title']}")
        c.update(_chapter_stats(c["text"]))

    booklets_plan, warnings = booklets.plan_booklets(
        [{"title": c["title"], "chars": c["chars"], "tables": c["tables"], "table_rows": c["table_rows"], "images": c["images"]} for c in chapters]
    )
    files = booklets.assign_filenames(doc, booklets_plan)
    # 册内容 = 章文本顺序拼接(章文本各自以 \n 结尾, 拼接即连续; 不加分隔防破坏字节幂等)
    contents: dict[str, str] = {}
    cursor = 0
    for filename, plan in zip(files, booklets_plan):
        count = len(plan["chapters"])
        chunk = chapters[cursor:cursor + count]
        cursor += count
        contents[filename] = "".join(c["text"] for c in chunk)
    return {
        "doc": doc,
        "files": files,
        "contents": contents,
        "booklets": booklets_plan,
        "warnings": warnings,
        "anomalies": anomalies,
    }


# =============================================================================
# ③ 偏离表 / ④ 覆盖率报表 / ⑥ 人核清单
# =============================================================================


def deviation_rows(clauses: list[dict]) -> list[dict]:
    """偏离表口径: 活条款 且 (强制条款 或 响应状态=deviation)。"""
    return [c for c in clauses if _is_active(c) and (c["class"] == "mandatory" or c["response_status"] == "deviation")]


def render_deviation_md(rows: list[dict], structure: list[dict]) -> str:
    """渲染偏离表——按招标文件模板拆商务/技术两张(用户决策): category=technical 入
    技术偏离表, 其余(commercial/qualification/format/service)入商务偏离表; rows 由调用方
    经 deviation_rows(clauses) 预计算一次(渲染与摘要共用, 不重算)。"""
    lines = [
        "# 偏离表",
        "",
        "> 口径: 仅强制条款(class=mandatory)与偏离项(response_status=deviation)入表——",
        "> 强制条款即使已响应也须声明零偏离; 其余条款不入表。superseded/voided 历史条款除外。",
        "> 按招标文件模板拆两张: category=technical 入技术偏离表, 其余入商务偏离表。",
        "",
    ]

    def _table(title: str, section_rows: list[dict]) -> None:
        lines.extend([f"## {title}", "", "| 条款ID | 类别 | 响应状态 | 招标要求 | 原文锚点 | 偏离说明 |", "| --- | --- | --- | --- | --- | --- |"])
        for clause in section_rows:
            requirement = _cell(clause.get("requirement") or "")
            quote = _cell((clause.get("source_ref") or {}).get("quote") or "")
            lines.append(f"| {clause['clause_id']} | {CLASS_LABELS.get(clause['class'], clause['class'])} | {clause['response_status']}({STATUS_LABELS.get(clause['response_status'], '')}) | {requirement} | {quote} | (待填) |")
        if not section_rows:
            lines.append("| (无) | | | | | |")
        lines.append("")

    _table("技术偏离表(technical 条款)", [c for c in rows if c.get("category") == "technical"])
    _table("商务偏离表(其余条款: commercial/qualification/format/service)", [c for c in rows if c.get("category") != "technical"])

    # 招标偏离表模板槽(path 含"偏离"的 table 槽): 模板原文已由商务卷镜像预填, 指回防两处填报
    dev_templates = [n for n in structure if n["slot_type"] == "table" and "偏离" in n["path"]]
    if dev_templates:
        lines.extend(["", "> 招标模板原文(商务偏离表/技术偏离表的列头与固定文字)见商务卷对应章节镜像(template_text 预填), 终稿按模板原样填报:", *(f"> - {n['node_id']} {_cell(n['path'])}" for n in dev_templates), ""])
    return "\n".join(lines)


def compute_coverage(clauses: list[dict]) -> dict:
    """覆盖率口径: 已响应=compliant+deviation; 待确认=draft+pending_confirm; 未分配=unassigned。"""
    active = [c for c in clauses if _is_active(c)]

    def count(statuses: tuple[str, ...]) -> int:
        return sum(1 for c in active if c["response_status"] in statuses)

    return {
        "total": len(active),
        "responded": count(RESPONDED_STATUSES),
        "pending": count(PENDING_STATUSES),
        "unassigned": count(("unassigned",)),
        "superseded": sum(1 for c in clauses if c.get("superseded_by") is not None),
        "voided": sum(1 for c in clauses if c.get("voided")),
    }


def _bucket(status: str) -> str:
    if status in RESPONDED_STATUSES:
        return "已响应"
    if status in PENDING_STATUSES:
        return "待确认"
    return "未分配"


def render_coverage_md(clauses: list[dict], coverage: dict, structure: list[dict]) -> str:
    lines = [
        "# 覆盖率报表",
        "",
        "> 口径: 已响应=compliant+deviation; 待确认=draft+pending_confirm; 未分配=unassigned;",
        "> superseded/voided 为历史条款, 除外列示不计入清单总数。",
        "",
        "| 指标 | 数量 |",
        "| --- | --- |",
        f"| 清单总数(活条款) | {coverage['total']} |",
        f"| 已响应(compliant+deviation) | {coverage['responded']} |",
        f"| 待确认(draft+pending_confirm) | {coverage['pending']} |",
        f"| 未分配(unassigned) | {coverage['unassigned']} |",
        f"| 除外: superseded | {coverage['superseded']} |",
        f"| 除外: voided | {coverage['voided']} |",
        "",
        "## 逐条款状态附录",
        "",
        "| 条款ID | 类别 | 分类 | 响应状态 | 口径桶 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for clause in clauses:
        if not _is_active(clause):
            continue
        status = clause["response_status"]
        lines.append(f"| {clause['clause_id']} | {CLASS_LABELS.get(clause['class'], clause['class'])} | {clause.get('category', '')} | {status}({STATUS_LABELS.get(status, '')}) | {_bucket(status)} |")
    if coverage["total"] == 0:
        lines.append("| (无活条款) | | | | |")

    # 槽位编排表(v2 sidecar): 双卷净化后槽位元数据的归属地——不进交付双卷正文
    # (回放实证: 槽位类型/格式要求/填写状态/关联条款 bullet 曾被当正文写进交付物)。
    clauses_by_id = {c["clause_id"]: c for c in clauses}
    lines.extend(["", "## 槽位编排表(sidecar——槽位元数据不进交付双卷正文)", "", "| 节点 | 卷 | 位置 | 槽位类型 | 格式要求 | 填写状态(现算) | 关联条款 |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for node in structure:
        if node["slot_type"] == "group":
            fill, reason = "—", "结构组"
        else:
            fill, reason = derive_fill_status(node)
        origin = " / 自拟" if node.get("origin") == "self_created" else ""
        labels = "; ".join(_linked_clause_labels(node, clauses_by_id))
        slot_label = f"{SLOT_TYPE_LABELS.get(node['slot_type'], node['slot_type'])}{origin}"
        desc_label = _cell((node.get("required_format") or {}).get("desc") or "")
        lines.append(f"| {node['node_id']} | {node['volume']} | {_cell(node['path'])} | {slot_label} | {desc_label} | {fill}({reason}) | {_cell(labels)} |")
    if not structure:
        lines.append("| (无) | | | | | | |")
    lines.extend(
        [
            "",
            f"> 技术卷「{ORPHAN_SECTION_TITLE}」节 = 未挂接任何格式槽的活条款({'/'.join(ENTRY_CATEGORIES)})兜底;",
            "> 关联条款列标注(不存在) = 悬挂外键, 同时计入摘要 anomalies 待人工改链。",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def render_checklist_md(structure: list[dict], responses: list[dict] | None = None) -> tuple[str, dict]:
    """人核清单: format_check 项(签字/盖章/份数/页码) + [待人工复刻]表格槽 + 生成内容人核。"""
    format_checks = [n for n in structure if n["slot_type"] == "format_check"]
    replica_tables = [n for n in structure if n["slot_type"] == "table"]
    lines = [
        "# 人核清单",
        "",
        "> 以下项**不进确定性判定**, 必须人工逐项核签(确认门2 终稿复核, skill 不做最终承诺):",
        "> format_check 项(签字/盖章/份数/页码)全部人核; [待人工复刻]表格槽=管道表格无法表达合并单元格/列宽。",
        "",
        "## 一、format_check 人核项(签字/盖章/份数/页码)",
        "",
        "| 节点 | 位置 | 要求 |",
        "| --- | --- | --- |",
    ]
    for node in format_checks:
        lines.append(f"| {node['node_id']} | {_cell(node['path'])} | {_cell((node.get('required_format') or {}).get('desc') or '')} |")
    if not format_checks:
        lines.append("| (无) | | |")
    lines.extend(["", "## 二、[待人工复刻] 表格槽(合并单元格/列宽须按招标文件原样复刻)", "", "| 节点 | 位置 | 列头 | 行数 | 格式要求 |", "| --- | --- | --- | --- | --- |"])
    for node in replica_tables:
        spec = (node.get("required_format") or {}).get("table_spec") or {}
        columns = "/".join(str(c) for c in (spec.get("columns") or []))
        lines.append(f"| {node['node_id']} | {_cell(node['path'])} | {_cell(columns)} | {_table_rows(spec)} | {_cell((node.get('required_format') or {}).get('desc') or '')} |")
    if not replica_tables:
        lines.append("| (无) | | | | |")

    # 模板原文比对(用户决策): template_text 照抄非确定性 → 终稿前逐字比对招标原文
    template_nodes = [n for n in structure if template_text_of(n) is not None]
    lines.extend(["", "## 三、模板原文比对(照抄非确定性, 终稿前逐字比对招标文件)", "", "| 节点 | 位置 | 字数 |", "| --- | --- | --- |"])
    for node in template_nodes:
        lines.append(f"| {node['node_id']} | {_cell(node['path'])} | {len(template_text_of(node))} |")
    if not template_nodes:
        lines.append("| (无) | | |")

    # 生成内容人核(v2 反馈3/4): 阶段4a 三模式生成的响应正文——web 引用逐条核实
    # (引用不进交付正文, 只在此留痕) + needs_human_verify 项供源留痕复核。
    verify_items = [r for r in (responses or []) if r.get("needs_human_verify") or r.get("citations")]
    lines.extend(["", "## 四、生成内容人核(阶段4a 生成响应: 编造/仿写/引用逐条批量确认——P4 政策)", "", "| 条款 | 供源 | 人核标记 | 引用标题 | URL | 引用片段 |", "| --- | --- | --- | --- | --- | --- |"])
    for item in verify_items:
        mark = "需人核" if item.get("needs_human_verify") else "-"
        citations = item.get("citations") or []
        if citations:
            def _cite_locator(c: dict) -> str:
                return (c.get("url") or "") or (("doc:" + c["source_doc"]) + (f"@{c['quote_span']}" if c.get("quote_span") else "")) if c.get("source_doc") else (c.get("url") or "")

            lines.extend(f"| {item.get('clause_id')} | {item.get('source_mode')} | {mark} | {_cell(c.get('title') or '')} | {_cell(_cite_locator(c))} | {_cell(c.get('quote') or '')} |" for c in citations)
        else:
            lines.append(f"| {item.get('clause_id')} | {item.get('source_mode')} | {mark} | - | - | - |")
    if not verify_items:
        lines.append("| (无) | | | | | |")
    lines.append("")
    return "\n".join(lines), {"format_check": len(format_checks), "replica_tables": len(replica_tables), "template_compare": len(template_nodes), "generated_content": len(verify_items)}


# =============================================================================
# ⑤ 实体一致性 lint(确定性 diff; 白名单=LLM 辅助抽取+人工确认, 非确定性)
# =============================================================================


def _entity_norm(value: str) -> str:
    """实体值归一化: 去全部空白 + casefold——"S7-1500V2.3" 与 "S7-1500 V2.3" 同值。"""
    return re.sub(r"\s+", "", value).casefold()


def _mask_whitelist(text: str, values: set[str]) -> str:
    """白名单值以非字哨兵掩蔽(长值优先)——掩蔽后的文本里白名单公司不再可被候选
    提取吸收, 贪婪前缀污染("见东智…有限公司")与相邻公司合并由此根除。"""
    masked = text
    for value in sorted(values, key=len, reverse=True):
        masked = masked.replace(value, _MASK_SENTINEL)
    return masked


def _extract_entity_candidates(text: str, values: set[str]) -> list[tuple[str, str]]:
    r"""确定性候选提取(类型, 候选值); spec_version 用正则, company 用后缀位扫描。

    company 扫描在白名单掩蔽后的文本上进行: ①找全部工商后缀位置(同一结束位置取
    最长后缀——"股份有限公司"含"有限公司", 只认外层); ②从后缀起点向前走 \w 最多
    COMPANY_MAX_PREFIX 字(前缀 <2 字跳过); ③前导连接/引介词修剪显示值; ④保序去重。
    """
    candidates: list[tuple[str, str]] = [("spec_version", m) for m in SPEC_VERSION_RE.findall(text)]
    masked = _mask_whitelist(text, values)
    claimed_ends: set[int] = set()  # 已按最长后缀认领的结束位置, 防内层后缀重复提取
    for suffix in sorted(COMPANY_SUFFIXES, key=len, reverse=True):
        start = 0
        while True:
            found = masked.find(suffix, start)
            if found < 0:
                break
            end = found + len(suffix)
            start = end
            if end in claimed_ends:
                continue
            claimed_ends.add(end)
            index = found
            while index > 0 and found - index < COMPANY_MAX_PREFIX and _WORD_CHAR_RE.match(masked[index - 1]):
                index -= 1
            prefix_start = index
            if found - prefix_start < 2:
                continue  # 字号前缀不足 2 字——不足以构成公司名
            candidate = masked[prefix_start:end]
            for token in COMPANY_LEADING_TRIM:  # 循环修剪前导连接/引介词(多字词优先)
                while candidate.startswith(token):
                    candidate = candidate[len(token) :]
            candidates.append(("company", candidate))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for etype, candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append((etype, candidate))
    return unique


def _candidate_whitelisted(candidate: str, values: set[str]) -> bool:
    """候选命中白名单判定: 精确相等或归一化相等(无空格写法同值)。"""
    normalized = _entity_norm(candidate)
    return any(candidate == v or normalized == _entity_norm(v) for v in values)


def run_entity_lint(
    clauses: list[dict],
    whitelist: dict | None,
    extra_texts: dict[str, str] | None = None,
) -> tuple[list[dict], dict]:
    """白名单 diff 全部 evidence_ref、引用片段与交付册全文(v4 T4 扩面)。

    hits = 白名单实体值出现次数(按归一化子串计数, 同一字段出现两次计 2);
    flagged = 确定性候选提取中不在白名单的(疑似上一项目残留)→[待核对]+异常。
    extra_texts(v4): {来源标签: 全文}——交付册全文扫描(编造正文正是白名单外
    实体的主要藏身处, 引用片段扫描覆盖不到); 标签用文件名, 命中记 field=来源。
    """
    values: set[str] = {e["value"] for e in (whitelist or {}).get("entities", [])}
    norm_values = {value: _entity_norm(value) for value in values}
    hits: dict[str, int] = {}
    flagged: list[dict] = []

    def _scan(field: str, text: str, owner: str) -> None:
        if not isinstance(text, str) or not text.strip():
            return
        normalized_text = _entity_norm(text)
        for value, norm_value in norm_values.items():
            count = normalized_text.count(norm_value)
            if count:
                hits[value] = hits.get(value, 0) + count
        for etype, candidate in _extract_entity_candidates(text, values):
            if _candidate_whitelisted(candidate, values):
                continue
            message = f"{owner} {field} 含白名单外实体 {candidate!r}({etype})——疑似上一项目残留, [待核对]"
            flagged.append({"kind": "entity_unverified", "clause_id": owner, "field": field, "type": etype, "value": candidate, "context": text[:200], "message": message})

    for clause in clauses:
        skeleton = clause.get("response_skeleton") or {}
        texts = (("evidence_ref", skeleton.get("evidence_ref")), ("引用片段", (clause.get("source_ref") or {}).get("quote")))
        for field, text in texts:
            _scan(field, text, clause["clause_id"])
    for label, text in (extra_texts or {}).items():
        _scan(f"交付册全文({label})", text, label)
    return flagged, hits


def render_lint_md(whitelist: dict | None, flagged: list[dict], hits: dict) -> str:
    lines = [
        "# 实体一致性 lint 报告",
        "",
        "> **LLM辅助抽取白名单，非确定性**: 实体白名单由 LLM 抽取+人工确认(确认门1 锁定)。",
        "> 本 lint 本身是确定性 diff(模式提取候选 ∩ 白名单比对); 可确定性提取的类型仅",
        "> company(工商后缀)/spec_version(型号+V版本)——person/project 等无确定性模式,",
        "> 只做白名单命中统计, 无法被动发现白名单外残留, 覆盖范围受此限制。",
    ]
    if whitelist is None:
        lines.append(">")
        lines.append("> **白名单缺失**: entities_whitelist.json 不存在, 按空集 diff(全部候选进[待核对])——确认门1 未锁定或文件被移动。")
    else:
        lines.append(">")
        lines.append(f"> 白名单锁定: {whitelist.get('locked_at', '(未知)')}({whitelist.get('source', '')})/ 共 {len(whitelist.get('entities', []))} 项实体。")
    lines.extend(
        [
            "",
            "## 白名单命中统计(evidence_ref 与引用片段)",
            "",
        ]
    )
    if hits:
        type_by_value = {e["value"]: e["type"] for e in (whitelist or {}).get("entities", [])}
        lines.extend(["| 实体值 | 类型 | 出现次数 |", "| --- | --- | --- |"])
        lines.extend(f"| {_cell(value)} | {type_by_value.get(value, '')} | {count} |" for value, count in sorted(hits.items()))
    else:
        lines.append("(无命中——白名单实体未出现在任何 evidence_ref/引用片段)")
    lines.extend(["", "## [待核对] 白名单外实体(疑似上一项目残留)", ""])
    if flagged:
        lines.extend(["| 条款/来源 | 字段 | 提取类型 | 提取值 | 上下文 |", "| --- | --- | --- | --- | --- |"])
        lines.extend(f"| {f['clause_id']} | {f['field']} | {f['type']} | {_cell(f['value'])} | {_cell(f['context'])} |" for f in flagged)
    else:
        lines.append("(无——未发现白名单外实体)")
    lines.append("")
    # 候选白名单通道(eng-review 4A): 确认属本项目合法实体后, 加入 entities_whitelist
    # (用户确认→Agent 写入, 白名单不签名)重跑 build 放行——不回 stage4a 重写。
    unique_candidates = sorted({f["value"] for f in flagged if f["type"] == "company"})
    if unique_candidates:
        lines.extend([
            "## 候选白名单(确认后一键入册)",
            "",
            "> 以上提取值若属本项目合法实体(招标文件提及/分包方等), 用户确认后加入",
            "> `state/entities_whitelist.json`(type=company)并重跑 build_output.py 即放行,",
            "> 无需回阶段4a 重写; 若属上一项目残留, 按上文[待核对]处置(重写响应)。",
            "",
            "```json",
            "  {\"type\": \"company\", \"value\": \"<确认的实体全称>\"}",
            "```",
            "",
            "候选值: " + "、".join(unique_candidates),
            "",
        ])
    return "\n".join(lines)


# =============================================================================
# 渲染管线 + CLI
# =============================================================================


def _entity_gate_state(state_dir: Path, flagged: list[dict]) -> dict:
    """实体门熔断状态(eng-review 4A): 轮次按 flagged 值集指纹比对——同集连犯递增,
    集合变化重置为 1(改对了或换了残留都算新轮起点)。

    rounds<2 → 硬门生效(blocked): 不写交付凭据且作废旧凭据(9A), 回 stage4a 重写
    或确认候选白名单后重跑; rounds>=2 → 转人工(escalated): 放行凭据, 把关责任移交
    人核清单/lint 报告——对齐 geo consistency FAIL 两轮处置规约, 防白名单缺项造成
    确定性死循环。轮次持久化在 workspace last_build.json(entity_gate 键; workspace
    不在签名登记范围, state/ 只读纪律不受影响)。
    """
    signature = None
    if flagged:
        sig_source = json.dumps(sorted({f["value"] for f in flagged}), ensure_ascii=False)
        signature = hashlib.sha256(sig_source.encode("utf-8")).hexdigest()
    prev: dict = {}
    receipt_path = state_dir.parent / "last_build.json"
    if receipt_path.is_file():
        try:
            prev = json.loads(receipt_path.read_text(encoding="utf-8")).get("entity_gate") or {}
        except (json.JSONDecodeError, OSError):
            prev = {}
    if not flagged:
        rounds = 0
    elif prev.get("flagged_signature") == signature:
        rounds = int(prev.get("rounds") or 0) + 1
    else:
        rounds = 1
    return {
        "flagged_signature": signature,
        "rounds": rounds,
        "blocked": bool(flagged) and rounds < 2,
        "escalated": bool(flagged) and rounds >= 2,
    }


def _sweep_stale_outputs(out_dir: Path, new_deliverables: set[str]) -> list[str]:
    """上一轮交付清场(外部声音 11A, 目录级幂等): 只删旧 manifest 列名文件——

    重切册后册数/文件名全变, 旧册残留在 outputs/ 会触发自家交付门"杂散 .md 整单
    拒"反控; 清场=按 manifest 确定性删除(脚本清场不违铁律9)。manifest 缺失/不可
    解析 → 跳过清场(首轮构建合法态), 返回告警行。防御: 只删 out_dir 直属普通文件。
    """
    manifest_path = out_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        # v3→v4 升级边角: 旧双卷(商务卷/技术卷.md)无 manifest 可依, 但文件名固定
        # 无歧义——确定性移除, 防其以"杂散 .md"身份触发自家交付门反控(11A 目录幂等)
        removed_legacy: list[str] = []
        for legacy in LEGACY_OUTPUT_FILES:
            target = out_dir / legacy
            if target.is_file():
                target.unlink()
                removed_legacy.append(legacy)
        note = f"清场跳过: {MANIFEST_NAME} 缺失(首轮构建)"
        return [note + (f"; 移除 v3 遗留双卷 {', '.join(removed_legacy)}" if removed_legacy else "")]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [f"清场跳过: {MANIFEST_NAME} 不可解析——不做遗留文件删除"]
    deleted: list[str] = []
    for name in manifest.get("deliverables") or []:
        if not isinstance(name, str) or name in new_deliverables:
            continue
        target = out_dir / name
        if target.parent == out_dir and target.is_file():
            target.unlink()
            deleted.append(name)
    return [f"清场删除上一轮遗留 {len(deleted)} 文件: {', '.join(sorted(deleted))}"] if deleted else []


def run_build(state_dir: Path, out_dir: Path) -> int:
    """读状态(只读) → 两文档册集渲染(v4) → 清场 → 原子写盘 → 交付凭据/构建回执
    → stdout 单行 JSON 摘要; 返回退出码。"""
    # 读盘前校验权威状态签名(回放实证 bfa917ce: 脚本外直写/rm 后下游只报远处症状)
    guard_problems = state_guard.verify_state_files(state_dir)
    if guard_problems:
        raise BuildOutputError("权威状态文件签名校验失败(疑似脚本外直写/误删):\n  - " + "\n  - ".join(guard_problems))
    clauses = load_clauses(state_dir)
    structure = load_structure(state_dir)
    whitelist = load_whitelist(state_dir)
    responses = load_responses(state_dir)  # 阶段4a 权威态; 缺失 → 骨架模式回退

    anomalies: list[dict] = []
    if whitelist is None:
        anomalies.append({"kind": "whitelist_missing", "message": "entities_whitelist.json 缺失, lint 按空集 diff(全部候选进[待核对])——确认门1 未锁定白名单或文件被移动"})

    # 两文档册集(v4 Revision 4): 技术卷先渲(整体方案技术占位页需其分册目录)
    slots = load_slots(state_dir)  # v4 T6c: 围栏域冻结值(缺失=空表, 未知键在注入期硬错)
    tech_doc = render_doc_booklets(DOC_TECH, structure, clauses, responses, slots=slots)
    overall_doc = render_doc_booklets(DOC_OVERALL, structure, clauses, responses, tech_ref=tech_doc, slots=slots)
    anomalies.extend(tech_doc["anomalies"])
    anomalies.extend(overall_doc["anomalies"])
    dev_rows = deviation_rows(clauses)  # 渲染与摘要共用一份, 不对同一数据计算两次
    deviation_md = render_deviation_md(dev_rows, structure)
    coverage = compute_coverage(clauses)
    coverage_md = render_coverage_md(clauses, coverage, structure)
    checklist_md, checklist_counts = render_checklist_md(structure, responses)
    # 实体门 v4(T4): 扫描面扩到交付册全文(编造正文=白名单外实体主要藏身处)
    scan_texts: dict[str, str] = {**overall_doc["contents"], **tech_doc["contents"]}
    flagged, hits = run_entity_lint(clauses, whitelist, extra_texts=scan_texts)
    anomalies.extend(flagged)
    entity_gate = _entity_gate_state(state_dir, flagged)
    lint_md = render_lint_md(whitelist, flagged, hits)

    index_md = booklets.render_index(
        [
            {"doc": DOC_OVERALL, "files": overall_doc["files"], "booklets": overall_doc["booklets"]},
            {"doc": DOC_TECH, "files": tech_doc["files"], "booklets": tech_doc["booklets"]},
        ],
        extra_notes=["槽位编排与围栏域分布见 覆盖率报表.md(槽位编排表); 分册告警见构建摘要 booklets 字段"],
    )
    outputs: dict[str, str] = {**overall_doc["contents"], **tech_doc["contents"], INDEX_FILE: index_md}
    outputs["偏离表.md"] = deviation_md
    outputs["覆盖率报表.md"] = coverage_md
    outputs["人核清单.md"] = checklist_md
    outputs["实体lint报告.md"] = lint_md
    deliverables = sorted(outputs)

    sweep_warnings = _sweep_stale_outputs(out_dir, set(deliverables))
    for name in deliverables:
        atomic_write_text(out_dir / name, outputs[name])

    # 交付凭据(v4 WP-2.3 bid 侧): skill/version/deliverables——T3 通用化后由
    # harness present_file_tool 消费(整单判定)。实体门(9A): blocked → 不写凭据且
    # 作废旧凭据/标记(交付门 STATUS_MISSING 全禁 .md); escalated → 放行+转人工。
    whitelist_path = state_dir / "entities_whitelist.json"
    whitelist_sha256 = state_guard.sha256_file(whitelist_path) if whitelist_path.is_file() else None
    files_sha = {name: hashlib.sha256(outputs[name].encode("utf-8")).hexdigest() for name in deliverables}
    if entity_gate["blocked"]:
        stale_manifest = out_dir / MANIFEST_NAME
        if stale_manifest.is_file():
            stale_manifest.unlink()
        stale_marker = out_dir / ".delivery-contract"
        if stale_marker.is_file():
            stale_marker.unlink()
        sweep_warnings.append(
            f"实体门硬门生效(第 {entity_gate['rounds']} 轮): 白名单外实体未处置, 本轮不写交付凭据——"
            "处置路径: 确认候选白名单入册(见 实体lint报告.md)或回 stage4a 重写响应后重跑"
        )
    manifest = {
        "skill": "bid-proposal-writing",
        "version": MANIFEST_VERSION,
        "deliverables": deliverables,
        # 确认门工件白名单(WP-2.3 aux_md): 门1 条款清单/门2 补遗diff表由 extract/merge
        # 阶段写 outputs/ 并在门2(build 后)经 present_files 呈现——非管线 build 产物但
        # 合法呈现, 由本管线在此申报(harness 交付门放行集=deliverables∪aux_md)。
        "aux_md": ["条款清单.md", "补遗diff表.md"],
        "files": files_sha,
        "docs": {
            DOC_OVERALL: {"booklets": len(overall_doc["files"]), "pages_est": booklets.total_pages(overall_doc["booklets"])},
            DOC_TECH: {"booklets": len(tech_doc["files"]), "pages_est": booklets.total_pages(tech_doc["booklets"])},
        },
        "whitelist_sha256": whitelist_sha256,
    }
    if not entity_gate["blocked"]:
        atomic_write_text(out_dir / MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        # 交付契约标记(bug-2225/3109): build 成功即激活本线程交付门——此后非管线 .md
        # present/下载/同步一律整单拒(清场+凭据保证 deliverables 集合自洽)。
        atomic_write_text(out_dir / ".delivery-contract", "{}\n")

    # 构建回执(回放实证 fd49b085: snapshot 靠 workspace/last_build.json 检测构建状态)。
    # 回执写在 workspace 层(与 project_snapshot.json 同级, 不动 state/ 权威态、不签名),
    # 内容确定性(out_dir+册集 sha256+白名单消费 hash), 重跑字节级幂等。
    # whitelist_sha256(v3, DEC-5): 白名单不签名(agent-written), 其"最近一次被消费"的
    # 留痕在此冻结——snapshot 比对当前 hash 即可确定性发现消费后改动(turn7 类违规)。
    receipt = {
        "out_dir": str(out_dir),
        "files": files_sha,
        "whitelist_sha256": whitelist_sha256,
        "entity_gate": entity_gate,
    }
    atomic_write_text(state_dir.parent / "last_build.json", json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    responded_ids = {r.get("clause_id") for r in responses}
    summary = {
        "written": deliverables,
        "booklets": {
            DOC_OVERALL: {"count": len(overall_doc["files"]), "pages_est": booklets.total_pages(overall_doc["booklets"]), "warnings": overall_doc["warnings"]},
            DOC_TECH: {"count": len(tech_doc["files"]), "pages_est": booklets.total_pages(tech_doc["booklets"]), "warnings": tech_doc["warnings"]},
        },
        "sweep": sweep_warnings,
        "coverage": coverage,
        "deviation_rows": len(dev_rows),
        "template_prefill_count": sum(1 for n in structure if template_text_of(n) is not None),
        "responses_rendered": sum(1 for c in clauses if _is_active(c) and c.get("category") in ENTRY_CATEGORIES and c["clause_id"] in responded_ids),
        "fixed_rows_replicated": sum(_fixed_row_count(n) for n in structure),
        "self_created_sections": sum(1 for n in structure if n.get("origin") == "self_created"),
        "human_checklist": checklist_counts,
        "lint": {"flagged": len(flagged), "entity_hits": len(hits), "whitelist_missing": whitelist is None},
        "entity_gate": entity_gate,
        "whitelist_sha256": whitelist_sha256,
        "anomalies": anomalies,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK if not anomalies else EXIT_ANOMALY


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回进程退出码(见模块 docstring 退出码约定)。"""
    parser = argparse.ArgumentParser(
        prog="build_output.py",
        description="投标方案编写·阶段4 交付渲染(v4 两文档册集): 整体方案=structure 镜像(商务全量+技术占位页) / 技术卷=逐条款条目(标题嵌 clause_id, D2) 分册 + 0-总目录索引 + 四张副表 / delivery_manifest(无 LLM, 不做 Word 转换)",
        epilog="示例: python build_output.py --state-dir state --out output",
    )
    parser.add_argument("--state-dir", required=True, help="状态目录(只读: clauses.json / structure.json / entities_whitelist.json; 派生字段现算不落盘)")
    parser.add_argument("--out", required=True, help="输出目录(两文档册集+索引+副表 md, 临时文件+os.replace 原子写盘, 重跑字节级幂等)")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse 用法错误默认 SystemExit(2), 与 ingest 的 OCR 分流退出码撞号——统一改道
        # EXIT_ERROR; --help 等正常退出(code 0)原样放行(同 merge_addenda.py 约定)。
        if not exc.code:
            return EXIT_OK
        print(f"[build_output] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}); 用法错误归退出码 1, 2 已保留给 ingest 的 OCR 分流(用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR

    try:
        return run_build(Path(args.state_dir), Path(args.out))
    except BuildOutputError as exc:
        print(f"[build_output] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        # 写盘 I/O 失败统一转退出码 1(终审 R5, 对齐 ingest 既定契约): --out 指向已存在
        # 普通文件 → atomic_write_text 的 mkdir FileExistsError。此前以裸 traceback 逃出
        # main(), 编排方拿到裸栈而非干净的 [build_output] 错误行——main 统一转退出码是
        # 模块自己的契约(原子性由临时文件+finally 清理保证, 不受影响)。
        print(f"[build_output] 错误: 文件读写失败({exc.__class__.__name__}): {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
