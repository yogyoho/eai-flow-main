"use client";

import { useState } from "react";

const NAV_ITEMS = [
  { key: "dashboard", label: "仪表盘", icon: "📊" },
  { key: "projects", label: "项目立项", icon: "📁" },
  { key: "tasks", label: "任务管理", icon: "✅" },
  { key: "milestones", label: "里程碑", icon: "🏁" },
  { key: "risks", label: "风险管理", icon: "⚠️" },
  { key: "resources", label: "资源配置", icon: "👥" },
];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "";

function getToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

type Stats = {
  total_projects: number;
  draft_count: number;
  ongoing_count: number;
  completed_count: number;
  suspended_count: number;
  total_budget: number;
  total_tasks: number;
  pending_tasks: number;
  overdue_tasks: number;
  high_risks: number;
};

type Project = {
  id: string;
  project_no: string;
  name: string;
  project_type: string;
  status: string;
  progress: number;
  created_at: string;
};

export default function ProjectPage() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [stats, setStats] = useState<Stats | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ data: Stats }>("/dashboard/stats");
      setStats(data.data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadProjects() {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ data: { items: Project[]; total: number } }>("/projects?limit=50");
      setProjects(data.data.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleTabChange(tab: string) {
    setActiveTab(tab);
    if (tab === "dashboard") await loadDashboard();
    if (tab === "projects") await loadProjects();
  }

  const StatusBadge = ({ status }: { status: string }) => {
    const colors: Record<string, string> = {
      draft: "bg-gray-100 text-gray-700",
      ongoing: "bg-blue-100 text-blue-800",
      completed: "bg-green-100 text-green-800",
      suspended: "bg-red-100 text-red-800",
    };
    return (
      <span className={`px-2 py-1 rounded text-xs ${colors[status] || "bg-gray-100"}`}>
        {status}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">项目管理</h1>
          <p className="text-sm text-gray-500">EAIFlow 企业项目管理模块</p>
        </div>
        <div className="flex gap-2">
          {["dashboard", "projects", "tasks", "risks"].map((tab) => (
            <button
              key={tab}
              onClick={() => handleTabChange(tab)}
              className={`px-4 py-2 rounded text-sm ${
                activeTab === tab
                  ? "bg-blue-600 text-white"
                  : "bg-white border text-gray-700 hover:bg-gray-50"
              }`}
            >
              {NAV_ITEMS.find((n) => n.key === tab)?.icon} {NAV_ITEMS.find((n) => n.key === tab)?.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
            {error}
          </div>
        )}

        {activeTab === "dashboard" && !stats && !loading && (
          <button
            onClick={loadDashboard}
            className="px-6 py-3 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            加载仪表盘
          </button>
        )}

        {loading && <div className="text-gray-500 py-8 text-center">加载中...</div>}

        {activeTab === "dashboard" && stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {[
              { label: "项目总数", value: stats.total_projects },
              { label: "总预算", value: `¥${Number(stats.total_budget).toLocaleString()}` },
              { label: "草稿", value: stats.draft_count, color: "text-gray-600" },
              { label: "进行中", value: stats.ongoing_count, color: "text-blue-600" },
              { label: "已完成", value: stats.completed_count, color: "text-green-600" },
              { label: "已暂停", value: stats.suspended_count, color: "text-red-600" },
              { label: "任务总数", value: stats.total_tasks },
              { label: "待处理任务", value: stats.pending_tasks, color: "text-orange-600" },
              { label: "逾期任务", value: stats.overdue_tasks, color: "text-red-600" },
              { label: "高风险", value: stats.high_risks, color: "text-red-600" },
            ].map((item) => (
              <div key={item.label} className="bg-white rounded-lg border p-4 shadow-sm">
                <div className="text-sm text-gray-500">{item.label}</div>
                <div className={`text-2xl font-semibold mt-1 ${(item as { color?: string }).color || "text-gray-900"}`}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === "projects" && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-medium">项目列表</h2>
              <button
                onClick={loadProjects}
                className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
              >
                刷新
              </button>
            </div>
            {projects.length > 0 ? (
              <table className="w-full bg-white border rounded-lg overflow-hidden">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">项目编号</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">名称</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">类型</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">状态</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">进度</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {projects.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm text-gray-900">{p.project_no}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">{p.name}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">{p.project_type}</td>
                      <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                      <td className="px-4 py-3 text-sm text-gray-900">{(p.progress * 100).toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="text-center text-gray-400 py-8">
                {loading ? "加载中..." : "暂无数据，点击刷新按钮加载"}
              </div>
            )}
          </div>
        )}

        {activeTab !== "dashboard" && activeTab !== "projects" && (
          <div className="text-center text-gray-400 py-12">
            <div className="text-4xl mb-4">{NAV_ITEMS.find((n) => n.key === activeTab)?.icon}</div>
            <div className="text-lg font-medium">{NAV_ITEMS.find((n) => n.key === activeTab)?.label}</div>
            <div className="text-sm text-gray-400 mt-2">该模块正在开发中...</div>
          </div>
        )}
      </div>
    </div>
  );
}
