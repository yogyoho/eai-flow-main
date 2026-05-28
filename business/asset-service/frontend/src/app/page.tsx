"use client";

import { useState } from "react";

const NAV_ITEMS = [
  { key: "dashboard", label: "仪表盘", icon: "📊" },
  { key: "assets", label: "资产台账", icon: "🏢" },
  { key: "maintenance", label: "维修保养", icon: "🔧" },
  { key: "allocation", label: "调拨管理", icon: "🔄" },
  { key: "depreciation", label: "折旧计算", icon: "📉" },
  { key: "check", label: "资产盘点", icon: "📋" },
  { key: "scrap", label: "报废管理", icon: "🗑️" },
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
  total_assets: number;
  total_value: number;
  normal_count: number;
  maintenance_count: number;
  allocated_count: number;
  scrapped_count: number;
  pending_maintenance: number;
  pending_allocations: number;
  pending_scraps: number;
};

type Asset = {
  id: string;
  asset_no: string;
  name: string;
  category: string;
  status: string;
  current_value: number;
  created_at: string;
};

export default function AssetPage() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [stats, setStats] = useState<Stats | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
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

  async function loadAssets() {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ data: { items: Asset[]; total: number } }>("/assets?limit=50");
      setAssets(data.data.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleTabChange(tab: string) {
    setActiveTab(tab);
    if (tab === "dashboard") await loadDashboard();
    if (tab === "assets") await loadAssets();
  }

  const StatusBadge = ({ status }: { status: string }) => {
    const colors: Record<string, string> = {
      normal: "bg-green-100 text-green-800",
      maintenance: "bg-yellow-100 text-yellow-800",
      allocated: "bg-blue-100 text-blue-800",
      scrapped: "bg-gray-100 text-gray-800",
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
          <h1 className="text-xl font-semibold text-gray-900">资产管理</h1>
          <p className="text-sm text-gray-500">EAIFlow 企业资产管理模块</p>
        </div>
        <div className="flex gap-2">
          {["dashboard", "assets", "maintenance", "allocation"].map((tab) => (
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
              { label: "资产总数", value: stats.total_assets },
              { label: "资产总值", value: `¥${Number(stats.total_value).toLocaleString()}` },
              { label: "正常", value: stats.normal_count, color: "text-green-600" },
              { label: "维修中", value: stats.maintenance_count, color: "text-yellow-600" },
              { label: "已调拨", value: stats.allocated_count, color: "text-blue-600" },
              { label: "已报废", value: stats.scrapped_count, color: "text-gray-600" },
              { label: "待保养", value: stats.pending_maintenance, color: "text-orange-600" },
              { label: "待审批调拨", value: stats.pending_allocations, color: "text-orange-600" },
              { label: "待审批报废", value: stats.pending_scraps, color: "text-orange-600" },
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

        {activeTab === "assets" && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-medium">资产列表</h2>
              <button
                onClick={loadAssets}
                className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
              >
                刷新
              </button>
            </div>
            {assets.length > 0 ? (
              <table className="w-full bg-white border rounded-lg overflow-hidden">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">资产编号</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">名称</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">类别</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">状态</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">当前价值</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {assets.map((asset) => (
                    <tr key={asset.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm text-gray-900">{asset.asset_no}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">{asset.name}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">{asset.category}</td>
                      <td className="px-4 py-3"><StatusBadge status={asset.status} /></td>
                      <td className="px-4 py-3 text-sm text-gray-900">
                        {asset.current_value != null ? `¥${Number(asset.current_value).toLocaleString()}` : "-"}
                      </td>
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

        {activeTab !== "dashboard" && activeTab !== "assets" && (
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
