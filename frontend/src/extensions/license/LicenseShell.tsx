// frontend/src/extensions/license/LicenseShell.tsx
"use client";

import { useEffect, useState } from "react";
import { DevModeBanner } from "./DevModeBanner";
import { GracePeriodBanner } from "./GracePeriodBanner";
import { SystemLockedPage } from "./SystemLockedPage";

interface LicenseState {
  isDevMode: boolean;
  inGracePeriod: boolean;
  isLocked: boolean;
  gracePeriodDays: number;
}

const POLL_INTERVAL = 5 * 60 * 1000; // 5 minutes

export function LicenseShell({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<LicenseState | null>(null);

  useEffect(() => {
    let mounted = true;

    async function check() {
      try {
        const res = await fetch("/api/license/status");
        if (!res.ok || !mounted) return;
        const data = await res.json();
        if (!mounted) return;
        setState({
          isDevMode: data.is_dev_mode ?? false,
          inGracePeriod: data.in_grace_period ?? false,
          isLocked: !data.valid && !data.in_grace_period,
          gracePeriodDays: data.grace_period_remaining_days ?? 0,
        });
      } catch {
        // Silently ignore fetch errors — don't block the app
      }
    }

    check();
    const interval = setInterval(check, POLL_INTERVAL);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Don't block rendering while loading
  if (!state) {
    return <>{children}</>;
  }

  return (
    <>
      <GracePeriodBanner />
      {state.isLocked ? <SystemLockedPage /> : children}
      {state.isDevMode && <DevModeBanner />}
    </>
  );
}
