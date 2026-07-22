/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface Task {
  id: string;
  title: string;
  description?: string;
  category: "Core" | "Security" | "Compute" | "Database";
  status: "pending" | "completed";
  priority: "low" | "medium" | "high" | "critical";
  updatedAt: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  progress: number; // 0 to 100
  status: "active" | "review" | "paused" | "completed";
  systemLoad: number; // percentage
  coreNodes: number;
}

export interface NotificationLog {
  id: string;
  title: string;
  description: string;
  timestamp: string;
  category: "system" | "workflow" | "security";
  unread: boolean;
  actionUrl?: string;
}

export interface CalendarEvent {
  id: string;
  title: string;
  date: string; // YYYY-MM-DD
  time?: string;
  type: "meeting" | "deployment" | "security" | "review";
  loadFactor: number; // 0 to 1
}

export interface SystemMetrics {
  activeProjects: number;
  pendingReviews: number;
  draftsInProgress: number;
  overdueTasks: number;
}

export interface DynamicTelemetry {
  cpuUsage: number;
  memoryUsage: number;
  networkTraffic: number;
  sandBoxSecurityStatus: "optimal" | "warning" | "compromised";
}
