// frontend/src/extensions/license/GracePeriodBanner.tsx
"use client";

import { useLicense } from "./useLicense";

export function GracePeriodBanner() {
  const { inGracePeriod, gracePeriodDays } = useLicense();

  if (!inGracePeriod) return null;

  return (
    <div className="flex items-center justify-center gap-2 bg-yellow-50 px-4 py-2 text-sm text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300">
      <span>⏳</span>
      <span>
        许可证未激活
        {gracePeriodDays > 0
          ? `，${gracePeriodDays} 天后系统将锁定`
          : "，请尽快导入许可证"}
      </span>
    </div>
  );
}
