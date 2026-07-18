# EAI 品牌定制白名单 v0.5.0

> 基线：`v0.5.0` (commit `44233079`)
> 上游：`bytedance/deer-flow` main 分支
> 用途：下次更新上游代码时，以下文件需要保留 EAI 定制内容，不得直接用上游版本覆盖。

---

## 一、前端共享代码定制（非 extensions，直接修改上游文件）

### 1.1 根布局 & 认证

| 文件 | 定制内容 | 说明 |
|------|---------|------|
| `src/app/layout.tsx` | +CoreAuthProvider +LicenseShell +ChunkErrorHandler | 双 AuthProvider 架构（extensions + core），许可证控制，chunk 加载兜底 |
| `src/app/(auth)/login/page.tsx` | 北京华宇品牌登录页 | 左侧背景图 + 品牌文案，右侧卡片表单，直接 POST /api/v1/auth/login/local |
| `src/app/(auth)/layout.tsx` | 去掉 AuthProvider 包裹 | 根 layout 已提供，此处只做 server-side redirect guard |
| `src/app/(auth)/setup/page.tsx` | EAIFlow 品牌文字 | 标题从 DeerFlow → EAIFlow |
| `src/app/page.tsx` | LandingNew 组件 | 替换上游 Header→Hero→Sections 为标准 landing，使用 EAI 定制 LandingNew |

### 1.2 工作区侧栏

| 文件 | 定制内容 | 说明 |
|------|---------|------|
| `src/components/workspace/workspace-header.tsx` | Bot 图标 + "AI智能体" | 替换上游 "DF" 缩写和 "DeerFlow" 文字 |
| `src/components/workspace/workspace-nav-menu.tsx` | 知识库/知识工厂/设置/退出 | 替换上游 GitHub/Bug/Website 链接 |
| `src/components/workspace/workspace-nav-chat-list.tsx` | +文档空间入口 | 新增 `/docmgr` 侧栏菜单项 |
| `src/components/workspace/welcome.tsx` | Bot 图标 + dark mode | 替换 wave emoji，暗色模式自适配 |
| `src/app/workspace/layout.tsx` | gateway offline 页面样式 | Retry + Logout 按钮 |

### 1.3 设置对话框

| 文件 | 定制内容 | 说明 |
|------|---------|------|
| `src/components/workspace/settings/settings-dialog.tsx` | 去掉 Appearance + About tab，加 WeChat tab | defaultSection 改为 "account" |
| `src/components/workspace/settings/skill-settings-page.tsx` | +扩展(legacy) tab | EAI 自定义技能归类为 legacy，需单独 tab |
| `src/components/workspace/settings/wechat-settings-page.tsx` | **本地独有** | 微信绑定码生成 + 机器人绑定 + 分享二维码 |
| `src/components/workspace/settings/about-content.ts` | EAIFlow 品牌 | 关于页文字 |

### 1.4 主题 & 样式

| 文件 | 定制内容 | 说明 |
|------|---------|------|
| `src/components/theme-provider.tsx` | 去掉 forcedTheme | 首页不再强制 dark 模式 |
| `src/styles/globals.css` | @fontsource + ProseMirror + dark 样式 | 替换 Google Fonts CDN，内网兼容 |
| `src/components/landing-new/App.tsx` | 北京华宇 LandingNew | EAI 独有首页，含 stats cards + quick access |
| `src/components/landing-new/index.css` | dark mode glass-card + grid-pattern | 暗色毛玻璃卡片样式 |

### 1.5 i18n

| 文件 | 定制内容 | 说明 |
|------|---------|------|
| `src/core/i18n/locales/zh-CN.ts` | +settings.basic.* +settings.wechat.* +DeerFlow→EAIFlow | EAI 专有翻译 key |
| `src/core/i18n/locales/en-US.ts` | +settings.basic.* +settings.wechat.* +DeerFlow→EAIFlow | EAI 专有翻译 key |

### 1.6 全局品牌替换

所有 `.tsx`/`.ts`/`.css`/`.mdx` 文件中的 `DeerFlow` 文字替换为 `EAIFlow`（不影响技术路径如 `deerflow` 包名、`DEER_FLOW` 环境变量、`bytedance/deer-flow` URL）。

### 1.7 其他组件微调

| 文件 | 定制内容 |
|------|---------|
| `src/components/workspace/workspace-container.tsx` | 容器样式微调 |
| `src/components/workspace/settings/grouped-model-select.tsx` | 分组模型选择器 |
| `src/components/workspace/artifacts/save-artifact-to-doc-button.tsx` | 保存产物到文档空间 |
| `src/components/workspace/save-to-doc-button.tsx` | 保存到文档按钮 |
| `src/components/chunk-error-handler.tsx` | Chunk 加载错误处理 |
| `src/app/workspace/workspace-content.tsx` | workspace 内容布局 |
| `src/core/threads/hooks.ts` | displayThreadId 参数（2 行差异） |

---

## 二、后端共享代码定制

| 文件 | 定制内容 | 说明 |
|------|---------|------|
| `backend/app/gateway/app.py` | +input_polish router +channel_service on app.state | input polish + wechat 端点支持 |
| `backend/app/gateway/auth_middleware.py` | +OAuth/wechat/license 公开路径 | /providers, /oauth/, /callback/, /api/extensions/*, /api/license/* |
| `backend/app/gateway/deps.py` | require_admin_user 签名对齐 | 上游有 `detail` 参数，本地同步 |
| `backend/app/gateway/routers/channel_connections.py` | +wechat bind/bind-status/bind-code/share-qrcode 端点 | 微信管理 API |
| `backend/app/gateway/routers/auth.py` | 上游完整版（831 行） | 包含 OAuth/OIDC 完整流程 |

---

## 三、EAI 扩展模块（上游无此目录，完全保留）

| 目录 | 模块 | 说明 |
|------|------|------|
| `frontend/src/extensions/` | 全部 | EAI 前端扩展（dashboard/project/docmgr/knowledge-factory/contract-price/workflow/collab/license/app-center/data-source/output/plugin/approval/shell） |
| `backend/app/extensions/` | 全部 | EAI 后端扩展（对应前端模块的 API + database + MCP） |
| `frontend/src/app/admin/` | 管理后台 | 用户/角色/部门管理 |
| `frontend/src/app/settings/` | EAI 设置页 | basic-settings + DataSource + License |
| `frontend/src/app/dashboard/` | 工作台 | EAI 仪表盘 |
| `frontend/src/app/projects/` | 项目管理 | 报告项目 + SciFi 详情 |
| `frontend/src/app/docmgr/` | 文档空间 | 文档管理 |
| `frontend/src/app/knowledge/` | 知识库 | 知识库页面 |
| `frontend/src/app/knowledge-factory/` | 知识工厂 | 模板/法规/合规 |
| `frontend/src/app/contract-price/` | 合同价格 | 价格分析 |
| `frontend/src/app/workflow-admin/` | 流程管理 | 审批模板 |
| `frontend/src/app/cad-design/` | CAD 设计 | 3D 模型查看 |
| `frontend/src/app/writing/` | 智能写作 | AI 辅助写作 |
| `frontend/src/app/output/` | 报告输出 | 排版导出 |
| `frontend/src/app/plugins/` | 插件市场 | 插件管理 |
| `frontend/src/app/data-sources/` | 数据源 | 数据源连接 |
| `frontend/src/app/app-center/` | 应用中心 | 应用聚合页 |
| `frontend/src/app/test-editor/` | 测试编辑器 | TipTap 测试 |
| `frontend/src/app/api/collab/ai-chat/route.ts` | 协作 AI | 协作编辑 AI 对话 |
| `frontend/src/app/api/memory/` | 记忆 API | 扩展记忆路由 |

---

## 四、EAI 独立新增文件（上游不存在）

| 文件 | 说明 |
|------|------|
| `frontend/src/core/auth/static-user.ts` | 静态网站模式用户 stub |
| `frontend/src/core/auth/setup.ts` | 从上游恢复（上游有，本地之前缺失） |
| `frontend/src/core/channels/` | wechat hooks/api/types（新增） |
| `frontend/src/components/ui/page-loading-overlay.tsx` | 页面加载层 |
| `frontend/src/components/ui/admin-select.tsx` | 管理后台选择器 |
| `frontend/src/components/ui/calendar.tsx` | 日历组件 |
| `frontend/src/components/ui/checkbox.tsx` | 复选框 |
| `frontend/src/components/ui/styled-checkbox.tsx` | 样式复选框 |
| `frontend/src/components/ui/word-rotate.tsx` | 文字轮播 |
| `frontend/src/components/landing-new/` | EAI 定制 Landing 页 |
| `frontend/src/components/workspace/agent-welcome.tsx` | Agent 欢迎页 |
| `frontend/src/components/workspace/agents/` | Agent 管理组件 |
| `frontend/src/components/workspace/settings/wechat-settings-page.tsx` | 微信设置页 |
| `frontend/src/components/workspace/settings/grouped-model-select.tsx` | 分组模型选择 |

---

## 五、上游更新操作指南

```bash
# 1. 拉取上游最新代码
git fetch bytedance main

# 2. 对比差异（只关注共享代码，排除 extensions）
git diff bytedance/main HEAD -- frontend/src/ ':!frontend/src/extensions/'
git diff bytedance/main HEAD -- backend/app/gateway/ ':!backend/app/extensions/'

# 3. 对于上游无变化的文件 → 直接 checkout 上游版本
git checkout bytedance/main -- <file>

# 4. 对于本白名单中的文件 → 逐行对比，保留 EAI 定制部分
#    （参考上方表格中的"定制内容"列）

# 5. 对于 extensions/ 目录 → 永远不要用上游覆盖
```

---

## 六、检查清单（每次上游同步后）

- [ ] `layout.tsx` — CoreAuthProvider + LicenseShell 仍存在
- [ ] `(auth)/login/page.tsx` — 北京华宇品牌布局仍存在
- [ ] `workspace-header.tsx` — Bot 图标 + "AI智能体"
- [ ] `workspace-nav-menu.tsx` — 知识库/知识工厂菜单项
- [ ] `workspace-nav-chat-list.tsx` — 文档空间入口
- [ ] `welcome.tsx` — Bot 图标 + dark mode
- [ ] `globals.css` — @fontsource 导入存在
- [ ] `theme-provider.tsx` — forcedTheme 为 undefined
- [ ] `settings-dialog.tsx` — 无 Appearance/About tab，有 WeChat tab
- [ ] `skill-settings-page.tsx` — 有"扩展" tab
- [ ] `auth_middleware.py` — OAuth/wechat 公开路径
- [ ] `deps.py` — require_admin_user 有 detail 参数
- [ ] `app.py` — input_polish router + channel_service on app.state
- [ ] `extensions/` 目录未被覆盖
- [ ] 全局 DeerFlow→EAIFlow 替换完整
