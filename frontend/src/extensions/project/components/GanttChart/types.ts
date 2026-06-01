export interface TimelineEntry {
  id: string;
  project_id: string;
  phase_node: string;
  planned_start: string | null;
  planned_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  depends_on: string[] | null;
  milestones: { label: string; target_date?: string; status?: string }[] | null;
  progress_pct: number;
  owner_id?: string | null;
}

export interface TimelineListResponse {
  entries: TimelineEntry[];
}

export type ZoomLevel = "month" | "week" | "day";
