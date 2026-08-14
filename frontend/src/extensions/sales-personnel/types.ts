/**
 * 销售人员(sales-personnel)类型 —— 对齐 data_source 罐装 dataset 列。
 * Decimal/numeric 经 JSON 序列化为 string。
 */

/** spq_kpi:单行 HR 汇总。 */
export interface HrKpiRow {
  employee_total: number;
  active_count: number;
  resigned_count: number;
  attendance_rate: string;
  travel_total: string;
  pending_count: number;
  pending_amount: string;
}

/** spq_attendance_summary:按部门考勤汇总。 */
export interface AttendanceSummaryRow {
  department: string;
  emp_count: number;
  present_days: number;
  leave_days: number;
  absent_days: number;
  trip_days: number;
  attendance_rate: string;
}

/** spq_dept_travel:按部门差旅汇总。 */
export interface DeptTravelRow {
  department: string;
  trip_count: number;
  total_amount: string;
  traveler_count: number;
  per_capita: string;
}

/** spq_reimburse_status:报销状态构成。 */
export interface ReimburseStatusRow {
  reimburse_status: string;
  cnt: number;
  total_amount: string;
}

/** mock_employee 明细行(直接 SELECT,列固定)。 */
export interface EmployeeRow {
  employee_id: string;
  name: string;
  employee_no: string;
  department: string;
  position: string;
  hire_date: string;
  status: string;
}

export interface QueryResult<T = Record<string, unknown>> {
  rows: T[];
  row_count: number;
  label?: string | null;
}
