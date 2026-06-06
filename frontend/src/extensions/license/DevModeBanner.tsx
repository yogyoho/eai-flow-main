// frontend/src/extensions/license/DevModeBanner.tsx
"use client";

export function DevModeBanner() {
  return (
    <div className="pointer-events-none fixed bottom-2 right-2 z-50 select-none rounded bg-amber-500/20 px-3 py-1 text-xs font-medium text-amber-700 backdrop-blur-sm dark:bg-amber-500/10 dark:text-amber-400">
      DEV MODE — License Bypassed
    </div>
  );
}
