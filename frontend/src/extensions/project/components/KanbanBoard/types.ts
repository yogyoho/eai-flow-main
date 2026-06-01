export interface KanbanCardData {
  id: string;
  title: string;
  status: "draft" | "writing" | "review" | "completed";
  assignee?: string;
  wordCount?: number;
  targetWordCount?: number;
  dueDate?: string;
}
