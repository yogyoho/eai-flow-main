"use client";

// EAI-CUSTOM 2026-10-29: 应用级 global-error(官方模式)。上游从未提供本文件,
// Next 走内建默认页;提供后获得品牌化错误 UI + digest 展示,并缩短错误路径。
// 注: 2026-10-29 回归测试曾怀疑本文件可绕过 next 16.4.0 的 /_global-error
// 预渲染崩溃(digest 569325325),实测无效——该崩溃另有根因,见回归记录。
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en" suppressHydrationWarning>
      <body
        style={{
          display: "flex",
          minHeight: "100vh",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "12px",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <h2 style={{ fontSize: "18px", margin: 0 }}>Something went wrong!</h2>
        {error?.digest ? (
          <p style={{ color: "#888", fontSize: "12px", margin: 0 }}>
            digest: {error.digest}
          </p>
        ) : null}
        <button
          onClick={reset}
          style={{
            padding: "6px 16px",
            cursor: "pointer",
            borderRadius: "6px",
            border: "1px solid #ccc",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
