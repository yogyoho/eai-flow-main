/**
 * EAI-CUSTOM: 镜像引入 canonical 测试——rstest 只发现 tests/unit/**（AGENTS.md 约定
 * 单测镜像 src 布局），而语义地图适配层的 canonical 测试按 plan 放在
 * src/extensions/ontology/__tests__/api-adapter.test.ts。此处引入即注册全部用例。
 */
import "@/extensions/ontology/__tests__/api-adapter.test";
