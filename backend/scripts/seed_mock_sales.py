#!/usr/bin/env python3
"""模块② 销售人员查询 — mock 数据 + data_source 元数据 seed(幂等)。

EAI-CUSTOM: 市场部门模块②。真实 HR/报销系统接入前的链路演示 mock。
形态 = 路线 B(data_source 复用),零自建扩展代码。统一 employee_id 跨表 join key。

🔒 行级权限(RBAC)TODO:本 mock 用 data_source 的 fail-closed 只读守卫即可;
真实 HR 库接入时,因 HR 数据敏感(经理只看本组),必须先定行级可见性方案
(Postgres RLS 绑连接角色 / 极薄注入层把调用者范围注入 WHERE),不定不接真实数据。

在 gateway 容器内运行:
    docker exec deer-flow-gateway python /app/backend/scripts/seed_mock_sales.py

幂等:重复运行只重灌样例 + upsert 元数据,不产生重复行。

数据故事(供技能推理,非真实员工):
- 61 名员工,12 部门(销售一部/二部/技术支持部/市场部 + 研发/生产/采购/产品/质量/行政/人力资源/财务);
  60 在岗 + 1 离职(E010,2025-11-14 离职);2026-08-18 随人员总览原型扩到全公司口径;
- 考勤:2025-10~12 三个月工作日,按部门目标天数确定性生成(行和精确等于部门目标,见 DEPT_ATT);
- 差旅:35 趟(2025-10~12),报销状态 approved/pending/rejected;公司差旅合计 29.21 万 = 报销合计(对账一致);
- 前 4 部门目的地呼应 ③ 管线客户(铜川/榆林/唐山/烟台…),跨模块叙事连贯。
"""

import asyncio
import json
import os
import random
from datetime import date, timedelta
from datetime import time as dtime

import asyncpg

# ── 连接参数(默认 docker 网络内 postgres-ext;gateway 容器视角)──
PG_HOST = os.environ.get("EXTENSIONS_DB_HOST", "postgres-ext")
PG_PORT = int(os.environ.get("EXTENSIONS_DB_PORT", "5432"))
PG_USER = os.environ.get("EXTENSIONS_DB_USER", "agentflow")
PG_PASS = os.environ.get("EXTENSIONS_DB_PASSWORD", "agentflow123")
EXT_DB = os.environ.get("EXTENSIONS_DB_NAME", "agentflow")  # extensions 库(data_sources 表所在)
MOCK_DB = "mock_market"  # 与①③共用 mock 库,表名隔离(mock_employee/attendance/travel)
SOURCE_NAME = "sales-personnel"

SOURCE_CONNECTION_CONFIG = {
    "driver": "postgresql+asyncpg",
    "host": PG_HOST,
    "port": PG_PORT,
    "database": MOCK_DB,
    "username": PG_USER,
    "password": PG_PASS,
}

# ── 61 名员工(前 12 名 = 原 4 部门故事保持不变;E013+ = 2026-08-18 扩全公司 8 部门)
# (employee_id, name, employee_no, department, position, hire_date, status, resign_date)
EMPLOYEES = [
    ("E001", "张伟", "S2018015", "销售一部", "销售经理", "2018-03-15", "active", None),
    ("E002", "李娜", "S2020042", "销售一部", "销售代表", "2020-07-01", "active", None),
    ("E003", "王强", "S2021008", "销售一部", "销售代表", "2021-02-20", "active", None),
    ("E004", "赵敏", "S2022099", "销售一部", "销售助理", "2022-09-10", "active", None),
    ("E005", "陈刚", "S2017033", "销售二部", "销售经理", "2017-05-08", "active", None),
    ("E006", "刘洋", "S2019117", "销售二部", "销售代表", "2019-11-25", "active", None),
    ("E007", "杨芳", "S2023056", "销售二部", "销售代表", "2023-04-18", "active", None),
    ("E008", "周涛", "T2016021", "技术支持部", "技术经理", "2016-08-12", "active", None),
    ("E009", "吴静", "T2021064", "技术支持部", "技术工程师", "2021-06-30", "active", None),
    ("E010", "孙磊", "T2019008", "技术支持部", "技术工程师", "2019-01-15", "resigned", "2025-11-14"),
    ("E011", "郑雪", "M2022047", "市场部", "市场专员", "2022-03-22", "active", None),
    ("E012", "马超", "M2023102", "市场部", "市场专员", "2023-10-05", "active", None),
    ("E013", "林浩", "R2015012", "研发部", "研发总监", "2015-04-01", "active", None),
    ("E014", "徐婷", "R2017088", "研发部", "高级研发工程师", "2017-07-10", "active", None),
    ("E015", "马晓东", "R2019121", "研发部", "研发工程师", "2019-03-18", "active", None),
    ("E016", "黄志强", "R2020054", "研发部", "研发工程师", "2020-06-15", "active", None),
    ("E017", "宋佳", "R2021099", "研发部", "研发工程师", "2021-08-02", "active", None),
    ("E018", "唐磊", "R2022108", "研发部", "研发工程师", "2022-05-09", "active", None),
    ("E019", "韩雪", "R2023067", "研发部", "研发工程师", "2023-02-13", "active", None),
    ("E020", "曹阳", "R2024023", "研发部", "研发工程师", "2024-03-11", "active", None),
    ("E021", "许志伟", "R2024091", "研发部", "研发工程师", "2024-07-22", "active", None),
    ("E022", "邓丽", "R2025014", "研发部", "研发工程师", "2025-01-06", "active", None),
    ("E023", "冯涛", "R2025062", "研发部", "研发工程师", "2025-06-02", "active", None),
    ("E024", "蒋明", "R2025095", "研发部", "研发工程师", "2025-09-01", "active", None),
    ("E025", "杜鹏", "P2014007", "生产部", "生产总监", "2014-03-01", "active", None),
    ("E026", "任静", "P2016105", "生产部", "生产计划主管", "2016-09-05", "active", None),
    ("E027", "姚强", "P2018042", "生产部", "车间主任", "2018-05-14", "active", None),
    ("E028", "卢敏", "P2019055", "生产部", "工艺工程师", "2019-04-08", "active", None),
    ("E029", "沈国栋", "P2020031", "生产部", "设备工程师", "2020-02-17", "active", None),
    ("E030", "崔浩", "P2021102", "生产部", "班组长", "2021-09-13", "active", None),
    ("E031", "谭丽", "P2022044", "生产部", "质检员", "2022-04-18", "active", None),
    ("E032", "范伟", "P2023088", "生产部", "操作员", "2023-06-26", "active", None),
    ("E033", "彭磊", "P2024015", "生产部", "操作员", "2024-02-19", "active", None),
    ("E034", "潘婷", "P2024106", "生产部", "操作员", "2024-10-14", "active", None),
    ("E035", "袁浩", "P2025021", "生产部", "操作员", "2025-02-10", "active", None),
    ("E036", "董雪", "P2025067", "生产部", "操作员", "2025-06-16", "active", None),
    ("E037", "于强", "P2025091", "生产部", "操作员", "2025-09-01", "active", None),
    ("E038", "苏婷", "P2025083", "生产部", "操作员", "2025-08-04", "active", None),
    ("E039", "魏国", "P2015063", "生产部", "班组长", "2015-11-23", "active", None),
    ("E040", "蔡明远", "C2016009", "采购部", "采购经理", "2016-04-11", "active", None),
    ("E041", "余静", "C2020061", "采购部", "采购专员", "2020-08-03", "active", None),
    ("E042", "侯磊", "C2023066", "采购部", "采购专员", "2023-05-15", "active", None),
    ("E043", "白洋", "C2024108", "采购部", "采购专员", "2024-10-21", "active", None),
    ("E044", "施磊", "C2025033", "采购部", "采购助理", "2025-03-03", "active", None),
    ("E045", "丁一", "D2019003", "产品部", "产品总监", "2019-01-07", "active", None),
    ("E046", "田甜", "D2022071", "产品部", "产品经理", "2022-07-11", "active", None),
    ("E047", "江浩", "D2024089", "产品部", "产品助理", "2024-09-09", "active", None),
    ("E048", "温强", "Q2017019", "质量部", "质量总监", "2017-02-20", "active", None),
    ("E049", "阎丽", "Q2021057", "质量部", "质量工程师", "2021-05-10", "active", None),
    ("E050", "石磊", "Q2023113", "质量部", "质量工程师", "2023-11-27", "active", None),
    ("E051", "白茹", "Q2025041", "质量部", "质量工程师", "2025-04-14", "active", None),
    ("E052", "贺敏", "X2018004", "行政部", "行政主管", "2018-03-05", "active", None),
    ("E053", "龚雪", "X2022095", "行政部", "行政专员", "2022-09-19", "active", None),
    ("E054", "陶磊", "X2025077", "行政部", "行政专员", "2025-07-07", "active", None),
    ("E055", "姜婷", "H2016002", "人力资源部", "人力资源经理", "2016-01-11", "active", None),
    ("E056", "戚强", "H2021108", "人力资源部", "招聘专员", "2021-10-18", "active", None),
    ("E057", "常丽", "H2024066", "人力资源部", "薪酬专员", "2024-06-24", "active", None),
    ("E058", "尚雪", "F2015006", "财务部", "财务经理", "2015-06-01", "active", None),
    ("E059", "乐磊", "F2020038", "财务部", "会计", "2020-04-13", "active", None),
    ("E060", "燕敏", "F2023059", "财务部", "会计", "2023-07-31", "active", None),
    ("E061", "邵强", "F2025082", "财务部", "出纳", "2025-08-11", "active", None),
]

# ── 20 趟差旅(显式,目的地呼应 ③ 管线客户)
# (trip_id, employee_id, destination, start_date, end_date, purpose, amount, reimburse_status)
TRIPS = [
    ("TR-2025-001", "E001", "西安·华能铜川电厂", "2025-10-08", "2025-10-10", "项目投标述标", 8500.00, "approved"),
    ("TR-2025-002", "E005", "榆林·陕西能源", "2025-10-09", "2025-10-12", "客户拜访", 11200.00, "approved"),
    ("TR-2025-003", "E008", "唐山·钢铁集团", "2025-10-13", "2025-10-15", "设备调试", 9800.00, "approved"),
    ("TR-2025-004", "E011", "烟台·万华化学", "2025-10-15", "2025-10-16", "市场调研", 6300.00, "pending"),
    ("TR-2025-005", "E001", "铜川·华能电厂", "2025-10-20", "2025-10-22", "合同谈判", 7200.00, "approved"),
    ("TR-2025-006", "E002", "宁夏·宝丰能源", "2025-10-22", "2025-10-24", "项目跟进", 8900.00, "rejected"),
    ("TR-2025-007", "E009", "雷州·大唐电厂", "2025-10-27", "2025-10-29", "售后维护", 10500.00, "approved"),
    ("TR-2025-008", "E005", "呼和浩特·久泰", "2025-11-03", "2025-11-05", "技术交流", 9100.00, "pending"),
    ("TR-2025-009", "E003", "鄂尔多斯·中天合创", "2025-11-05", "2025-11-07", "投标支持", 7800.00, "approved"),
    ("TR-2025-010", "E008", "榆林·煤化工基地", "2025-11-10", "2025-11-13", "现场勘查", 13400.00, "approved"),
    ("TR-2025-011", "E006", "烟台·万华PDH", "2025-11-12", "2025-11-14", "客户拜访", 8600.00, "pending"),
    ("TR-2025-012", "E010", "唐山·钢铁集团", "2025-11-06", "2025-11-08", "设备调试", 9200.00, "approved"),
    ("TR-2025-013", "E001", "榆林·气化装置", "2025-11-17", "2025-11-19", "合同评审", 8100.00, "approved"),
    ("TR-2025-014", "E012", "上海·行业展会", "2025-11-20", "2025-11-22", "展会参展", 12500.00, "approved"),
    ("TR-2025-015", "E007", "宁夏·宝丰", "2025-11-24", "2025-11-26", "项目跟进", 7400.00, "rejected"),
    ("TR-2025-016", "E005", "唐山·钢铁余热", "2025-12-01", "2025-12-03", "投标述标", 9700.00, "pending"),
    ("TR-2025-017", "E008", "铜川·华能二期", "2025-12-04", "2025-12-06", "现场服务", 8800.00, "approved"),
    ("TR-2025-018", "E002", "榆林·陕西能源", "2025-12-08", "2025-12-10", "合同执行", 7900.00, "approved"),
    ("TR-2025-019", "E011", "北京·行业峰会", "2025-12-11", "2025-12-12", "市场推广", 6800.00, "pending"),
    ("TR-2025-020", "E001", "唐山·钢铁集团", "2025-12-15", "2025-12-17", "项目验收", 9300.00, "approved"),
    # ── 8 个扩展部门(2026-08-18 全公司口径;每部门金额合计 = 人员总览原型示意)──
    ("TR-2025-021", "E013", "深圳·嵌入式技术大会", "2025-10-16", "2025-10-18", "技术调研", 12000.00, "approved"),
    ("TR-2025-022", "E014", "上海·合作伙伴技术对接", "2025-11-19", "2025-11-21", "技术交流", 10000.00, "approved"),
    ("TR-2025-023", "E015", "北京·客户现场联调", "2025-12-08", "2025-12-10", "现场支持", 9200.00, "pending"),
    ("TR-2025-024", "E025", "苏州·设备供应商验货", "2025-10-21", "2025-10-22", "设备验收", 8300.00, "approved"),
    ("TR-2025-025", "E026", "常州·外协厂审核", "2025-11-25", "2025-11-26", "供应商审核", 4200.00, "pending"),
    ("TR-2025-026", "E027", "无锡·产线故障处理", "2025-12-16", "2025-12-17", "现场抢修", 6000.00, "rejected"),
    ("TR-2025-027", "E040", "宁波·钢材供应商考察", "2025-10-27", "2025-10-29", "供应商考察", 7500.00, "approved"),
    ("TR-2025-028", "E041", "佛山·元器件采购谈判", "2025-11-11", "2025-11-12", "采购谈判", 8800.00, "pending"),
    ("TR-2025-029", "E042", "青岛·物流方案评审", "2025-12-02", "2025-12-03", "物流评审", 6700.00, "approved"),
    ("TR-2025-030", "E045", "广州·行业产品发布会", "2025-11-06", "2025-11-07", "产品发布", 14400.00, "approved"),
    ("TR-2025-031", "E048", "天津·来料质量处理", "2025-10-13", "2025-10-14", "质量处理", 6000.00, "approved"),
    ("TR-2025-032", "E049", "大连·客户质量审核", "2025-12-09", "2025-12-10", "质量审核", 5500.00, "approved"),
    ("TR-2025-033", "E052", "杭州·分公司行政对接", "2025-11-04", "2025-11-05", "行政对接", 6200.00, "approved"),
    ("TR-2025-034", "E055", "成都·校园招聘宣讲", "2025-10-20", "2025-10-21", "校园招聘", 3500.00, "approved"),
    ("TR-2025-035", "E058", "厦门·税务政策培训", "2025-12-15", "2025-12-16", "税务培训", 2800.00, "approved"),
]

# ── 部门考勤目标(2026-08-18 人员总览原型口径):(请假, 缺勤)天数
# 出差不设目标——直接取 TRIPS 行程覆盖的工作日(真值);出勤 = 工作日 - 其余三态(自然收口)。
# 部门总天数 = 人数×66 工作日(E010 离职者 33)。
DEPT_ATT = {
    "销售一部": (11, 8),
    "销售二部": (7, 8),
    "技术支持部": (8, 2),
    "市场部": (7, 4),
    "研发部": (36, 18),
    "生产部": (51, 24),
    "采购部": (15, 9),
    "产品部": (8, 4),
    "质量部": (12, 5),
    "行政部": (11, 5),
    "人力资源部": (10, 6),
    "财务部": (14, 6),
}
RESIGNED_ATT = (28, 2, 2, 1)  # E010 离职者固定拆分(出勤/出差/请假/缺勤;窗口内 33 工作日至 2025-11-14,出差 2 天 = TR-012)

# 考勤窗口
WIN_START = date(2025, 10, 1)
WIN_END = date(2025, 12, 31)

# ── 6 个罐装 dataset(只读 SELECT,过 assert_readonly_select 守卫)──
DATASETS = [
    {
        "table_name": "spq_kpi",
        "label": "HR总览",
        "description": "员工总数/在岗/离职/全员出勤率/差旅总额/待审批笔数与金额(单行汇总)。",
        "default_query": """
            SELECT
              (SELECT COUNT(*) FROM mock_employee) AS employee_total,
              (SELECT COUNT(*) FROM mock_employee WHERE status='active') AS active_count,
              (SELECT COUNT(*) FROM mock_employee WHERE status='resigned') AS resigned_count,
              ROUND(100.0 * (SELECT COUNT(*) FROM mock_attendance WHERE status='present')
                    / NULLIF((SELECT COUNT(*) FROM mock_attendance),0), 1) AS attendance_rate,
              (SELECT COALESCE(SUM(amount),0) FROM mock_travel) AS travel_total,
              (SELECT COUNT(*) FROM mock_travel WHERE reimburse_status='pending') AS pending_count,
              (SELECT COALESCE(SUM(amount),0) FROM mock_travel WHERE reimburse_status='pending') AS pending_amount
        """.strip(),
    },
    {
        "table_name": "spq_attendance_summary",
        "label": "考勤汇总",
        "description": "按部门统计在岗/请假/缺勤/出差天数与出勤率。",
        "default_query": """
            SELECT e.department,
              COUNT(DISTINCT a.employee_id) AS emp_count,
              SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS present_days,
              SUM(CASE WHEN a.status='leave' THEN 1 ELSE 0 END) AS leave_days,
              SUM(CASE WHEN a.status='absent' THEN 1 ELSE 0 END) AS absent_days,
              SUM(CASE WHEN a.status='trip' THEN 1 ELSE 0 END) AS trip_days,
              ROUND(100.0 * SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 1) AS attendance_rate
            FROM mock_attendance a JOIN mock_employee e ON a.employee_id=e.employee_id
            GROUP BY e.department ORDER BY e.department
        """.strip(),
    },
    {
        "table_name": "spq_dept_travel",
        "label": "部门差旅",
        "description": "按部门统计差旅总额、出差次数、人均差旅。",
        "default_query": """
            SELECT e.department,
              COUNT(*) AS trip_count,
              COALESCE(SUM(t.amount),0) AS total_amount,
              COUNT(DISTINCT t.employee_id) AS traveler_count,
              ROUND(COALESCE(SUM(t.amount),0)::numeric / NULLIF(COUNT(DISTINCT t.employee_id),0), 0) AS per_capita
            FROM mock_travel t JOIN mock_employee e ON t.employee_id=e.employee_id
            GROUP BY e.department ORDER BY total_amount DESC
        """.strip(),
    },
    {
        "table_name": "spq_reimburse_status",
        "label": "报销状态构成",
        "description": "按报销状态统计笔数与金额(approved/pending/rejected)。",
        "default_query": """
            SELECT reimburse_status,
              COUNT(*) AS cnt,
              COALESCE(SUM(amount),0) AS total_amount
            FROM mock_travel GROUP BY reimburse_status ORDER BY total_amount DESC
        """.strip(),
    },
    {
        "table_name": "spq_reimburse_dept",
        "label": "报销状态×部门",
        "description": "按部门 × 报销状态统计笔数与金额(部门筛选联动口径)。",
        "default_query": """
            SELECT e.department, t.reimburse_status,
              COUNT(*) AS cnt,
              COALESCE(SUM(t.amount),0) AS total_amount
            FROM mock_travel t JOIN mock_employee e ON t.employee_id=e.employee_id
            GROUP BY e.department, t.reimburse_status ORDER BY e.department
        """.strip(),
    },
    {
        "table_name": "spq_employee_detail",
        "label": "员工明细",
        "description": "按员工统计考勤四态天数、出勤率与差旅金额(含在职状态)。",
        "default_query": """
            SELECT e.employee_id, e.name, e.department, e.status,
              SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS present_days,
              SUM(CASE WHEN a.status='trip' THEN 1 ELSE 0 END) AS trip_days,
              SUM(CASE WHEN a.status='leave' THEN 1 ELSE 0 END) AS leave_days,
              SUM(CASE WHEN a.status='absent' THEN 1 ELSE 0 END) AS absent_days,
              ROUND(100.0 * SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 1) AS attendance_rate,
              COALESCE((SELECT SUM(t.amount) FROM mock_travel t WHERE t.employee_id=e.employee_id), 0) AS travel_amount
            FROM mock_employee e LEFT JOIN mock_attendance a ON a.employee_id=e.employee_id
            GROUP BY e.employee_id, e.name, e.department, e.status ORDER BY e.employee_id
        """.strip(),
    },
]


def _working_days(start: date, end: date):
    """生成 [start,end] 内的工作日(周一至周五)。"""
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _dist(total: int, n: int) -> list[int]:
    """均分:前 r 个多 1,保证行和精确等于部门目标天数。"""
    base, rem = divmod(total, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def _pick(n: int, k: int, phase: int, occupied: set[int]) -> set[int]:
    """确定性取 k 个下标:均匀铺开 + 相位错开;撞车(他人已占)时向后找空位。"""
    chosen: set[int] = set()
    for i in range(k):
        j = (i * n // max(k, 1) + phase) % n
        while j in occupied or j in chosen:
            j = (j + 1) % n
        chosen.add(j)
        occupied.add(j)
    return chosen


def gen_attendance() -> list[tuple]:
    """确定性生成考勤(2026-08-18 人员总览原型口径)。

    - 出差天数 = TRIPS 行程覆盖的窗口内工作日(真值,不造数);
    - 请假/缺勤 = DEPT_ATT 部门目标,在岗者间均摊(行和精确);
    - 出勤 = 剩余工作日(自然收口,人内四态互斥);
    - random.Random(42) 仅装饰 present 打卡时刻,不影响天数分布。
    """
    rnd = random.Random(42)  # 仅装饰:present 打卡时刻
    trip_days_by_emp: dict[str, int] = {}
    for _tid, eid, _dest, s, e, *_rest in TRIPS:
        ds, de = date.fromisoformat(s), date.fromisoformat(e)
        trip_days_by_emp[eid] = trip_days_by_emp.get(eid, 0) + sum(1 for d in _working_days(ds, de) if WIN_START <= d <= WIN_END)

    by_dept: dict[str, list] = {}
    for emp in EMPLOYEES:
        by_dept.setdefault(emp[3], []).append(emp)

    rows: list[tuple] = []

    def _emit(eid: str, wdays: list[date], t: int, l: int, a: int) -> None:
        """把 (trip t / leave l / absent a / 其余 present) 铺到 wdays 上,互斥。"""
        occupied: set[int] = set()
        n = len(wdays)
        trip_i = _pick(n, t, 0, occupied)
        leave_i = _pick(n, l, n // 3, occupied)
        abs_i = _pick(n, a, 2 * n // 3, occupied)
        for idx, d in enumerate(wdays):
            if idx in trip_i:
                rows.append((eid, d, "trip", None, None))
            elif idx in leave_i:
                rows.append((eid, d, "leave", None, None))
            elif idx in abs_i:
                rows.append((eid, d, "absent", None, None))
            else:
                cin_m = 8 * 60 + rnd.randint(35, 55)
                cout_m = 18 * 60 + rnd.randint(0, 30)
                rows.append((eid, d, "present", dtime(cin_m // 60, cin_m % 60), dtime(cout_m // 60, cout_m % 60)))

    for dept, emps in by_dept.items():
        leave_t, abs_t = DEPT_ATT[dept]
        actives = [e for e in emps if e[6] == "active"]
        resigned = [e for e in emps if e[6] != "active"]
        leave_t -= RESIGNED_ATT[2] * len(resigned)
        abs_t -= RESIGNED_ATT[3] * len(resigned)

        # 离职者固定拆分(现仅 E010:窗口内 33 工作日,出差 2 天 = TR-012 真值)
        for emp in resigned:
            eid, _n, _eno, _d, _p, _h, _st, resign_date = emp
            end = date.fromisoformat(resign_date) if resign_date else WIN_END
            _r_pre, r_trip, r_leave, r_abs = RESIGNED_ATT
            _emit(eid, list(_working_days(WIN_START, end)), r_trip, r_leave, r_abs)

        leave_q = _dist(leave_t, len(actives))
        abs_q = _dist(abs_t, len(actives))
        for i, emp in enumerate(actives):
            eid = emp[0]
            _emit(eid, list(_working_days(WIN_START, WIN_END)), trip_days_by_emp.get(eid, 0), leave_q[i], abs_q[i])
    return rows


async def main() -> None:
    common = dict(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS)

    # 1. mock_market 库(① 已建,幂等跳过)
    sys_conn = await asyncpg.connect(**common, database=EXT_DB)
    try:
        await sys_conn.execute(f'CREATE DATABASE "{MOCK_DB}"')
        print(f"[ok] 已建库 {MOCK_DB}")
    except asyncpg.DuplicateDatabaseError:
        print(f"[skip] 库 {MOCK_DB} 已存在")
    finally:
        await sys_conn.close()

    # 2. 建 3 表 + 重灌(幂等)
    mock = await asyncpg.connect(**common, database=MOCK_DB)
    await mock.execute(
        """
        CREATE TABLE IF NOT EXISTS mock_employee (
          employee_id  TEXT PRIMARY KEY,
          name         TEXT NOT NULL,
          employee_no  TEXT NOT NULL,
          department   TEXT NOT NULL,
          position     TEXT NOT NULL,
          hire_date    DATE NOT NULL,
          status       TEXT NOT NULL DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS mock_attendance (
          id           SERIAL PRIMARY KEY,
          employee_id  TEXT NOT NULL REFERENCES mock_employee(employee_id) ON DELETE CASCADE,
          date         DATE NOT NULL,
          status       TEXT NOT NULL,
          check_in     TIME,
          check_out    TIME
        );
        CREATE TABLE IF NOT EXISTS mock_travel (
          trip_id           TEXT PRIMARY KEY,
          employee_id       TEXT NOT NULL REFERENCES mock_employee(employee_id) ON DELETE CASCADE,
          destination       TEXT NOT NULL,
          start_date        DATE NOT NULL,
          end_date          DATE NOT NULL,
          purpose           TEXT NOT NULL,
          amount            NUMERIC(14,2) NOT NULL,
          reimburse_status  TEXT NOT NULL
        );
        """
    )
    # FK:mock_attendance/mock_travel → mock_employee,必须同语句 CASCADE 截断(分语句会被 FK 阻止)
    await mock.execute("TRUNCATE mock_travel, mock_attendance, mock_employee RESTART IDENTITY CASCADE;")

    emp_rows = [(eid, name, eno, dept, pos, date.fromisoformat(hire), status) for (eid, name, eno, dept, pos, hire, status, _resign) in EMPLOYEES]
    att_rows = gen_attendance()
    trip_rows = [(tid, eid, dest, date.fromisoformat(s), date.fromisoformat(e), purpose, amount, rstatus) for (tid, eid, dest, s, e, purpose, amount, rstatus) in TRIPS]

    await mock.executemany(
        "INSERT INTO mock_employee (employee_id,name,employee_no,department,position,hire_date,status) VALUES ($1,$2,$3,$4,$5,$6,$7)",
        emp_rows,
    )
    await mock.executemany(
        "INSERT INTO mock_attendance (employee_id,date,status,check_in,check_out) VALUES ($1,$2,$3,$4,$5)",
        att_rows,
    )
    await mock.executemany(
        "INSERT INTO mock_travel (trip_id,employee_id,destination,start_date,end_date,purpose,amount,reimburse_status) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        trip_rows,
    )
    print(f"[ok] 已灌 {len(emp_rows)} employee / {len(att_rows)} attendance / {len(trip_rows)} travel")
    await mock.close()

    # 3. extensions 库 upsert 第 3 条 data_source 连接 + 4 dataset(幂等)
    ext = await asyncpg.connect(**common, database=EXT_DB)
    cfg_json = json.dumps(SOURCE_CONNECTION_CONFIG)
    src_id = await ext.fetchval("SELECT id FROM data_sources WHERE name=$1", SOURCE_NAME)
    desc = "模块② 销售人员查询 mock 数据源(HR 员工/考勤/报销差旅,统一 employee_id)。"
    if src_id is None:
        src_id = await ext.fetchval(
            "INSERT INTO data_sources (id,name,description,type,connection_config,auth_type,sync_mode,status,created_at,updated_at) VALUES (gen_random_uuid(),$1,$2,$3,$4::jsonb,$5,$6,$7,now(),now()) RETURNING id",
            SOURCE_NAME,
            desc,
            "database",
            cfg_json,
            "none",
            "manual",
            "connected",
        )
        print(f"[ok] 已建 data_source '{SOURCE_NAME}'")
    else:
        await ext.execute(
            "UPDATE data_sources SET description=$2, connection_config=$3::jsonb, status='connected' WHERE id=$1",
            src_id,
            desc,
            cfg_json,
        )
        print(f"[ok] 已更新 data_source '{SOURCE_NAME}'")

    for ds in DATASETS:
        await ext.execute(
            "INSERT INTO data_source_datasets (id,source_id,table_name,label,description,default_query,created_at,updated_at) "
            "VALUES (gen_random_uuid(),$1,$2,$3,$4,$5,now(),now()) "
            "ON CONFLICT (source_id, table_name) DO UPDATE SET "
            "  label=EXCLUDED.label, description=EXCLUDED.description, "
            "  default_query=EXCLUDED.default_query, updated_at=now()",
            src_id,
            ds["table_name"],
            ds["label"],
            ds["description"],
            ds["default_query"],
        )
    print(f"[ok] 已 upsert {len(DATASETS)} 个 dataset")
    await ext.close()

    # 自检(肉眼校验)
    chk = await asyncpg.connect(**common, database=MOCK_DB)
    n_emp = await chk.fetchval("SELECT count(*) FROM mock_employee")
    n_active = await chk.fetchval("SELECT count(*) FROM mock_employee WHERE status='active'")
    n_att = await chk.fetchval("SELECT count(*) FROM mock_attendance")
    n_present = await chk.fetchval("SELECT count(*) FROM mock_attendance WHERE status='present'")
    n_trip = await chk.fetchval("SELECT count(*) FROM mock_travel")
    amt_total = await chk.fetchval("SELECT coalesce(sum(amount),0) FROM mock_travel")
    n_pending = await chk.fetchval("SELECT count(*) FROM mock_travel WHERE reimburse_status='pending'")
    amt_pending = await chk.fetchval("SELECT coalesce(sum(amount),0) FROM mock_travel WHERE reimburse_status='pending'")
    rate = round(100.0 * n_present / n_att, 1) if n_att else 0
    print("\n===== 自检 =====")
    print(f"员工={n_emp} 在岗={n_active} 离职={n_emp - n_active}\n考勤记录={n_att} 覆盖 2025-10~12 全员出勤率={rate}%\n差旅={n_trip} 趟 总额={amt_total:.0f}元 待审批={n_pending}笔/{amt_pending:.0f}元")
    await chk.close()
    print("\n[done] seed 完成。重启 gateway 使 data_source MCP 缓存感知新连接。")


if __name__ == "__main__":
    asyncio.run(main())
