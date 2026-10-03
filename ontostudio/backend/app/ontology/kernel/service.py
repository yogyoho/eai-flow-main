"""kernel 服务门面（P5）——REST/MCP 统一入口.

进程内单例：OxStore（ONTOSTUDIO_KERNEL_PATH 持久化，缺省内存）+ registry 热重载 +
规则集（YAML + 内置链规则 + sameAs 传播）。
refresh() 编排：schema 重编 → owlrl 闭包 → CONSTRUCT 派生（防抖由调用方负责）。
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.ontology.kernel.cq import load_cqs, run_cqs
from app.ontology.kernel.infer import InferStats, compute_entailment, refresh_schema
from app.ontology.kernel.loader import load_doc_graph_rows
from app.ontology.kernel.rules import (
    BUILTIN_SAMEAS_PROPAGATION,
    builtin_chain_rules,
    load_rules,
    run_all_rules,
)
from app.ontology.kernel.store import ASSERTED_GRAPH, OxStore
from app.ontology.registry import get_registry

# 合法 IRI（防注入：溯源端点把 s/p/o 直接拼进 SPARQL 尖括号字面量）
_IRI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:[^\s<>\"{}|^`\\]*$")


class KernelService:
    def __init__(self) -> None:
        self.kernel_path = os.environ.get("ONTOSTUDIO_KERNEL_PATH")
        self.store = OxStore(self.kernel_path) if self.kernel_path else OxStore()

    def refresh(self, min_confidence: float = 0.7, dry: bool = False) -> InferStats:
        """schema 重编 → 闭包 → 派生全量重算。

        dry=试算（F6）：跳过 schema 重编、闭包只算不写、规则只计数——全程零落盘。
        停用规则（F8）不参与重算。
        """
        registry = get_registry()
        disabled = self._disabled_rules()
        all_rules = [r for r in self._all_rules(registry) if r.name not in disabled]
        if not dry:
            refresh_schema(self.store, registry)
        stats = compute_entailment(self.store, min_confidence=min_confidence, write=not dry)
        if dry:
            stats.rule_counts = {
                r.name: len(list(self.store._store.query(r.construct))) for r in all_rules
            }
        else:
            stats.rule_counts = run_all_rules(self.store, all_rules)
            self._append_history(min_confidence, stats)
        return stats

    def _all_rules(self, registry) -> list:  # noqa: ANN001 - Registry
        """规则全集 = YAML + registry 链生成 + 内置 sameAs（refresh 与溯源共用）。"""
        return load_rules() + builtin_chain_rules(registry) + [BUILTIN_SAMEAS_PROPAGATION]

    def load_ontology(self, payload: dict, domain: str = "eia") -> dict:
        """四类目标抽取结果（extract_ontology 输出形态）写入断言图.

        entities: [{etype, name, attrs?, confidence?}]；relations: [{predicate, subject, object}]；
        可选 chapters 树 + report_name（① 章节结构实体化）。实体 uuid = uuid5 确定性，重复装载幂等。
        """
        import uuid as uuid_mod

        from app.ontology.kernel.compile import collect_vocabularies
        from app.ontology.kernel.graph_ops import add_relation, upsert_entity
        from app.ontology.kernel.loader import etype_class_map

        registry = get_registry()
        vocab = collect_vocabularies(registry)[domain]
        classes = etype_class_map(registry, domain)

        name_iri: dict[str, str] = {}
        entities = list(payload.get("entities", []))
        chapter_rels: list[dict] = []
        report_name = payload.get("report_name")
        if report_name:
            report_iri = upsert_entity(
                self.store,
                vocab,
                class_name="Report",
                entity_uuid=uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, "eia-report:" + report_name),
                etype="report",
                canonical_name=report_name,
                confidence=0.95,
            )
            name_iri[report_name] = report_iri
        for ch in payload.get("chapters", []):
            ch_name = ("第" + str(ch.get("no", "")) + "章 " + str(ch.get("title", ""))).strip()
            ch_iri = upsert_entity(
                self.store,
                vocab,
                class_name="Chapter",
                entity_uuid=uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, "eia-chapter:" + ch_name),
                etype="chapter",
                canonical_name=ch_name,
                confidence=0.9,
            )
            name_iri[ch_name] = ch_iri
            entities.append({"etype": "chapter", "name": ch_name})
            if report_name:
                chapter_rels.append({"predicate": "has_chapter", "subject": report_name, "object": ch_name})
            for sec in ch.get("sections", []):
                sec_name = (str(sec.get("no", "")) + " " + str(sec.get("title", ""))).strip()
                sec_iri = upsert_entity(
                    self.store,
                    vocab,
                    class_name="Section",
                    entity_uuid=uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, "eia-section:" + sec_name),
                    etype="section",
                    canonical_name=sec_name,
                    confidence=0.9,
                )
                name_iri[sec_name] = sec_iri
                entities.append({"etype": "section", "name": sec_name})
                chapter_rels.append({"predicate": "has_subsection", "subject": ch_name, "object": sec_name})

        inserted = 0
        for e in entities:
            etype = e["etype"]
            if etype not in classes:
                continue
            iri = upsert_entity(
                self.store,
                vocab,
                class_name=classes[etype],
                entity_uuid=uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, "eia:" + etype + ":" + e["name"]),
                etype=etype,
                canonical_name=e["name"],
                confidence=float(e.get("confidence", 0.85)),
                attrs=e.get("attrs"),
            )
            name_iri[e["name"]] = iri
            inserted += 1

        relations = list(payload.get("relations", [])) + chapter_rels
        rel_count = 0
        skipped: list[str] = []
        for r in relations:
            s_iri = name_iri.get(r["subject"])
            o_iri = name_iri.get(r["object"])
            if not s_iri or not o_iri:
                skipped.append(str(r["subject"]) + "->" + str(r["object"]))
                continue
            try:
                add_relation(
                    self.store,
                    vocab,
                    relation_uuid=uuid_mod.uuid4(),
                    subject_iri=s_iri,
                    predicate=r["predicate"],
                    object_iri=o_iri,
                    confidence=float(r.get("confidence", 0.8)),
                )
                rel_count += 1
            except Exception:  # noqa: BLE001 - 单行弹性（谓词越域等历史数据）
                skipped.append(str(r["subject"]) + "->" + str(r["object"]))
        return {"entities": inserted, "relations": rel_count, "skipped": skipped}

    def rule_sources(self) -> list[dict]:
        """F1 规则清单 + F8 启用状态（enabled 由 rules_state.json overlay 合成）。"""
        from app.ontology.kernel.rules import (
            BUILTIN_SAMEAS_PROPAGATION,
            builtin_chain_rules,
            load_rules,
        )

        registry = get_registry()
        disabled = self._disabled_rules()
        return [
            {"name": r.name, "construct": r.construct, "origin": origin, "enabled": r.name not in disabled}
            for origin, group in (
                ("yaml", load_rules()),
                ("builtin", [BUILTIN_SAMEAS_PROPAGATION]),
                ("chain", builtin_chain_rules(registry)),
            )
            for r in group
        ]

    # ---- F8 规则启停（状态 overlay：kernel 数据卷 rules_state.json，与定义分离）----

    def _rules_state_path(self) -> Path | None:
        return Path(self.kernel_path) / "rules_state.json" if self.kernel_path else None

    def _disabled_rules(self) -> set[str]:
        path = self._rules_state_path()
        if not path or not path.exists():
            return set()
        try:
            return set(json.loads(path.read_text(encoding="utf-8")).get("disabled", []))
        except Exception:  # noqa: BLE001 - 状态文件损坏视为全启用（fail-open 到可用态）
            return set()

    def set_rule_enabled(self, name: str, enabled: bool) -> dict:
        """启停规则并即时生效：启用=单规则重算恢复派生；停用=清空对应派生图。"""
        import re

        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError("规则名不合法")
        path = self._rules_state_path()
        if not path:
            raise ValueError("内核为内存模式，规则状态不持久")
        state: dict = {}
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                state = {}
        disabled = set(state.get("disabled", []))
        if enabled:
            disabled.discard(name)
        else:
            disabled.add(name)
        state["disabled"] = sorted(disabled)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        rule = next((r for r in self._all_rules(get_registry()) if r.name == name), None)
        if rule is None:
            raise KeyError(name)
        if enabled:
            from app.ontology.kernel.rules import run_rule

            count = run_rule(self.store, rule)
        else:
            self.store.clear_graph(f"graph:derived:{name}")
            count = 0
        return {"rule": name, "enabled": enabled, "count": count}

    # ---- F9 推理历史 ----

    def _history_path(self) -> Path | None:
        return Path(self.kernel_path) / "infer_history.jsonl" if self.kernel_path else None

    def _append_history(self, min_confidence: float, stats: InferStats) -> None:
        path = self._history_path()
        if not path:
            return
        try:
            row = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "min_conf": min_confidence,
                "input_triples": stats.input_triples,
                "filtered_low_confidence": stats.filtered_low_confidence,
                "entailment_triples": stats.entailment_triples,
                "rule_counts": stats.rule_counts,
                "duration_ms": stats.duration_ms,
            }
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 - 历史失败不影响主流程
            pass

    def infer_history(self, limit: int = 20) -> list[dict]:
        """近 N 次落盘重算（倒序）；前端做相邻 diff。"""
        path = self._history_path()
        if not path or not path.exists():
            return []
        rows: list[dict] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001 - 坏行跳过
                    pass
        except Exception:  # noqa: BLE001
            return []
        return list(reversed(rows[-limit:]))

    def infer_last(self) -> dict:
        """内核当前推理状态（页面初始化读路径，零重算）。

        派生/闭包计数 = 实时数图（含启停/装载后的真实状态）；
        输入/过滤/耗时/时间戳 = 最近一次落盘重算记录（infer_history 首行）。
        """
        registry = get_registry()
        counts: dict[str, int] = {}
        for r in self._all_rules(registry):
            rows = self.store.query(
                "SELECT (COUNT(*) AS ?n) WHERE { GRAPH <graph:derived:" + r.name + "> { ?s ?p ?o } }"
            )
            counts[r.name] = int(rows[0]["n"] or 0) if rows else 0
        ent = self.store.query(
            "SELECT (COUNT(*) AS ?n) WHERE { GRAPH <graph:entailment> { ?s ?p ?o } }"
        )
        entailment = int(ent[0]["n"] or 0) if ent else 0
        last = self.infer_history(1)
        head = last[0] if last else {}
        return {
            "entailment_triples": entailment,
            "rule_counts": counts,
            "input_triples": head.get("input_triples", 0),
            "filtered_low_confidence": head.get("filtered_low_confidence", 0),
            "duration_ms": head.get("duration_ms", 0),
            "min_conf": head.get("min_conf"),
            "ran_at": head.get("ts"),
        }

    async def orphans(self) -> dict:
        """内核孤儿实体（治理）：asserted 图实体 IRI 中，dg_entities 无对应行者。

        实体 IRI 形态 = {ns}id/{uuid}；uuid 不在 dg_entities（或 IRI 非该形态）即候选孤儿
        ——装载为增量并集（只增不删），SQL 侧删除的行会以孤儿形式永驻内核并持续参与推理。
        """
        from pyoxigraph import NamedNode
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.config import DatabaseConfig

        # subjects 用 SPARQL DISTINCT（trace/explain 同款通道，实测可见全部实体）；
        # quads_for_pattern 迭代在此处存在行为差异（漏实体 → 孤儿恒 0 的教训）
        rows = self.store.query(
            "SELECT DISTINCT ?s WHERE { GRAPH <" + ASSERTED_GRAPH + "> { ?s ?p ?o } }"
        )
        subjects = {r["s"] for r in rows}
        engine = create_async_engine(DatabaseConfig.from_env().url)
        try:
            async with engine.connect() as conn:
                rows = (await conn.execute(text("SELECT id::text FROM dg_entities"))).all()
        finally:
            await engine.dispose()
        known = {r[0] for r in rows}
        # 治理范围限定：eia 域实体 IRI 形态 {eia_ns}id/{uuid}——mention/合同价等其它形态
        # 节点不属 dg_entities 治理域，不算孤儿（首轮误判 21709 全孤儿的教训）
        prefix = "https://ontology.eai-flow.com/eia#id/"
        orphans: list[str] = []
        for s in sorted(subjects):
            if s.startswith(prefix) and s[len(prefix):].lower() not in known:
                orphans.append(s)
        return {"total_subjects": len(subjects), "orphan_count": len(orphans), "orphans": orphans}

    def purge_orphans(self, iris: list[str]) -> dict:
        """精确清除指定实体的全部 asserted 三元组（主体/客体两侧）；派生图待全量重算刷新。"""
        from pyoxigraph import NamedNode

        gn = NamedNode(ASSERTED_GRAPH)
        removed = 0
        valid = [i for i in iris if _IRI_RE.match(i)]
        for iri in valid:
            node = NamedNode(iri)
            for q in list(self.store._store.quads_for_pattern(node, None, None, gn)):
                self.store._store.remove(q)
                removed += 1
            for q in list(self.store._store.quads_for_pattern(None, None, node, gn)):
                self.store._store.remove(q)
                removed += 1
        return {"entities": len(valid), "removed_triples": removed}

    def run_cqs(self) -> list[dict]:
        """CQ 验收（F5）：cq.yaml 逐条 ASK 真跑，FAIL 不阻断（推理工作台页数据源）。"""
        return run_cqs(self.store, load_cqs())

    def _labels_for(self, iris: list[str]) -> dict[str, str]:
        """IRI → canonical_name（匹配任意域 attr/canonical_name 谓词）；无名不进表。"""
        if not iris:
            return {}
        iris_list = ", ".join("<" + i + ">" for i in iris)
        rows = self.store.query(
            "SELECT ?e ?l WHERE { ?e ?pp ?l . FILTER(STRENDS(STR(?pp), 'attr/canonical_name'))"
            " FILTER(?e IN (" + iris_list + ")) }"
        )
        return {r["e"]: r["l"] for r in rows if r.get("l")}

    def rule_derivations(self, name: str, *, limit: int = 200, offset: int = 0) -> dict:
        """graph:derived:<name> 内容（F2 下钻）：派生三元组分页 + 总数 + 实体名映射（可读性）。"""
        import re

        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError("规则名不合法")
        graph = f"graph:derived:{name}"
        total_rows = self.store.query(
            f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}"
        )
        total = int(total_rows[0]["n"] or 0) if total_rows else 0
        rows = self.store.query(
            f"SELECT ?s ?p ?o WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} "
            f"ORDER BY ?s ?p ?o LIMIT {int(limit)} OFFSET {int(offset)}"
        )
        labels = self._labels_for([r["s"] for r in rows] + [r["o"] for r in rows])
        return {"total": total, "labels": labels, "rows": rows}

    def rule_trace(self, name: str, s: str, p: str, o: str) -> dict:
        """F3 溯源：派生三元组 (s, p, o) 的触发基础事实。

        分派：链规则（trace=谓词 IRI 序列）→ 逐段路径查询；qualified_bidder →
        资质满足清单；sameas_propagation → sameAs 链接 + 规范实体事实。
        """
        for iri in (s, p, o):
            if not _IRI_RE.match(iri):
                raise ValueError(f"IRI 不合法: {iri[:60]}")
        rule = next((r for r in self._all_rules(get_registry()) if r.name == name), None)
        if rule is None:
            raise KeyError(name)
        if name == "qualified_bidder":
            return self._trace_requirements(s, o)
        if name == "sameas_propagation":
            return self._trace_sameas(s, p, o)
        trace = rule.trace
        if not trace or len(trace) < 2:
            raise ValueError("该规则未定义溯源链（trace）")
        mids = [f"m{i}" for i in range(len(trace) - 1)]
        patterns = ["<" + s + "> <" + trace[0] + "> ?" + mids[0]]
        for i in range(1, len(trace) - 1):
            patterns.append("?" + mids[i - 1] + " <" + trace[i] + "> ?" + mids[i])
        patterns.append("?" + mids[-1] + " <" + trace[-1] + "> <" + o + ">")
        rows = self.store.query(
            "SELECT " + " ".join("?" + m for m in mids)
            + " WHERE { GRAPH <" + ASSERTED_GRAPH + "> { " + " . ".join(patterns) + " } }"
        )
        evidence: list[dict] = []
        for row in rows:
            nodes = [s] + [row[m] for m in mids] + [o]
            for i, pred in enumerate(trace):
                evidence.append({"s": nodes[i], "p": pred, "o": nodes[i + 1]})
        labels = self._labels_for(sorted({e for ev in evidence for e in (ev["s"], ev["o"])}))
        return {"rule": name, "kind": "chain", "satisfied": bool(rows), "evidence": evidence, "labels": labels}

    _P_BIDDER_OF = "https://ontology.eai-flow.com/doc_graph#predicate/bidder_of_project"
    _P_REQUIRES = "https://ontology.eai-flow.com/doc_graph#predicate/requires_qualification"
    _P_HOLDS = "https://ontology.eai-flow.com/doc_graph#predicate/bidder_holds_qualification"

    def _trace_requirements(self, bidder: str, project: str) -> dict:
        """qualified_bidder 溯源：项目资质要求 × 投标人持有 对照清单。"""
        req = self.store.query(
            "SELECT ?q WHERE { GRAPH <" + ASSERTED_GRAPH
            + "> { <" + project + "> <" + self._P_REQUIRES + "> ?q } }"
        )
        held = {
            r["q"]
            for r in self.store.query(
                "SELECT ?q WHERE { GRAPH <" + ASSERTED_GRAPH
                + "> { <" + bidder + "> <" + self._P_HOLDS + "> ?q } }"
            )
        }
        evidence = [{"s": bidder, "p": self._P_BIDDER_OF, "o": project}]
        for r in req:
            evidence.append({"s": project, "p": self._P_REQUIRES, "o": r["q"]})
            if r["q"] in held:
                evidence.append({"s": bidder, "p": self._P_HOLDS, "o": r["q"]})
        satisfied = bool(req) and all(r["q"] in held for r in req)
        labels = self._labels_for([bidder, project] + [r["q"] for r in req])
        return {
            "rule": "qualified_bidder",
            "kind": "requirements",
            "satisfied": satisfied,
            "evidence": evidence,
            "labels": labels,
            "details": [
                {"qualification": r["q"], "held": r["q"] in held} for r in req
            ],
        }

    def _trace_sameas(self, alias: str, p: str, o: str) -> dict:
        """sameas_propagation 溯源：sameAs 链接 + 规范实体的对应事实。"""
        owl_sameas = "http://www.w3.org/2002/07/owl#sameAs"
        rows = self.store.query(
            "SELECT ?canonical WHERE { GRAPH <graph:alignment> { { <" + alias
            + "> <" + owl_sameas + "> ?canonical } UNION { ?canonical <"
            + owl_sameas + "> <" + alias + "> } } }"
        )
        evidence: list[dict] = []
        for r in rows:
            canonical = r["canonical"]
            evidence.append({"s": alias, "p": owl_sameas, "o": canonical})
            facts = self.store.query(
                "SELECT ?f WHERE { GRAPH <" + ASSERTED_GRAPH
                + "> { <" + canonical + "> <" + p + "> <" + o + "> } LIMIT 1 }"
            )
            if facts:
                evidence.append({"s": canonical, "p": p, "o": o})
        return {
            "rule": "sameas_propagation",
            "kind": "sameas",
            "satisfied": bool(evidence),
            "evidence": evidence,
        }

    def rule_explain_miss(self, name: str, s: str, o: str) -> dict:
        """F4 反事实：期望派生未出现时，沿 trace 逐段走断言图，报第一处断裂。

        satisfied=True 表示路径实际存在（结论应可派生，若缺失请全量重算）。
        """
        for iri in (s, o):
            if not _IRI_RE.match(iri):
                raise ValueError(f"IRI 不合法: {iri[:60]}")
        rule = next((r for r in self._all_rules(get_registry()) if r.name == name), None)
        if rule is None:
            raise KeyError(name)
        if name == "qualified_bidder":
            res = self._trace_requirements(s, o)
            details = res.get("details") or []
            missing = [d["qualification"] for d in details if not d["held"]]
            if res["satisfied"]:
                res["hint"] = "全部资质满足——结论应可派生（若缺失请全量重算）"
            elif not details:
                res["hint"] = "项目未声明任何资质要求（requires_qualification 缺失）"
            else:
                res["hint"] = f"缺少资质 {len(missing)} 项: " + ", ".join(missing)
            return res
        if name == "sameas_propagation":
            res = self._trace_sameas(s, "", o)
            res["hint"] = (
                "无 sameAs 候选链接（graph:alignment 为空）" if not res["evidence"]
                else "候选链接存在但规范实体无对应事实"
            )
            return res
        trace = rule.trace
        if not trace or len(trace) < 2:
            raise ValueError("该规则未定义溯源链（trace），反事实仅支持链规则")
        reached = s
        evidence: list[dict] = []
        for i, pred in enumerate(trace):
            rows = self.store.query(
                "SELECT ?n WHERE { GRAPH <" + ASSERTED_GRAPH
                + "> { <" + reached + "> <" + pred + "> ?n } } LIMIT 1"
            )
            if not rows:
                return {
                    "rule": name,
                    "kind": "chain",
                    "satisfied": False,
                    "missing_at": i,
                    "missing_pred": pred,
                    "reached": reached,
                    "evidence": evidence,
                    "labels": self._labels_for([reached, s, o]),
                    "hint": (
                        "链首缺实例——" + s[:80] + " 无 <" + pred.rsplit("/", 1)[-1]
                        + "> 边（owlrl prp-spo2 对此类静默零推断，建议补该事实或换参照实体）"
                        if i == 0
                        else "第 " + str(i + 1) + " 段缺后续事实：<" + pred.rsplit("/", 1)[-1]
                        + "> 在 " + reached[:80] + " 处断裂"
                    ),
                }
            evidence.append({"s": reached, "p": pred, "o": rows[0]["n"]})
            reached = rows[0]["n"]
        if reached == o:
            return {
                "rule": name,
                "kind": "chain",
                "satisfied": True,
                "evidence": evidence,
                "labels": self._labels_for(sorted({e for ev in evidence for e in (ev["s"], ev["o"])} | {s, o})),
                "hint": "路径实际存在——结论应可派生（若缺失请全量重算）",
            }
        return {
            "rule": name,
            "kind": "chain",
            "satisfied": False,
            "missing_at": len(trace) - 1,
            "missing_pred": trace[-1],
            "reached": reached,
            "evidence": evidence,
            "labels": self._labels_for(sorted({e for ev in evidence for e in (ev["s"], ev["o"])} | {s, o, reached})),
            "hint": "链尾到达 " + reached[:80] + "，非期望客体 " + o[:80],
        }

    def validate(self) -> dict:
        """SHACL 报告 + 国标五项符合性（校验中心页数据源）。跑完即记历史（F9 同构）。"""
        from app.ontology.kernel.conformance import run_conformance
        from app.ontology.kernel.validate import run_shacl

        registry = get_registry()
        report = run_shacl(self.store, registry)
        conformance = run_conformance(self.store, registry, shacl_report=report)
        self._append_validate_history(report)
        return {
            "shacl": {"conforms": report.conforms, "violations": report.violations, "duration_ms": report.duration_ms},
            "conformance": [asdict(c) for c in conformance],
        }

    def _append_validate_history(self, report) -> None:  # noqa: ANN001 - ValidationReport
        path = Path(self.kernel_path) / "validate_history.jsonl" if self.kernel_path else None
        if not path:
            return
        try:
            row = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "conforms": report.conforms,
                "errors": sum(1 for v in report.violations if not (v.get("severity") or "").endswith("Warning")),
                "warnings": sum(1 for v in report.violations if (v.get("severity") or "").endswith("Warning")),
                "duration_ms": report.duration_ms,
            }
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 - 历史失败不影响主流程
            pass

    def validate_history(self, limit: int = 20) -> list[dict]:
        """校验历史（F9 同构）：近 N 次 SHACL 运行（倒序）。"""
        path = Path(self.kernel_path) / "validate_history.jsonl" if self.kernel_path else None
        if not path or not path.exists():
            return []
        rows: list[dict] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            return []
        return list(reversed(rows[-limit:]))

    def export(self, fmt: str = "turtle", graphs: str = "all") -> str | dict:
        """图真源 → 标准序列化（国标 §5.3 交付物）。graphs: all|schema|asserted|entailment。"""

        from rdflib import Graph

        from app.ontology.kernel.export import to_jsonld, to_turtle

        wanted = {"graph:schema", "graph:asserted", "graph:entailment"} if graphs == "all" else {"graph:" + graphs}
        g = Graph()
        for quad in self.store._store.quads_for_pattern(None, None, None, None):
            if quad.graph_name.value in wanted:
                g.add(_rdflib_triple(quad))
        if fmt == "json-ld":
            return to_jsonld(g)
        return to_turtle(g)

    async def load_from_sql(self, dsn: str | None = None, domain: str | None = None) -> dict:
        """SQL 测试数据装载（兼任主系统桥接器）。"""
        from app.config import DatabaseConfig
        from app.ontology.kernel.loader import read_doc_graph_rows

        dsn = dsn or DatabaseConfig.from_env().url
        entity_rows, relation_rows, mention_rows = await read_doc_graph_rows(dsn)
        stats = load_doc_graph_rows(
            self.store,
            get_registry(),
            entity_rows=entity_rows,
            relation_rows=relation_rows,
            mention_rows=mention_rows,
            domain=domain,
        )
        return asdict(stats)


def _rdflib_triple(quad) -> tuple:  # noqa: ANN001
    from pyoxigraph import BlankNode, NamedNode
    from pyoxigraph import Literal as OxLiteral
    from rdflib import BNode, Literal, URIRef

    def conv(term):  # noqa: ANN001
        if isinstance(term, NamedNode):
            return URIRef(term.value)
        if isinstance(term, BlankNode):
            return BNode(term.value)
        if isinstance(term, OxLiteral):
            if term.language is not None:
                return Literal(term.value, lang=term.language)
            datatype = URIRef(term.datatype.value) if term.datatype is not None else None
            return Literal(term.value, datatype=datatype)
        return Literal(term.value)

    return conv(quad.subject), conv(quad.predicate), conv(quad.object)


_kernel: KernelService | None = None
_lock = threading.Lock()


def get_kernel() -> KernelService:
    global _kernel
    with _lock:
        if _kernel is None:
            _kernel = KernelService()
        return _kernel
