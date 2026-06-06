// frontend/src/extensions/license/ModuleLockedPage.tsx
"use client";

interface ModuleLockedPageProps {
  module: string;
}

const MODULE_LABELS: Record<string, string> = {
  project: "项目管理",
  docmgr: "文档管理",
  knowledge: "知识库",
  collab: "协同编辑",
  report: "报告生成",
  approval: "审批流程",
  workflow: "工作流",
  dashboard: "仪表盘",
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
