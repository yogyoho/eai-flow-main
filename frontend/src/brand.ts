// EAI-CUSTOM: 按客户品牌化（构建期注入）。
// 镜像 version.ts 的 NEXT_PUBLIC_* 模式：process.env.NEXT_PUBLIC_* 在 `next build` 时
// 被内联烘焙进产物。导出常量供 layout / setup / footer 等处统一引用，避免散落硬编码。
// offline-export.sh 构建前端时通过 --build-arg 注入（见 deploy.conf 的 BRAND_* 字段）。
export const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME || "EAIFlow";
export const BRAND_FOOTER = process.env.NEXT_PUBLIC_BRAND_FOOTER || "";
