/**
 * 系统级只读知识库的按名识别（上传/编辑/删除按钮禁用 + 引导横幅）。
 * 管理员重命名该 KB 后识别失效、按钮恢复（等同改动前现状），可接受。
 * 独立成文件而非放进 KnowledgeBaseDetail.tsx：组件文件依赖树重，单测 import
 * 会拖入 kbApi/lucide/UploadModal 等。
 */

/**
 * 法规标准系统库种子名都以此开头（后端 law.service._ensure_kb_registered 用
 * config.py law.dataset_display_info 的 name 注册："法规标准库 — 法律/法规/规章" /
 * "法规标准库 — 标准/规范"）。
 */
export const isLawKnowledgeBase = (name: string) =>
  name.startsWith("法规标准库");

/**
 * 地质切片系统库（EAI-CUSTOM, 2026-09-05）：后端 geo_samples init 端点注册
 * （/pipeline/init-ragflow → knowledge_bases 表），切片由地质样例库「编译」自动
 * 写入 RAGFlow——精确名匹配（前缀会误伤普通库）。
 */
export const isGeoSlicesKnowledgeBase = (name: string) =>
  name === "固体矿产报告切片库";

/** 任一系统级只读库（列表/详情页按钮禁用统一入口）。 */
export const isReadOnlyKnowledgeBase = (name: string) =>
  isLawKnowledgeBase(name) || isGeoSlicesKnowledgeBase(name);

/** 只读库的按钮禁用提示文案（编辑/删除/同步共用）。 */
export const readOnlyKBTitle = (name: string) =>
  isGeoSlicesKnowledgeBase(name)
    ? "地质切片系统库，由 地质样例库「编译」自动写入"
    : "法规标准系统库，请在 知识工厂 → 法规标准 中管理";
