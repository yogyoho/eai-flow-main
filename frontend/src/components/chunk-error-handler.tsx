"use client";

import { useEffect } from "react";

/**
 * Catches ChunkLoadError from dynamic imports (common with Turbopack HMR)
 * and offers a one-click page reload instead of a cryptic error screen.
 *
 * ponytail: global listener, sufficient until we need per-component retry.
 */
export function ChunkErrorHandler() {
  useEffect(() => {
    const handler = (event: PromiseRejectionEvent) => {
      const msg = String(event?.reason?.message ?? event?.reason ?? "");
      if (msg.includes("ChunkLoadError") || msg.includes("Failed to load chunk")) {
        event.preventDefault();
        // Only show the reload overlay once per page session
        if (document.getElementById("__chunk-error-overlay")) return;

        const overlay = document.createElement("div");
        overlay.id = "__chunk-error-overlay";
        overlay.style.cssText =
          "position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.55);font-family:system-ui,sans-serif";
        overlay.innerHTML = `
          <div style="background:#fff;border-radius:8px;padding:24px 32px;max-width:360px;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,0.15)">
            <p style="font-size:16px;font-weight:600;margin:0 0 8px;color:#212529">页面需要刷新</p>
            <p style="font-size:14px;color:#6c757d;margin:0 0 16px">检测到新版本，请刷新页面以继续。</p>
            <button id="__chunk-reload-btn" style="padding:8px 20px;background:#0d6efd;color:#fff;border:none;border-radius:4px;font-size:14px;cursor:pointer">刷新页面</button>
          </div>`;
        document.body.appendChild(overlay);

        document.getElementById("__chunk-reload-btn")?.addEventListener("click", () => {
          window.location.reload();
        });
      }
    };

    window.addEventListener("unhandledrejection", handler);
    return () => window.removeEventListener("unhandledrejection", handler);
  }, []);

  return null;
}
