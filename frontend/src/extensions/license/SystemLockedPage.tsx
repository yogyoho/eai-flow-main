// frontend/src/extensions/license/SystemLockedPage.tsx
"use client";

export function SystemLockedPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-950">
      <div className="max-w-md text-center">
        <div className="mb-4 text-6xl">🔒</div>
        <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-white">
          系统未激活
        </h1>
        <p className="mb-6 text-gray-600 dark:text-gray-400">
          许可证宽限期已结束。请联系管理员导入有效的许可证文件以恢复系统访问。
        </p>
        <p className="text-sm text-gray-400">
          管理员请登录管理后台导入 license.lic 文件
        </p>
      </div>
    </div>
  );
}
