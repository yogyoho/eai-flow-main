/// <reference types="vite/client" />

// explorer/ vendored 零改动：上游文件（GraphCanvas.tsx ×2、graphSceneState.ts ×1）使用
// process.env.NODE_ENV（当初从 Vite 移植进 Next 时的改写残留）。运行时由 vite.config.ts
// 的 define 按 mode 静态替换；此处仅补全局类型声明，避免给 vendored 文件本体加 @types/node。
declare var process: {
  env: {
    NODE_ENV?: string;
  };
};
