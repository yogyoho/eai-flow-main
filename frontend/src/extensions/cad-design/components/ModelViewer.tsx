"use client";

import { createElement } from "react";

// model-viewer is a web component. Load it client-only (parent uses next/dynamic
// ssr:false) and render via createElement to avoid JSX intrinsic-element typing.
import "@google/model-viewer";

export default function ModelViewer({ src }: { src: string }) {
  return createElement("model-viewer", {
    src,
    alt: "CAD 零件预览",
    "auto-rotate": true,
    "camera-controls": true,
    "shadow-intensity": "1",
    "environment-image": "neutral",
    style: { width: "100%", height: "100%", minHeight: 420, display: "block" },
  });
}
