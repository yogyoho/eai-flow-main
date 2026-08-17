// frontend/src/extensions/license/LicensePage.tsx
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileDown } from "lucide-react";
import { useState } from "react";

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
      void queryClient.invalidateQueries({ queryKey: ["license"] });
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
    return map[t ?? ""] ?? t ?? "—";
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">许可证管理</h1>

      {/* Status Card */}
      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold">当前许可证</h2>
        {status?.is_dev_mode && (
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-amber-500/30 bg-gradient-to-r from-amber-500/5 via-amber-500/10 to-amber-500/5 px-4 py-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-amber-500/15 text-base leading-none">
              &#9889;
            </span>
            <div>
              <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">
                开发模式已启用
              </p>
              <p className="text-xs text-amber-600/80 dark:text-amber-400/70">
                许可证验证已跳过，所有功能模块均可用
              </p>
            </div>
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
            <dd className="mt-1 font-mono text-xs break-all">
              {status?.machine_id ?? "—"}
            </dd>
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
            <dd>{formatDate(status?.expires_at ?? null)}</dd>
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
          <div className="mt-5">
            <span className="mb-3 block text-xs font-medium tracking-widest text-gray-400 uppercase">
              模块授权
            </span>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.entries(status.modules).map(([name, enabled]) => (
                <div
                  key={name}
                  className={`group relative overflow-hidden rounded-lg border px-3 py-2.5 transition-all duration-200 hover:shadow-md ${
                    enabled
                      ? "border-emerald-500/20 bg-emerald-500/[0.04] hover:border-emerald-500/40 hover:bg-emerald-500/[0.07] dark:border-emerald-500/15 dark:bg-emerald-500/[0.03]"
                      : "border-gray-200 bg-gray-50/50 dark:border-gray-700/50 dark:bg-gray-800/30"
                  }`}
                >
                  {/* top accent strip */}
                  <div
                    className={`absolute inset-x-0 top-0 h-px ${
                      enabled
                        ? "bg-gradient-to-r from-transparent via-emerald-400/60 to-transparent dark:via-emerald-400/40"
                        : "bg-gradient-to-r from-transparent via-gray-300 to-transparent dark:via-gray-600"
                    }`}
                  />
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`flex size-2 shrink-0 rounded-full ${
                        enabled
                          ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.4)] dark:bg-emerald-500 dark:shadow-[0_0_8px_rgba(52,211,153,0.3)]"
                          : "bg-gray-300 dark:bg-gray-600"
                      }`}
                    />
                    <span
                      className={`truncate text-[13px] font-medium ${
                        enabled
                          ? "text-gray-800 dark:text-gray-200"
                          : "text-gray-400 dark:text-gray-500"
                      }`}
                    >
                      {name}
                    </span>
                  </div>
                  <p className="mt-1 pl-[26px] text-[11px] text-gray-400 dark:text-gray-500">
                    {enabled ? "已授权" : "未授权"}
                  </p>
                </div>
              ))}
            </div>
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
          如已获取{" "}
          <code className="rounded bg-gray-100 px-1 py-0.5 text-xs dark:bg-gray-800">
            license.lic
          </code>{" "}
          文件，可直接导入。如尚未申请，请先下载申请文件并提交给厂商制作许可证。
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
            type="button"
            onClick={handleExport}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            <Download className="h-4 w-4" />
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
                  <th className="pr-4 pb-2">许可证 ID</th>
                  <th className="pr-4 pb-2">类型</th>
                  <th className="pr-4 pb-2">客户</th>
                  <th className="pr-4 pb-2">导入时间</th>
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
                    <td className="py-2 pr-4">
                      {formatDate(item.imported_at)}
                    </td>
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
