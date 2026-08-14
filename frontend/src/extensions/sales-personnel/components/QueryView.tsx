"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { DrillDownModal } from "@/extensions/sales-personnel/components/DrillDownModal";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/sales-personnel/components/ui/table";
import { useAttendanceSummary, useDeptTravel, useEmployeeList } from "@/extensions/sales-personnel/hooks";
import type { AttendanceSummaryRow, DeptTravelRow, EmployeeRow } from "@/extensions/sales-personnel/types";

type TabKey = "employees" | "attendance" | "travel";

const TABS: { key: TabKey; label: string }[] = [
  { key: "employees", label: "员工明细" },
  { key: "attendance", label: "部门考勤汇总" },
  { key: "travel", label: "部门差旅汇总" },
];

// 清洗:单引号转义防 SQL 注入(值来自 DB 行数据,非用户自由输入),仅用于 SQL 拼接。
// no-base-to-string: v 为 unknown,需显式收窄后再 String()(对象走 JSON)。
const esc = (v: unknown) => {
  const s =
    v === null || v === undefined
      ? ""
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v as string | number | boolean);
  return s.replace(/'/g, "''");
};

export function QueryView() {
  const [tab, setTab] = useState<TabKey>("employees");
  const [drill, setDrill] = useState<{ title: string; sql: string } | null>(null);

  const empQ = useEmployeeList();
  const attQ = useAttendanceSummary();
  const travelQ = useDeptTravel();

  const empRows = empQ.data ?? [];
  const attRows = attQ.data ?? [];
  const travelRows = travelQ.data ?? [];

  const onRowDrill = (key: TabKey, row: EmployeeRow | AttendanceSummaryRow | DeptTravelRow) => {
    // 白名单维度:employee_id / department;值经 esc 转义后拼入只读 SELECT。
    if (key === "employees") {
      const eid = esc((row as EmployeeRow).employee_id);
      const name = esc((row as EmployeeRow).name);
      setDrill({
        title: `员工差旅明细 · ${name}`,
        sql: `SELECT trip_id, destination, start_date, end_date, purpose, amount, reimburse_status FROM mock_travel WHERE employee_id='${eid}' ORDER BY start_date DESC`,
      });
    } else if (key === "attendance") {
      const dept = esc((row as AttendanceSummaryRow).department);
      setDrill({
        title: `部门员工名单 · ${dept}`,
        sql: `SELECT employee_id, name, employee_no, position, status FROM mock_employee WHERE department='${dept}' ORDER BY employee_id`,
      });
    } else {
      const dept = esc((row as DeptTravelRow).department);
      setDrill({
        title: `部门差旅明细 · ${dept}`,
        sql: `SELECT t.trip_id, e.name, t.destination, t.start_date, t.end_date, t.purpose, t.amount, t.reimburse_status FROM mock_travel t JOIN mock_employee e ON t.employee_id=e.employee_id WHERE e.department='${dept}' ORDER BY t.start_date DESC`,
      });
    }
  };

  const loading = useMemo(
    () => (tab === "employees" ? empQ.isLoading : tab === "attendance" ? attQ.isLoading : travelQ.isLoading),
    [tab, empQ.isLoading, attQ.isLoading, travelQ.isLoading],
  );

  const toWan = (v: unknown) => {
    const n = v === null || v === undefined ? null : Number(v);
    return n === null || Number.isNaN(n) ? "—" : `${(n / 10000).toFixed(1)}万`;
  };

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center gap-3">
        <Search className="h-5 w-5 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">数据查询</h1>
      </div>

      {/* 视图 tab(pill) */}
      <div className="flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={
              "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors " +
              (tab === t.key
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 当前视图表(点行下钻) */}
      <div className="rounded-xl border border-border bg-card p-4">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
        ) : tab === "employees" ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>工号</TableHead>
                <TableHead>姓名</TableHead>
                <TableHead>员工编号</TableHead>
                <TableHead>部门</TableHead>
                <TableHead>职位</TableHead>
                <TableHead>入职日期</TableHead>
                <TableHead>状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {empRows.map((r) => (
                <TableRow key={r.employee_id} onClick={() => onRowDrill("employees", r)}>
                  <TableCell>{r.employee_id}</TableCell>
                  <TableCell>{r.name}</TableCell>
                  <TableCell>{r.employee_no}</TableCell>
                  <TableCell>{r.department}</TableCell>
                  <TableCell>{r.position}</TableCell>
                  <TableCell>{r.hire_date}</TableCell>
                  <TableCell className={r.status === "resigned" ? "font-bold text-destructive" : ""}>
                    {r.status === "active" ? "在岗" : "离职"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : tab === "attendance" ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>部门</TableHead>
                <TableHead>人数</TableHead>
                <TableHead>出勤(天)</TableHead>
                <TableHead>出差(天)</TableHead>
                <TableHead>请假(天)</TableHead>
                <TableHead>缺勤(天)</TableHead>
                <TableHead>出勤率</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {attRows.map((r) => (
                <TableRow key={r.department} onClick={() => onRowDrill("attendance", r)}>
                  <TableCell>{r.department}</TableCell>
                  <TableCell>{r.emp_count}</TableCell>
                  <TableCell>{r.present_days}</TableCell>
                  <TableCell>{r.trip_days}</TableCell>
                  <TableCell>{r.leave_days}</TableCell>
                  <TableCell>{r.absent_days}</TableCell>
                  <TableCell className={Number(r.attendance_rate) >= 85 ? "font-bold text-primary" : ""}>
                    {r.attendance_rate}%
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>部门</TableHead>
                <TableHead>差旅次数</TableHead>
                <TableHead>差旅总额</TableHead>
                <TableHead>出差人数</TableHead>
                <TableHead>人均差旅</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {travelRows.map((r) => (
                <TableRow key={r.department} onClick={() => onRowDrill("travel", r)}>
                  <TableCell>{r.department}</TableCell>
                  <TableCell>{r.trip_count}</TableCell>
                  <TableCell>{toWan(r.total_amount)}</TableCell>
                  <TableCell>{r.traveler_count}</TableCell>
                  <TableCell>{toWan(r.per_capita)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <DrillDownModal title={drill?.title ?? ""} sql={drill?.sql ?? null} onClose={() => setDrill(null)} />
    </div>
  );
}
