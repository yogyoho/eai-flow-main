// frontend/src/extensions/license/ModuleLockedPage.tsx
"use client";

interface ModuleLockedPageProps {
  module: string;
}

const MODULE_LABELS: Record<string, string> = {
  platform: "基础平台",
  project: "项目协作",
  dashboard: "工作台",
  typography: "报告输出",
  contract_price: "合同价格分析",
};

export function ModuleLockedPage({ module }: ModuleLockedPageProps) {
  const label = MODULE_LABELS[module] ?? module;

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="max-w-md text-center">
        <div className="mb-4 text-5xl">🚫</div>
        <h2 className="mb-2 text-xl font-semibold text-gray-900 dark:text-white">
          {label} 模块未授权
        </h2>
        <p className="text-gray-600 dark:text-gray-400">
          当前许可证不包含「{label}」模块。如需使用，请联系管理员升级许可证。
        </p>
      </div>
    </div>
  );
}
