/**
 * sales-personnel TanStack Query hooks。queryKey 统一 ["spq", ...] 命名空间。
 * 罐装视图:resolve source/dataset id(缓存)→ queryDataset;
 * 明细/下钻:raw SQL → querySql(后端 assert_readonly_select 守卫)。
 *
 * 铁律:dataset label 必须与 seed_mock_sales.py 一字不差。
 */

import { useQuery } from "@tanstack/react-query";

import { queryDataset, querySql, resolveDatasetId, resolveSourceId } from "./api";
import type {
  AttendanceSummaryRow,
  DeptTravelRow,
  EmployeeDetailRow,
  EmployeeRow,
  HrKpiRow,
  QueryResult,
  ReimburseDeptRow,
  ReimburseStatusRow,
} from "./types";

export const KEYS = {
  kpi: ["spq", "kpi"] as const,
  attendance: ["spq", "attendance"] as const,
  travel: ["spq", "travel"] as const,
  reimburse: ["spq", "reimburse"] as const,
  employees: ["spq", "employees"] as const,
  detail: ["spq", "detail"] as const,
  reimburseDept: ["spq", "reimburse-dept"] as const,
  drilldown: (sql: string) => ["spq", "drilldown", sql] as const,
};

function useDatasetQuery<T>(key: readonly string[], label: string, enabled = true) {
  return useQuery({
    queryKey: key,
    enabled,
    queryFn: async (): Promise<T[]> => {
      const sid = await resolveSourceId();
      const did = await resolveDatasetId(sid, label);
      const res = await queryDataset(sid, did);
      return res.rows as T[];
    },
  });
}

export const useHrKpi = () => useDatasetQuery<HrKpiRow>(KEYS.kpi, "HR总览");
export const useAttendanceSummary = () => useDatasetQuery<AttendanceSummaryRow>(KEYS.attendance, "考勤汇总");
export const useDeptTravel = () => useDatasetQuery<DeptTravelRow>(KEYS.travel, "部门差旅");
export const useReimburseStatus = () => useDatasetQuery<ReimburseStatusRow>(KEYS.reimburse, "报销状态构成");
export const useEmployeeDetail = () => useDatasetQuery<EmployeeDetailRow>(KEYS.detail, "员工明细");
export const useReimburseDept = () => useDatasetQuery<ReimburseDeptRow>(KEYS.reimburseDept, "报销状态×部门");

/** 员工明细:全量 mock_employee,下钻来源。 */
export function useEmployeeList(enabled = true) {
  return useQuery({
    queryKey: KEYS.employees,
    enabled,
    queryFn: async (): Promise<EmployeeRow[]> => {
      const sid = await resolveSourceId();
      const res = await querySql(
        sid,
        "SELECT employee_id, name, employee_no, department, position, hire_date, status FROM mock_employee ORDER BY employee_id",
      );
      // EmployeeRow 为具名 interface(非 Record),与 QueryResult 默认 Record<string,unknown> 不重叠 → 先转 unknown
      return res.rows as unknown as EmployeeRow[];
    },
  });
}

/** 下钻:参数化只读 SQL(由查询页点击触发,sql=null 时不发)。 */
export function useDrillDown(sql: string | null) {
  return useQuery({
    queryKey: KEYS.drilldown(sql ?? ""),
    enabled: !!sql,
    queryFn: async (): Promise<QueryResult> => {
      const sid = await resolveSourceId();
      return querySql(sid, sql!); // enabled: !!sql 保证此处非空,lint 偏好 ! 非 as 断言
    },
  });
}
