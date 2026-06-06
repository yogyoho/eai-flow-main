// frontend/src/extensions/license/GracePeriodBanner.tsx
"use client";

import { useEffect, useState } from "react";

export function GracePeriodBanner() {
  const [show, setShow] = useState(false);
  const [days, setDays] = useState(0);

  useEffect(() => {
    let mounted = true;
    async function check() {
      try {
        const res = await fetch("/api/license/status");
        const data = await res.json();
        if (!mounted) return;
        if (data.in_grace_period) {
          setShow(true);
          setDays(data.grace_period_remaining_days ?? 0);
        }
      } catch {
        // ignore
      }
    }
    check();
    return () => { mounted = false; };
  }, []);

  if (!show) return null;

  return (
    <div className="flex items-center justify-center gap-2 bg-yellow-50 px-4 py-2 text-sm text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300">
      <span>⏳</span>
      <span>
        许可证未激活
        {days > 0 ? `，${days} 天后系统将锁定` : "，请尽快导入许可证"}
      </span>
    </div>
  );
}
