"""PS 报价表校验器(批二十 M1,EAI-CUSTOM 2026-11-13)——SK-PS-001..010 逐条按
注册表 expr 兑现(plan 契约表)。行匹配键=id 优先 name 兜底(strip+lower 归一,
沿 L1-011 codes() set_eq 口径的执行器侧简化:ids 生成期已稳定,无需全量归一)。"""

from __future__ import annotations

from decimal import Decimal

from app.extensions.bid_write.executor.amount_cn import cn_to_num, num_to_cn
from app.extensions.bid_write.executor.models import Outcome
from app.extensions.bid_write.executor.validators import need, norm_text, opt, register
from app.extensions.bid_write.executor.wordscan import hit_message, scan_text, words_for

_ABNORMAL_LOW_RATIO = Decimal("0.7")  # 低于历史均价 7 折告警(D2)
_PRICE_MODES = ("含税", "不含税")
_PRICE_VAGUE_WORDS = words_for("price_vague")


def _row_key(row: dict) -> str:
    """行匹配键:id 优先,name 兜底(strip+lower);双空=空串(调用方按缺标识处理)。"""
    return (norm_text(row.get("id")) or norm_text(row.get("name"))).lower()


def _ps_rows(products: dict) -> list[dict]:
    return [r for r in (opt(need(products, "price_sheet"), "rows") or []) if isinstance(r, dict)]


@register("SK-PS-001")
def _ps001_boq_coverage(ctx: dict, adef) -> Outcome:
    """expr:tender.boq_items 每行均有对应输出行且无多余行(双向集合差)。"""
    products = need(ctx, "products")
    tender_rows = [r for r in (opt(need(ctx, "tender"), "tender.boq_items") or []) if isinstance(r, dict)]
    out_rows = _ps_rows(products)
    tkeys = {_row_key(r) for r in tender_rows}
    okeys = {_row_key(r) for r in out_rows}
    if "" in tkeys or "" in okeys:
        return Outcome(status="FAIL", level=adef.level, message="存在缺 id/name 标识的清单行")
    missing, extra = tkeys - okeys, okeys - tkeys
    if missing or extra:
        parts = [f"缺行: {', '.join(sorted(missing))}"] if missing else []
        parts += [f"多余行: {', '.join(sorted(extra))}"] if extra else []
        return Outcome(status="FAIL", level=adef.level, message=f"清单覆盖不一致({len(okeys)}/{len(tkeys)}): " + "; ".join(parts))
    return Outcome(status="PASS", message=f"清单 {len(tkeys)} 行全覆盖无多余")


@register("SK-PS-002")
def _ps002_qty_unit(ctx: dict, adef) -> Outcome:
    """expr:逐行 qty/unit 与招标清单相等(不得改数量;qty 数值比,unit 归一比)。"""
    products = need(ctx, "products")
    tender_map = {_row_key(r): r for r in (opt(need(ctx, "tender"), "tender.boq_items") or []) if isinstance(r, dict)}
    offenders: list[str] = []
    for row in _ps_rows(products):
        t = tender_map.get(_row_key(row))
        if t is None:
            continue  # 覆盖面归 PS-001
        if Decimal(str(row.get("qty"))) != Decimal(str(t.get("qty"))):
            offenders.append(f"{_row_key(row)}: qty {row.get('qty')} ≠ {t.get('qty')}")
        if norm_text(row.get("unit")) != norm_text(t.get("unit")):
            offenders.append(f"{_row_key(row)}: unit {row.get('unit')!r} ≠ {t.get('unit')!r}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"数量/单位不一致 {len(offenders)} 行: {'; '.join(offenders[:8])}")
    return Outcome(status="PASS", message=f"{'、'.join(str(r.get('qty')) for r in _ps_rows(products))} 数量单位与清单一致")


@register("SK-PS-003")
def _ps003_totals(ctx: dict, adef) -> Outcome:
    """expr:明细合计=汇总表=开标一览表=投标函金额(明细表唯一事实源,派生表全
    同步)。任一面缺→CtxMissing(不得静默跳过)。"""
    products = need(ctx, "products")
    detail = Decimal(str(need(need(products, "price_sheet"), "detail_total")))
    summary = Decimal(str(need(need(products, "price_sheet"), "summary_total")))
    open_total = Decimal(str(need(need(products, "price_sheet"), "open_letter_total")))
    letter = Decimal(str(need(need(need(products, "bid_letter"), "slots"), "total_amount_num")))
    faces = {"明细合计": detail, "汇总表": summary, "开标一览表": open_total, "投标函": letter}
    bad = {k: v for k, v in faces.items() if v != detail}
    if bad:
        detail_s = " = ".join(f"{k} {v}" for k, v in faces.items())
        return Outcome(status="FAIL", level=adef.level, message="四表加总不一致: " + detail_s)
    return Outcome(status="PASS", message=f"四表加总一致({detail})")


@register("SK-PS-004")
def _ps004_amount_cn(ctx: dict, adef) -> Outcome:
    """expr:报价表大写金额与数字互转相等(固定函数 amount_cn,含零/整/角分规则;
    非 canonical=FAIL,双向都要过)。human_action=null(处置自动闭环)。"""
    ps = need(ctx, "products").get("price_sheet") or {}
    cn = norm_text(need(ps, "amount_cn"))
    detail = Decimal(str(need(ps, "detail_total")))
    try:
        parsed = cn_to_num(cn)
    except ValueError as exc:
        return Outcome(status="FAIL", level=adef.level, message=f"大写金额非 canonical: {exc}")
    canonical = num_to_cn(detail)
    bad = []
    if parsed != detail:
        bad.append(f"cn_to_num({cn})={parsed} ≠ {detail}")
    if canonical != cn:
        bad.append(f"num_to_cn({detail})={canonical} ≠ 「{cn}」")
    if bad:
        return Outcome(status="FAIL", level=adef.level, message="金额互转不一致: " + "; ".join(bad))
    return Outcome(status="PASS", message=f"大写小写互转一致({cn})")


@register("SK-PS-005")
def _ps005_price_mode(ctx: dict, adef) -> Outcome:
    """expr:全表 price_mode 唯一(含税/不含税),税率一致或分行标注(行级缺省=
    继承表级;行级与表级冲突=FAIL)。"""
    ps = need(ctx, "products").get("price_sheet") or {}
    mode = norm_text(need(ps, "price_mode"))
    if mode not in _PRICE_MODES:
        return Outcome(status="FAIL", level=adef.level, message=f"price_mode 非法: {mode!r}(合法:含税/不含税)")
    offenders: list[str] = []
    for row in _ps_rows(ctx.get("products") or {}):
        rm = norm_text(row.get("price_mode"))
        if rm and rm != mode:
            offenders.append(f"{_row_key(row)}: 行级 {rm!r} ≠ 表级 {mode!r}")
        rt = row.get("tax_rate")
        if rt is not None and Decimal(str(rt)) != Decimal(str(opt(ps, "tax_rate"))):
            offenders.append(f"{_row_key(row)}: 税率 {rt} ≠ 表级 {opt(ps, 'tax_rate')}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"口径不一致 {len(offenders)} 处: {'; '.join(offenders[:8])}")
    return Outcome(status="PASS", message=f"口径统一({mode},税率 {opt(ps, 'tax_rate')})")


@register("SK-PS-006")
def _ps006_max_price(ctx: dict, adef) -> Outcome:
    """expr:total ≤ tender.max_price;限价未抽到→D2 SKIPPED(no_signal)标注
    「限价未确认」,不做假合规。"""
    tender = opt(ctx, "tender") or {}
    max_price = opt(tender, "tender.max_price")
    if max_price is None:
        return Outcome(status="SKIPPED", level="D2", message="限价未确认(招标文件未抽到 max_price)")
    products = need(ctx, "products")
    detail = Decimal(str(need(need(products, "price_sheet"), "detail_total")))
    cap = Decimal(str(max_price))
    if detail > cap:
        return Outcome(status="FAIL", level=adef.level, message=f"报价 {detail} 超最高限价 {cap}")
    return Outcome(status="PASS", message=f"报价 {detail} ≤ 限价 {cap}")


@register("SK-PS-007")
def _ps007_unit_price(ctx: dict, adef) -> Outcome:
    """expr:所有行 unit_price > 0(缺失保留空单元格标注,不导出不补——空/零/
    负都算违例,逐行点名)。"""
    products = need(ctx, "products")
    offenders: list[str] = []
    for row in _ps_rows(products):
        up = row.get("unit_price")
        try:
            ok = up is not None and Decimal(str(up)) > 0
        except (TypeError, ValueError, ArithmeticError):
            ok = False
        if not ok:
            offenders.append(f"{_row_key(row)}: {up!r}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"空/非正单价 {len(offenders)} 行(保留空格不导出): {'; '.join(offenders[:8])}")
    return Outcome(status="PASS", message=f"{len(_ps_rows(products))} 行单价全为正")


@register("SK-PS-008")
def _ps008_replay(ctx: dict, adef) -> Outcome:
    """expr:同输入重算逐单元格相等(重放=计算内核产出,执行器只读 pre 标志,
    deterministic=False);价格表无行=空跑诚实 PASS(注记)。"""
    pre = need(ctx, "pre")
    equal = need(pre, "ps_replay_equal")
    ps = opt(need(ctx, "products"), "price_sheet") or {}
    if not ps.get("rows"):
        return Outcome(status="PASS", deterministic=False, note="价格表无行,重放核验空跑(诚实零)")
    if equal is not True:
        return Outcome(status="FAIL", level=adef.level, deterministic=False, message="报价重放不一致(ps_replay_equal=False)")
    return Outcome(status="PASS", deterministic=False, message="报价重放逐单元格一致")


@register("SK-PS-009")
def _ps009_vague_price(ctx: dict, adef) -> Outcome:
    """expr:报价说明模糊调价类词扫描 0 命中;**无调价机制时命中升 D0**,
    有机制维持 D1(price_adjust_mechanism=True)。"""
    products = need(ctx, "products")
    ps = need(products, "price_sheet")
    note = norm_text(opt(ps, "note"))
    hits = scan_text(note, _PRICE_VAGUE_WORDS)
    if hits:
        has_mech = ps.get("price_adjust_mechanism") is True
        level = adef.level if has_mech else "D0"
        tail = "已有调价机制,维持 D1" if has_mech else "无调价机制,升 D0"
        return Outcome(status="FAIL", level=level, message=f"报价说明模糊调价表述({tail}): {hit_message(hits)}")
    return Outcome(status="PASS", message="报价说明无模糊调价表述")


@register("SK-PS-010")
def _ps010_abnormal_low(ctx: dict, adef) -> Outcome:
    """expr:低于 price_history 均值 7 折告警(D2);历史价缺失→D3 静默
    (SKIPPED no_signal,写作端新增规则不做假校验)。"""
    material = opt(ctx, "material") or {}
    history = opt(material, "price_history") or []
    amounts = [Decimal(str(h.get("amount"))) for h in history if isinstance(h, dict) and h.get("amount") is not None]
    if not amounts:
        return Outcome(status="SKIPPED", level="D3", message="历史价缺失,异常低价校验静默")
    mean = (sum(amounts) / len(amounts)).quantize(Decimal("0.01"))
    detail = Decimal(str(need(need(ctx, "products"), "price_sheet").get("detail_total")))
    threshold = (mean * _ABNORMAL_LOW_RATIO).quantize(Decimal("0.01"))
    if detail < threshold:
        return Outcome(status="FAIL", level=adef.level, deterministic=False, message=f"报价 {detail} < 历史均价×{_ABNORMAL_LOW_RATIO}={threshold}(均值 {mean},疑似异常低价)")
    return Outcome(status="PASS", deterministic=False, message=f"报价 {detail} 不低于历史均价阈值 {threshold}")
