export interface TaskItem {
  id: string;
  type: "review" | "writing" | "phase_lead" | "ai_writing" | "rejection";
  priority_score: number;
  project_id: string;
  project_name: string;
  phase_label?: string;
  phase_node?: string;
  chapter_id?: string;
  chapter_title?: string;
  due_date?: string;
  is_blocking: boolean;
  is_urgent: boolean;
  action_label: string;
  action_url: string;
}

export interface MyTasksResponse {
  tasks: TaskItem[];
  urgent_count: number;
  total_count: number;
}

export interface MyProjectItem {
  project_id: string;
  project_name: string;
  report_type?: string;
  status: string;
  current_phase?: string;
  current_phase_node?: string;
  progress_pct: number;
  role_label: string;
  pending_task_count: number;
  last_updated?: string;
}

export interface MyProjectsResponse {
  groups: Record<string, MyProjectItem[]>;
  total_count: number;
}

export interface MyStatsResponse {
  projects_count: number;
  pending_reviews: number;
  pending_writing: number;
  completed_this_week: number;
  overdue_count: number;
}

export interface CalendarEvent {
  id: string;
  title: string;
  date: string;
  type: "deadline" | "milestone" | "phase_start" | "personal";
  project_id?: string;
  project_name?: string;
  color: "blue" | "yellow" | "green" | "red" | "purple";
}

export interface MyCalendarResponse {
  events: CalendarEvent[];
}
