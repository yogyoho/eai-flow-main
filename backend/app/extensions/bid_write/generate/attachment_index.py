"""SK-AI 附件索引装配(批二十 M1-h,EAI-CUSTOM 2026-11-13)——§2.4 兑现:
attachment_requirements × material.entities(名归一匹配)→索引行;未命中→
**待补占位行不静默省略**(漏报直接相关设计点),负证据(retrieved/match_key/
nearest)随 pending_items 行进(CMN-005 面);待补行 page/fingerprint/source
齐备(AI-004/006/007 校验面不豁免占位行);「待补」词只进 status 列不进名称列
(AI 铁律);volumes→V1.. 分册行 copies=min_copies(AI-005 面);目录=正文标题
同源列表(AI-008 面);指纹=审查端指纹字典类型名匹配(审查端 fingerprints.load
零改动复用),未命中→要求名代位(非 unknown_type;类型精化=人工指定后重跑面)。
页码=page_estimates 面注入(排版输入),缺→顺序占位;total_pages=估值 max。
纯函数零 IO 零时钟。"""

from __future__ import annotations

from app.extensions.bid_review.engine.fingerprints import load as load_fingerprints


def _norm(s) -> str:
    return "".join(str(s or "").split()).lower()


def _match_entity(name: str, entities: dict) -> tuple[str | None, str]:
    """(命中实体键, 最近候选名)——名归一精确匹配;未命中取首实体名为最近候选。"""
    n = _norm(name)
    for k, e in (entities or {}).items():
        if _norm((e or {}).get("name")) == n:
            return k, str((e or {}).get("name") or "")
    nearest = next((str((e or {}).get("name") or "") for e in (entities or {}).values()), "无匹配实体")
    return None, nearest


def _fingerprint_for(name: str) -> str:
    """指纹字典类型名匹配(名含类型或类型含名);未命中→要求名代位。"""
    n = _norm(name)
    for t in load_fingerprints():
        tn = _norm(t)
        if tn and (tn in n or n in tn):
            return t
    return _norm(name) or "unmatched"


def build_attachment_index(attachment_requirements: list | None, volume_specs: list | None, material: dict | None, sections: list[dict] | None, *, page_estimates: dict | None = None, total_pages: int | None = None) -> dict:
    entities = (material or {}).get("entities") or {}
    est = page_estimates or {}
    sec_codes = [str(s.get("code") or "sec:1") for s in (sections or [])] or ["sec:1"]
    items: list[dict] = []
    pending: list[dict] = []
    for r in attachment_requirements or []:
        name = str(r.get("name") or "").strip()
        no = str(r.get("no") or "").strip()
        hit, nearest = _match_entity(name, entities)
        page = est.get(no) if isinstance(est.get(no), int) else len(items) + 1
        if hit is not None:
            status = "ready"
            fingerprint = str((entities.get(hit) or {}).get("type") or _fingerprint_for(name))
        else:
            status = "待补"
            fingerprint = _fingerprint_for(name)
            pending.append({
                "item": name,
                "status": "待补",
                "negative_evidence": {
                    "retrieved": "material.entities 全库名归一检索",
                    "match_key": f"name={name}",
                    "nearest": nearest,
                },
            })
        items.append({
            "no": no,
            "name": name,
            "page": page,
            "copies": int(r.get("min_count") or 1),
            "type_fingerprint": fingerprint,
            "source": sec_codes[min(len(sec_codes) - 1, len(items))],
            "status": status,
        })
    for vi, v in enumerate(volume_specs or [], 1):
        vno = f"V{vi}"
        items.append({
            "no": vno,
            "name": str(v.get("name") or "").strip(),
            "page": est.get(vno) if isinstance(est.get(vno), int) else 1,
            "copies": int(v.get("min_copies") or 1),
            "type_fingerprint": "volume",
            "source": sec_codes[0],
            "status": "ready",
        })
    names = [i["name"] for i in items]
    pages = [i["page"] for i in items if isinstance(i["page"], int)]
    total = total_pages if isinstance(total_pages, int) and total_pages >= max(pages or [1]) else max(pages or [1])
    ref_nos = "、".join(f"附件{i['no']}" for i in items if i["no"] and not i["no"].startswith("V"))
    return {
        "items": items,
        "total_pages": total,
        "body_text": f"本卷共{len(items)}项,详见{ref_nos}。" if ref_nos else f"本卷共{len(items)}项。",
        "toc_titles": list(names),
        "body_headings": list(names),
        "pending_items": pending,
    }
