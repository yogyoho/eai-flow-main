// frontend/src/extensions/license/DevModeBanner.tsx
"use client";

export function DevModeBanner() {
  return (
    <div className="pointer-events-none fixed right-3 bottom-3 z-50 select-none">
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/25 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold tracking-wider text-amber-700 uppercase backdrop-blur-md dark:text-amber-400">
        <span className="size-1.5 animate-pulse rounded-full bg-amber-500" />
        Dev Mode
      </span>
    </div>
  );
}
