// frontend/src/extensions/license/LicenseShell.tsx
"use client";

import { DevModeBanner } from "./DevModeBanner";
import { GracePeriodBanner } from "./GracePeriodBanner";
import { SystemLockedPage } from "./SystemLockedPage";
import { useLicense } from "./useLicense";

export function LicenseShell({ children }: { children: React.ReactNode }) {
  const { isDevMode, isLocked, isLoading } = useLicense();

  // Don't block rendering while loading license status
  if (isLoading) {
    return <>{children}</>;
  }

  return (
    <>
      <GracePeriodBanner />
      {isLocked ? <SystemLockedPage /> : children}
      {isDevMode && <DevModeBanner />}
    </>
  );
}
