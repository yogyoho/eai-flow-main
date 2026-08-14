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
- 12 名员工,4 部门(销售一部/二部/技术支持部/市场部);11 在岗 + 1 离职(E010,2025-11-14 离职);
- 考勤:2025-10~12 三个月工作日,程序生成(present≈85%/trip≈8%/leave≈4%/absent≈3%);离职员工只到离职日;
- 差旅:20 趟(2025-10~12),报销状态 approved/pending/rejected ≈ 65/25/10;
- 目的地呼应 ③ 管线客户(铜川/榆林/唐山/烟台…),跨模块叙事连贯。
"""

import asyncio
import json
import os
import random
from datetime import date, time as dtime, timedelta

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

# ── 12 名员工
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
]

# 考勤窗口
WIN_START = date(2025, 10, 1)
WIN_END = date(2025, 12, 31)

# ── 4 个罐装 dataset(只读 SELECT,过 assert_readonly_select 守卫)──
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
]


def _working_days(start: date, end: date):
    """生成 [start,end] 内的工作日(周一至周五)。"""
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def gen_attendance() -> list[tuple]:
    """按权重生成考勤行(确定性:固定种子)。present≈85%/trip≈8%/leave≈4%/absent≈3%。"""
    rnd = random.Random(42)
    rows = []
    for emp_id, _name, _eno, _dept, _pos, _hire, status, resign_date in EMPLOYEES:
        end = date.fromisoformat(resign_date) if (status == "resigned" and resign_date) else WIN_END
        if end < WIN_START:
            continue  # 窗口前已离职,无考勤
        for d in _working_days(WIN_START, end):
            r = rnd.random()
            if r < 0.85:
                cin_m = 8 * 60 + rnd.randint(35, 55)  # 08:35-08:55
                cout_m = 18 * 60 + rnd.randint(0, 30)  # 18:00-18:30
                cin = dtime(cin_m // 60, cin_m % 60)
                cout = dtime(cout_m // 60, cout_m % 60)
                rows.append((emp_id, d, "present", cin, cout))
            elif r < 0.93:
                rows.append((emp_id, d, "trip", None, None))
            elif r < 0.97:
                rows.append((emp_id, d, "leave", None, None))
            else:
                rows.append((emp_id, d, "absent", None, None))
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
    await mock.execute(
        "TRUNCATE mock_travel, mock_attendance, mock_employee RESTART IDENTITY CASCADE;"
    )

    emp_rows = [
        (eid, name, eno, dept, pos, date.fromisoformat(hire), status)
        for (eid, name, eno, dept, pos, hire, status, _resign) in EMPLOYEES
    ]
    att_rows = gen_attendance()
    trip_rows = [
        (tid, eid, dest, date.fromisoformat(s), date.fromisoformat(e), purpose, amount, rstatus)
        for (tid, eid, dest, s, e, purpose, amount, rstatus) in TRIPS
    ]

    await mock.executemany(
        "INSERT INTO mock_employee (employee_id,name,employee_no,department,position,hire_date,status) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7)",
        emp_rows,
    )
    await mock.executemany(
        "INSERT INTO mock_attendance (employee_id,date,status,check_in,check_out) VALUES ($1,$2,$3,$4,$5)",
        att_rows,
    )
    await mock.executemany(
        "INSERT INTO mock_travel (trip_id,employee_id,destination,start_date,end_date,purpose,amount,reimburse_status) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
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
            "INSERT INTO data_sources (id,name,description,type,connection_config,auth_type,sync_mode,status,created_at,updated_at) "
            "VALUES (gen_random_uuid(),$1,$2,$3,$4::jsonb,$5,$6,$7,now(),now()) RETURNING id",
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
    print(
        f"员工={n_emp} 在岗={n_active} 离职={n_emp - n_active}\n"
        f"考勤记录={n_att} 覆盖 2025-10~12 全员出勤率={rate}%\n"
        f"差旅={n_trip} 趟 总额={amt_total:.0f}元 待审批={n_pending}笔/{amt_pending:.0f}元"
    )
    await chk.close()
    print("\n[done] seed 完成。重启 gateway 使 data_source MCP 缓存感知新连接。")


if __name__ == "__main__":
    asyncio.run(main())
