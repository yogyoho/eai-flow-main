// frontend/src/extensions/license/DevModeBanner.tsx
"use client";

export function DevModeBanner() {
  return (
    <div className="pointer-events-none fixed bottom-3 right-3 z-50 select-none">
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/25 bg-amber-500/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-700 backdrop-blur-md dark:text-amber-400">
        <span className="size-1.5 rounded-full bg-amber-500 animate-pulse" />
        Dev Mode
      </span>
    </div>
  );
}
