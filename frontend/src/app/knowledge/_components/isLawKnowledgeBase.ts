/**
 * 法规标准系统库种子名都以此开头(后端 _ensure_kb_registered 用 config.py
 * law.dataset_display_info 的 name 注册:"法规标准库 — 法律/法规/规章" /
 * "法规标准库 — 标准/规范")。管理员重命名该 KB 后识别失效、上传按钮恢复
 * (等同改动前现状),可接受。
 * 独立成文件而非放进 KnowledgeBaseDetail.tsx:组件文件依赖树重,单测 import
 * 会拖入 kbApi/lucide/UploadModal 等。
 */
export const isLawKnowledgeBase = (name: string) =>
  name.startsWith("法规标准库");
