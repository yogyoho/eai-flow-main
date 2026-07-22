# TODOS — 报告模板提取

## 模板提取（knowledge_factory）

### P2 — PDF 解析增强
**Priority:** P2
**What:** 安装 PyMuPDF (fitz) 到 gateway Docker 镜像，PDF 解析改用字体大小启发式检测标题（当前仅基础文本提取 + 正则）。
**Why:** 扫描 PDF 走 RAGFlow OCR 兜底，文字型 PDF 缺 Heading 样式检测，章节层级丢失。PyMuPDF 的 `page.get_text("dict")` 能拿到字体大小/加粗，可做高置信度标题推断。
**Context:** `backend/app/extensions/knowledge_factory/doc_parser.py:parse_pdf` 当前 try import fitz 失败则降级。`pyproject.toml` 加 `pymupdf>=1.23.0` 后需 `make rebuild-gateway`（依赖变更必须重建镜像，restart 无效）。
**Depends on:** 镜像重建（重操作，择期）。

### P2 — 表格合并单元格解析
**Priority:** P2
**What:** expat 解析器处理 Word 表格的 `<w:gridSpan>`（水平合并）和 `<w:vMerge>`（垂直合并）。
**Why:** 当前 `doc_parser._parse_docx_expat` 把每个 `<w:tc>` 当独立 cell，合并单元格读成空或重复，富元数据 `table_schemas` 的 columns 结构失真。
**Context:** 需给 `DocTable` schema 加合并信息字段（如 `spans`），expat 状态机增加 gridSpan/vMerge 跟踪。LLM 主要看 caption + 大致结构，精确合并非阻塞，但提升表格定义准确度。
**Depends on:** DocTable schema 变更（向后兼容，optional 字段）。

### P2 — 集成测试 + LLM eval
**Priority:** P2
**What:** 建立 golden dataset（如横城矿区 14 章已知结构）回归测试，验证章节推断准确率 + grounding 效果。
**Why:** 当前 19 个单元测试覆盖 doc_parser，但完整流水线（含 LLM）无自动化验证。每次提取需 3-50 分钟手动跑，回归靠人眼。
**Context:** LLM eval 在 CI 需稳定端点或 mock 录制/回放。先做 mock 录制（record/replay）验证 pipeline 不崩 + 章节数稳定，后续加 golden dataset 质量阈值。
**Depends on:** 选定 eval 框架（vcr.py / 自建录制）。

### P3 — Skill prompt 外化未连接
**Priority:** P3
**What:** `llm.py` 的 `_SCHEMA_INFERENCE_SYSTEM_PROMPT` 等仍是硬编码，`skills/custom/kf-extract-template/SKILL.md` 的 prompt 模板仅作文档，未连接到实际 LLM 调用。
**Why:** 用户期望"改 SKILL.md 即调 prompt，不碰 Python"。当前调 prompt 仍需改 `llm.py` + 重启。
**Context:** 需 llm.py 从 SKILL.md frontmatter 或独立 yaml 读 prompt。低频改动，延后。

## 已完成（本 session）
- [x] 章节推断稳定（expat 替代 python-docx，50MB 4.5min）
- [x] 富元数据合并 LLM pass（表格/公式/脚本/剖面）
- [x] 原文锚定 grounding（精确切片 + LLM 输出校验减幻觉）
- [x] 元数据并发抽取 + 进度反馈（15min→3-5min）
- [x] section offset 内存优化（去重复存储）
- [x] 错误可观测性（失败/grounding 统计透传 UI）
- [x] kb:upload 权限修复（project_manager 角色）
- [x] StructureType 枚举 fallback（修模板编辑 500）
- [x] kf_extract_template MCP 工具 + skill
- [x] 直接上传 Word/PDF（提取对话框）
