export interface KanbanCardData {
  id: string;
  title: string;
  status: "pending" | "draft" | "reviewing" | "approved"; // EAI-CUSTOM: canonical (ADR 2026-08-02 P4)
  assignee?: string;
  wordCount?: number;
  targetWordCount?: number;
  dueDate?: string;
}
