// frontend/src/extensions/license/ModuleLockedPage.tsx
"use client";

import { MODULE_LABELS } from "./labels";

interface ModuleLockedPageProps {
  module: string;
}

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
