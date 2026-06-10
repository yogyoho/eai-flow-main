// frontend/src/extensions/license/LicensePage.tsx
"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileDown } from "lucide-react";
import {
  exportLicense,
  getLicenseHistory,
  getLicenseStatus,
  importLicense,
  type LicenseHistoryItem,
} from "./api";

export default function LicensePage() {
  const queryClient = useQueryClient();
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<string | null>(null);

  const { data: status } = useQuery({
    queryKey: ["license", "status"],
    queryFn: getLicenseStatus,
    refetchInterval: 5 * 60 * 1000,
  });

  const { data: history } = useQuery({
    queryKey: ["license", "history"],
    queryFn: () => getLicenseHistory(0, 20),
  });

  const importMutation = useMutation({
    mutationFn: importLicense,
    onSuccess: (data) => {
      setImportSuccess(data.message);
      setImportError(null);
      queryClient.invalidateQueries({ queryKey: ["license"] });
    },
    onError: (err: Error) => {
      setImportError(err.message);
      setImportSuccess(null);
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportError(null);
      setImportSuccess(null);
      importMutation.mutate(file);
    }
  };

  const handleExport = async () => {
    try {
      const blob = await exportLicense();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "license.lic";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Export errors are non-critical
    }
  };

  const handleDownloadRequest = () => {
    const requestData = {
      machine_id: status?.machine_id ?? "",
      generated_at: new Date().toISOString(),
      system_info: {
        hostname: status?.system_info?.hostname ?? "",
        platform: status?.system_info?.platform ?? navigator.platform ?? "",
      },
    };

    const blob = new Blob([JSON.stringify(requestData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "license_request.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const formatDate = (d: string | null) => {
    if (!d) return "—";
    return new Date(d).toLocaleDateString("zh-CN");
  };

  const typeLabel = (t: string | null | undefined) => {
    const map: Record<string, string> = {
      permanent: "永久",
      trial: "试用",
      subscription: "订阅",
      grace: "宽限期",
    };
    return map[t ?? ""] ?? (t ?? "—");
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">许可证管理</h1>

      {/* Status Card */}
      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold">当前许可证</h2>
        {status?.is_dev_mode && (
          <div className="mb-4 rounded bg-amber-100 px-3 py-2 text-sm text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
            ⚠️ 开发模式 — 许可证验证已跳过
          </div>
        )}
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-gray-500">状态</dt>
            <dd>
              {status?.in_grace_period ? (
                <span className="text-yellow-600">
                  宽限期 ({status.grace_period_remaining_days}天)
                </span>
              ) : status?.valid ? (
                <span className="text-green-600">有效</span>
              ) : (
                <span className="text-red-600">无效</span>
              )}
            </dd>
          </div>
          <div className="col-span-2">
            <dt className="text-gray-500">机器ID</dt>
            <dd className="font-mono text-xs break-all mt-1">{status?.machine_id ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">类型</dt>
            <dd>{typeLabel(status?.type)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">客户</dt>
            <dd>{status?.customer ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">到期时间</dt>
            <dd>{formatDate(status?.expires_at)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">用户数</dt>
            <dd>
              {status?.current_users ?? 0} / {status?.max_users ?? "∞"}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">剩余天数</dt>
            <dd>{status?.days_remaining ?? "—"}</dd>
          </div>
        </dl>

        {/* Module badges */}
        {status?.modules && Object.keys(status.modules).length > 0 && (
          <div className="mt-4">
            <dt className="mb-2 text-sm text-gray-500">模块授权</dt>
            <dd className="flex flex-wrap gap-2">
              {Object.entries(status.modules).map(([name, enabled]) => (
                <span
                  key={name}
                  className={`rounded-full px-3 py-1 text-xs ${
                    enabled
                      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                      : "bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500"
                  }`}
                >
                  {name}
                </span>
              ))}
            </dd>
          </div>
        )}

        {/* Warnings */}
        {status?.warnings && status.warnings.length > 0 && (
          <div className="mt-4 space-y-1">
            {status.warnings.map((w) => (
              <div
                key={w}
                className="rounded bg-orange-50 px-3 py-2 text-sm text-orange-700 dark:bg-orange-900/20 dark:text-orange-400"
              >
                ⚠ {w}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Import */}
      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold">导入许可证</h2>
        <p className="mb-4 text-sm text-gray-500">
          如已获取 <code className="rounded bg-gray-100 px-1 py-0.5 text-xs dark:bg-gray-800">license.lic</code> 文件，可直接导入。如尚未申请，请先下载申请文件并提交给厂商制作许可证。
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
            <FileDown className="h-4 w-4" />
            选择 .lic 文件
            <input
              type="file"
              accept=".lic"
              onChange={handleFileChange}
              className="hidden"
            />
          </label>
          <button
            type="button"
            onClick={handleDownloadRequest}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            <Download className="h-4 w-4" />
            申请许可证
          </button>
        </div>
        {importMutation.isPending && (
          <span className="ml-3 text-sm text-gray-500">导入中...</span>
        )}
        {importError && (
          <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
            {importError}
          </div>
        )}
        {importSuccess && (
          <div className="mt-3 rounded bg-green-50 px-3 py-2 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-400">
            {importSuccess}
          </div>
        )}
      </div>

      {/* Export */}
      {status?.valid && (
        <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900">
          <h2 className="mb-4 text-lg font-semibold">导出许可证</h2>
          <button
            onClick={handleExport}
            className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700"
          >
            下载 license.lic
          </button>
        </div>
      )}

      {/* History */}
      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold">导入历史</h2>
        {!history?.items.length ? (
          <p className="text-sm text-gray-400">暂无记录</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-2 pr-4">许可证 ID</th>
                  <th className="pb-2 pr-4">类型</th>
                  <th className="pb-2 pr-4">客户</th>
                  <th className="pb-2 pr-4">导入时间</th>
                  <th className="pb-2">状态</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((item: LicenseHistoryItem) => (
                  <tr key={item.id} className="border-b dark:border-gray-800">
                    <td className="py-2 pr-4 font-mono text-xs">
                      {item.jwt_jti}
                    </td>
                    <td className="py-2 pr-4">{typeLabel(item.type)}</td>
                    <td className="py-2 pr-4">{item.customer ?? "—"}</td>
                    <td className="py-2 pr-4">{formatDate(item.imported_at)}</td>
                    <td className="py-2">
                      {item.is_active ? (
                        <span className="text-green-600">生效中</span>
                      ) : (
                        <span className="text-gray-400">已替换</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
