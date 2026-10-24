"""Idempotent development seed for the QW2 sales cockpit."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.approval_service import TEMPLATES
from app.domain import create_duplicate_case, create_todo, stage_due_for
from app.enums import STAGE_BASE_PROBABILITY
from app.models import (
    ApprovalDefinition,
    Contact,
    Customer,
    CustomerGroup,
    LostReasonCode,
    Mine,
    Opportunity,
    OpportunityContact,
    PilotProject,
    Product,
    RoleLoadLimit,
    RuleConfig,
    SalesRegion,
    UserProfile,
    WorkbenchCardConfig,
    Workface,
)


async def _one(db: AsyncSession, model, **filters):
    stmt = select(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none()


async def seed_all(db: AsyncSession) -> None:
    now = datetime.now(UTC)
    region_north = await _one(db, SalesRegion, code="NORTH")
    if region_north is None:
        region_north = SalesRegion(code="NORTH", name="华北运营大区", eai_dept_id="dept-north", source="seed")
        db.add(region_north)
        await db.flush()
    region_nw = await _one(db, SalesRegion, code="NORTHWEST")
    if region_nw is None:
        region_nw = SalesRegion(code="NORTHWEST", name="西北运营大区", eai_dept_id="dept-northwest", source="seed")
        db.add(region_nw)
        await db.flush()
    default_region = await _one(db, SalesRegion, code="DEFAULT")
    if default_region is None:
        db.add(SalesRegion(code="DEFAULT", name="未分配区域", source="seed"))
        await db.flush()

    for user_id, name, role, region in [
        ("demo-rep", "李昂", "sales_rep", "NORTH"),
        ("demo-manager", "周涛", "regional_manager", "NORTH"),
        ("demo-director", "陈静", "sales_director", None),
        ("demo-compliance", "王珂", "compliance_officer", None),
    ]:
        if await db.get(UserProfile, user_id) is None:
            db.add(
                UserProfile(
                    id=user_id,
                    username=user_id,
                    display_name=name,
                    role_code=role,
                    sales_role=role,
                    region_code=region,
                    data_scope="all" if role in {"sales_director", "compliance_officer"} else ("region" if role == "regional_manager" else "self"),
                    eai_dept_id="dept-north" if user_id == "demo-manager" else None,
                )
            )

    if await _one(db, CustomerGroup, name="国能天马能源集团") is None:
        group1 = CustomerGroup(name="国能天马能源集团", credit_code="91110000EAI00001", region_code="NORTH", is_new_customer=False, source="seed", completeness=96)
        group2 = CustomerGroup(name="晋能控股集团", credit_code="91140000EAI00002", region_code="NORTHWEST", is_new_customer=True, source="seed", completeness=78)
        group3 = CustomerGroup(name="陕煤集团", credit_code="91610000EAI00003", region_code="NORTHWEST", is_new_customer=False, source="seed", completeness=88)
        db.add_all([group1, group2, group3])
        await db.flush()
        customers = [
            Customer(name="天马一矿", group_id=group1.id, region_code="NORTH", eai_dept_id="dept-north", address="山西省大同市", related_party_status="no", source="seed", completeness=95),
            Customer(name="天马二矿", group_id=group1.id, region_code="NORTH", eai_dept_id="dept-north", address="山西省朔州市", related_party_status="no", source="seed", completeness=91),
            Customer(name="晋能塔山煤矿", group_id=group2.id, region_code="NORTHWEST", eai_dept_id="dept-northwest", address="山西省大同市", related_party_status="unknown", source="seed", completeness=64),
            Customer(name="陕煤红柳林矿业", group_id=group3.id, region_code="NORTHWEST", eai_dept_id="dept-northwest", address="陕西省榆林市", related_party_status="yes", source="seed", completeness=87),
        ]
        db.add_all(customers)
        await db.flush()
        mines = [
            Mine(customer_id=customers[0].id, group_id=group1.id, name="天马一矿", region_code="NORTH", capacity="600 万吨/年", source="seed"),
            Mine(customer_id=customers[1].id, group_id=group1.id, name="天马二矿", region_code="NORTH", capacity="450 万吨/年", source="seed"),
            Mine(customer_id=customers[2].id, group_id=group2.id, name="塔山煤矿", region_code="NORTHWEST", capacity="1500 万吨/年", source="seed"),
            Mine(customer_id=customers[3].id, group_id=group3.id, name="红柳林煤矿", region_code="NORTHWEST", capacity="1800 万吨/年", source="seed"),
        ]
        db.add_all(mines)
        await db.flush()
        workfaces = [
            Workface(mine_id=mines[0].id, name="5302 综采工作面", mining_height_m=Decimal("4.2"), conditions="坚硬顶板，瓦斯中等", source="seed"),
            Workface(mine_id=mines[1].id, name="8206 综放工作面", mining_height_m=Decimal("6.8"), conditions="厚煤层，断层发育", source="seed"),
            Workface(mine_id=mines[2].id, name="8206 综采工作面", mining_height_m=Decimal("5.1"), conditions="高瓦斯，需防冲", source="seed"),
            Workface(mine_id=mines[3].id, name="15210 综采工作面", mining_height_m=Decimal("3.6"), conditions="薄煤层，智能化基础好", source="seed"),
        ]
        db.add_all(workfaces)
        await db.flush()
        products = [
            Product(product_line="智能综采", model="SC-9", name="智能综采成套装备", source="seed"),
            Product(product_line="电液控制", model="EHC-4", name="电液控制系统", source="seed"),
            Product(product_line="掘进装备", model="TJ-6", name="智能掘进机器人", source="seed"),
            Product(product_line="备件服务", model="SP-1", name="备件与运维服务", source="seed"),
        ]
        db.add_all(products)
        await db.flush()
        contacts = [
            Contact(customer_id=customers[0].id, name="张建国", title="机电矿长", role="技术决策", influence="high", stance="support", phone="13900001001", source="seed"),
            Contact(customer_id=customers[0].id, name="刘敏", title="机电科长", role="技术评估", influence="medium", stance="neutral", phone="13900001002", source="seed"),
            Contact(customer_id=customers[2].id, name="赵海峰", title="生产矿长", role="业务决策", influence="high", stance="unknown", phone="13900002001", source="seed"),
            Contact(customer_id=customers[3].id, name="孙立", title="总工程师", role="技术决策", influence="high", stance="support", phone="13900003001", source="seed"),
        ]
        db.add_all(contacts)
        await db.flush()
        db.add(
            PilotProject(
                customer_group_id=group1.id,
                workface_id=workfaces[0].id,
                name="天马一矿 5302 智能综采示范面",
                completed_at=now - timedelta(days=120),
                effect="单班人员减少 6 人，月产提升 8%",
                evidence_url="https://example.invalid/pilot/tianma-5302",
                source="seed",
            )
        )
        await db.flush()

        # Opportunities
        def opp(
            no: str,
            name: str,
            customer: Customer,
            workface: Workface | None,
            product_line: str,
            amount: str,
            stage: str,
            owner: str,
            region: str,
            *,
            expected_days: int = 30,
            status: str = "active",
            result: str | None = None,
            related: str | None = None,
            lost: str | None = None,
            contract: bool = False,
            due_offset: int | None = None,
        ) -> Opportunity:
            prob = STAGE_BASE_PROBABILITY[stage]
            return Opportunity(
                opportunity_no=no,
                name=name,
                customer_id=customer.id,
                mine_id=workface.mine_id if workface else None,
                workface_id=workface.id if workface else None,
                product_line=product_line,
                amount=Decimal(amount),
                stage=stage,
                status=status,
                result=result,
                stage_entered_at=now - timedelta(days=12),
                stage_due_at=now + timedelta(days=due_offset) if due_offset is not None else stage_due_for(stage, now),
                expected_close_date=date.today() + timedelta(days=expected_days),
                owner_id=owner,
                region_code=region,
                source="seed",
                rule_probability=Decimal(str(prob)),
                effective_probability=Decimal(str(prob)),
                probability_source="rule",
                forecast_excluded=status != "active" or stage == "S9",
                lost_reason_code=lost,
                contract_no="HT-2026-0188" if contract else None,
                contract_amount=Decimal("22000000") if contract else None,
                contract_effective_date=date.today() - timedelta(days=9) if contract else None,
            )

        opportunities = [
            opp("OPP2026100001", "天马一矿 5302 智能综采升级", customers[0], workfaces[0], "智能综采", "12000000", "S4", "demo-rep", "NORTH", expected_days=45),
            opp("OPP2026100002", "天马二矿 8206 电液控改造", customers[1], workfaces[1], "电液控制", "6800000", "S5", "demo-rep", "NORTH", expected_days=60),
            opp("OPP2026100003", "塔山煤矿 8206 智能综采新建", customers[2], workfaces[2], "智能综采", "24000000", "S4", "demo-manager", "NORTHWEST", expected_days=75, due_offset=-3),
            opp("OPP2026100004", "红柳林 15210 智能掘进", customers[3], workfaces[3], "掘进装备", "9000000", "S6", "demo-manager", "NORTHWEST", expected_days=40),
            opp("OPP2026100005", "天马一矿备件年度框架", customers[0], None, "备件服务", "3000000", "S7", "demo-rep", "NORTH", expected_days=20),
            opp("OPP2026100006", "塔山煤矿电液控升级", customers[2], workfaces[2], "电液控制", "15000000", "S3", "demo-manager", "NORTHWEST", expected_days=90),
            opp("OPP2026100007", "红柳林智能化改造二期", customers[3], workfaces[3], "智能综采", "18000000", "S8", "demo-manager", "NORTHWEST", expected_days=5, result="won"),
            opp("OPP2026100008", "天马三矿工作面配套", customers[0], None, "备件服务", "5000000", "S8", "demo-rep", "NORTH", expected_days=-2, status="lost", result="lost", lost="R1"),
            opp("OPP2026100009", "陕煤红柳林合同生效", customers[3], workfaces[3], "智能综采", "22000000", "S9", "demo-director", "NORTHWEST", expected_days=0, status="won", result="won", contract=True),
            opp("OPP2026100010", "天马一矿备件试点", customers[0], None, "备件服务", "1200000", "S1", "demo-rep", "NORTH", expected_days=110),
            opp("OPP2026100011", "晋能塔山运维服务", customers[2], workfaces[2], "备件服务", "2600000", "S2", "demo-manager", "NORTHWEST", expected_days=100),
            opp("OPP2026100012", "天马一矿 5302 电液控增补", customers[0], workfaces[0], "电液控制", "3600000", "S3", "demo-rep", "NORTH", expected_days=70),
            opp("OPP2026100013", "天马一矿 5302 电液控备件", customers[0], workfaces[0], "电液控制", "3500000", "S3", "demo-manager", "NORTH", expected_days=65),
        ]
        db.add_all(opportunities)
        await db.flush()
        db.add_all(
            [
                OpportunityContact(opportunity_id=opportunities[0].id, contact_id=contacts[0].id, role="技术决策", is_primary=True),
                OpportunityContact(opportunity_id=opportunities[0].id, contact_id=contacts[1].id, role="技术评估", is_primary=False),
                OpportunityContact(opportunity_id=opportunities[3].id, contact_id=contacts[3].id, role="技术决策", is_primary=True),
            ]
        )
        await create_duplicate_case(db, opportunities[12], opportunities[11], "seed")

    if await _one(db, LostReasonCode, code="R1") is None:
        db.add_all(
            [
                LostReasonCode(code="R1", label="价格竞争力不足", sort_order=1),
                LostReasonCode(code="R2", label="技术方案不满足", sort_order=2),
                LostReasonCode(code="R3", label="交付周期", sort_order=3),
                LostReasonCode(code="R4", label="客户关系", sort_order=4),
                LostReasonCode(code="R5", label="资质/业绩", sort_order=5),
                LostReasonCode(code="C99", label="其他（必须说明）", requires_note=True, sort_order=99),
            ]
        )

    if await _one(db, RuleConfig, rule_code="PROBABILITY_MODEL") is None:
        db.add_all(
            [
                RuleConfig(rule_code="PROBABILITY_MODEL", version=1, config_json={"base": STAGE_BASE_PROBABILITY, "overdue_penalty_pp": 15, "max_penalty_pp": 20, "floor": 5, "manual_override_threshold_pp": 15}),
                RuleConfig(rule_code="STAGE_FIELDS", version=1, config_json={"required": {}}),
                RuleConfig(rule_code="STAGE_OVERDUE", version=1, config_json={"severity": "high", "threshold_days": 0}),
                RuleConfig(rule_code="TODO_SLA", version=1, config_json={"hours": {"blocker": 4, "high": 24, "medium": 72, "low": 168}}),
                RuleConfig(rule_code="R10_DUPLICATE", version=1, config_json={"severity": "high"}),
                RuleConfig(rule_code="R4", version=1, config_json={"enabled": True}),
                RuleConfig(rule_code="R2", version=1, config_json={"enabled": True}),
                RuleConfig(rule_code="R6", version=1, config_json={"enabled": True}),
                RuleConfig(rule_code="R9", version=1, config_json={"enabled": True}),
            ]
        )

    if await _one(db, ApprovalDefinition, code="R4_EXCEPTION") is None:
        for template in TEMPLATES.values():
            db.add(
                ApprovalDefinition(
                    code=template["code"],
                    name=template["name"],
                    version=1,
                    mode="sequential",
                    steps_json=template["steps"],
                    is_active=True,
                    effective_from=now,
                )
            )

    if (await db.execute(select(WorkbenchCardConfig).limit(1))).scalar_one_or_none() is None:
        for role in ["sales_rep", "regional_manager", "sales_director", "sales_admin", "compliance_officer", "data_steward", "bid_manager"]:
            for index, card in enumerate(["today_todos", "pending_approvals", "blockers", "overdue_opportunities", "weighted_forecast", "funnel_health"]):
                db.add(WorkbenchCardConfig(role_code=role, card_code=card, sort_order=index, enabled=True))

    for role, limit in [("regional_manager", 20), ("sales_director", 30), ("compliance_officer", 15)]:
        if await db.get(RoleLoadLimit, role) is None:
            db.add(RoleLoadLimit(role_code=role, max_open=limit))

    opps = list((await db.execute(select(Opportunity).order_by(Opportunity.opportunity_no))).scalars())
    by_no = {o.opportunity_no: o for o in opps}
    if "OPP2026100003" in by_no:
        await create_todo(
            db,
            type="rule_event",
            severity="blocker",
            title="塔山煤矿商机已超期 3 天",
            description="S4 阶段停留超过 SLA，需补充示范面方案或发起 R4 例外审批。",
            object_type="opportunity",
            object_id=by_no["OPP2026100003"].id,
            dedupe_key="stage-overdue:OPP2026100003",
            source_rule="STAGE_OVERDUE",
            assignee_role="regional_manager",
            created_by="seed",
        )
    if "OPP2026100004" in by_no:
        await create_todo(
            db,
            type="data_fix",
            severity="high",
            title="补全红柳林客户关联方状态",
            description="客户关联方状态为 yes，进入 S7 前需完成 R6 合规审批。",
            object_type="opportunity",
            object_id=by_no["OPP2026100004"].id,
            dedupe_key="r6-related:OPP2026100004",
            source_rule="R6",
            assignee_role="compliance_officer",
            created_by="seed",
        )
    if "OPP2026100013" in by_no:
        await create_todo(
            db,
            type="arbitration",
            severity="high",
            title="疑似撞单：天马一矿 5302 电液控",
            description="与 OPP2026100012 命中同一客户、工作面、产品线。",
            object_type="opportunity",
            object_id=by_no["OPP2026100013"].id,
            dedupe_key="duplicate:OPP2026100013",
            source_rule="R10",
            assignee_role="regional_manager",
            created_by="seed",
        )

    await db.flush()
