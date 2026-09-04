# 知识库管理页法规标准库收口为「只读引导」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 知识库管理页的两个法规标准系统知识库不再提供裸上传(隐藏「添加文件」按钮),并在描述下方渲染引导文案(带链接)指引用户到 知识工厂 → 法规标准 导入。

**Architecture:** 纯前端单点改动。新建 3 行 helper `isLawKnowledgeBase(name)`(按种子名前缀「法规标准库」识别),在 `KnowledgeBaseDetail.tsx` 中用它叠加隐藏上传按钮、条件渲染引导横幅。后端零改动(spec §3 Non-goals)。

**Tech Stack:** Next.js 16 / React 19 / Tailwind 4,单测 Rstest(node 环境),源码路径 `@/app/knowledge/_components/`。

**Spec:** `docs/superpowers/specs/2026-09-04-law-kb-upload-guidance-design.md`

---

### Task 1: helper `isLawKnowledgeBase` + 单测

**Files:**
- Create: `frontend/src/app/knowledge/_components/isLawKnowledgeBase.ts`
- Test: `frontend/tests/unit/app/knowledge/_components/isLawKnowledgeBase.test.ts`

- [ ] **Step 1: 写失败的单测**

先建测试目录中已有同类文件(`sources-sort.test.ts`),照其格式新建:

```ts
// frontend/tests/unit/app/knowledge/_components/isLawKnowledgeBase.test.ts
import { describe, expect, it } from "@rstest/core";

import { isLawKnowledgeBase } from "@/app/knowledge/_components/isLawKnowledgeBase";

describe("isLawKnowledgeBase", () => {
  it("matches seeded law KB display names", () => {
    // 两个种子名与 backend config.py → law.dataset_display_info 一致
    expect(isLawKnowledgeBase("法规标准库 — 法律/法规/规章")).toBe(true);
    expect(isLawKnowledgeBase("法规标准库 — 标准/规范")).toBe(true);
  });

  it("does not match ordinary KB names", () => {
    expect(isLawKnowledgeBase("我的知识库")).toBe(false);
    expect(isLawKnowledgeBase("合同模板库")).toBe(false);
    expect(isLawKnowledgeBase("")).toBe(false);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && pnpm test tests/unit/app/knowledge/_components/isLawKnowledgeBase.test.ts
```

Expected: FAIL(模块不存在 / import 报错)。

- [ ] **Step 3: 写最小实现**

```ts
// frontend/src/app/knowledge/_components/isLawKnowledgeBase.ts
// 法规标准系统库种子名都以此开头(后端 _ensure_kb_registered 用 config.py
// law.dataset_display_info 的 name 注册:"法规标准库 — 法律/法规/规章" /
// "法规标准库 — 标准/规范")。管理员重命名该 KB 后识别失效、上传按钮恢复
// (等同改动前现状),可接受。
// 独立成文件而非放进 KnowledgeBaseDetail.tsx:组件文件依赖树重,单测 import
// 会拖入 kbApi/lucide/UploadModal 等。
export const isLawKnowledgeBase = (name: string) => name.startsWith("法规标准库");
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && pnpm test tests/unit/app/knowledge/_components/isLawKnowledgeBase.test.ts
```

Expected: PASS(2 tests)。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/knowledge/_components/isLawKnowledgeBase.ts frontend/tests/unit/app/knowledge/_components/isLawKnowledgeBase.test.ts
git commit -m "feat(knowledge): isLawKnowledgeBase helper 识别法规标准系统库"
```

---

### Task 2: 接入 KnowledgeBaseDetail(隐藏上传按钮 + 引导横幅)

**Files:**
- Modify: `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`(四处:imports、flag、按钮条件、横幅)

- [ ] **Step 1: 加 imports**

`next/link` 插在外部导入组(lucide-react 之后、react 之前,按字母序);`Info` 图标加进 lucide-react 具名导入(按字母序放 `FileText` 与 `Loader2` 之间);helper 加进相对导入组(`DocStatusBadge` 与 `sortSourcesByScore` 之间):

```tsx
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRightToLine,
  CheckCircle2,
  ChevronLeft,
  Copy,
  Database,
  Edit3,
  FileText,
  Info,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Search as SearchIcon,
  Settings,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
```

(仅示意位置与增量;其余既有导入不动。)相对导入组:

```tsx
import { ChunkModal } from "./ChunkModal";
import { CustomSelect } from "./CustomSelect";
import { DocStatusBadge } from "./DocStatusBadge";
import { isLawKnowledgeBase } from "./isLawKnowledgeBase";
import { sortSourcesByScore } from "./sources-sort";
import { ToastContainer, useToast } from "./toast";
import { UploadModal, formatFileSize } from "./UploadModal";
```

- [ ] **Step 2: 组件内计算 flag**

在 `const { can, is_admin, identity } = usePermission();`(组件顶部,约 86 行)之后加一行:

```tsx
  // EAI-CUSTOM: 法规标准系统库不提供直接上传,引导去知识工厂导入
  // (spec docs/superpowers/specs/2026-09-04-law-kb-upload-guidance-design.md)
  const isLawKb = isLawKnowledgeBase(kb.name);
```

- [ ] **Step 3: 隐藏上传按钮**

改「添加文件」按钮的条件(约 441-451 行),把注释一并更新:

```tsx
            {/* EAI-CUSTOM: gate upload button by kb:upload permission;
                法规标准系统库不提供直接上传(孤儿文档会绕过 Law 元数据层) */}
            {can("kb:upload") && !isLawKb && (
              <Button
                variant="ghost"
                onClick={() => setShowUpload(true)}
                className="text-foreground hover:text-primary"
              >
                <Plus className="h-4 w-4" />
                添加文件
              </Button>
            )}
```

- [ ] **Step 4: 描述下方渲染引导横幅**

在描述段落(约 432-435 行 `<p className="text-muted-foreground text-sm">…</p>`)之后、Header Card `</div>` 之前插入:

```tsx
          {isLawKb && (
            <p className="text-muted-foreground mt-2 flex items-start gap-1.5 text-xs">
              <Info className="text-info mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                本库为法规标准系统知识库,不提供直接上传。法规/标准文件请在
                <Link
                  href="/knowledge-factory?tab=law"
                  className="text-primary hover:underline"
                >
                  知识工厂 → 法规标准
                </Link>
                中导入——自动登记元数据(标准号/类型/行业等)并同步到本库。
              </span>
            </p>
          )}
```

- [ ] **Step 5: 全量静态检查**

```bash
cd frontend && pnpm lint && pnpm typecheck && pnpm test
```

Expected: lint 0 error、typecheck 0 error、单测全绿(既有债务基线不变)。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx
git commit -m "feat(knowledge): 法规标准库详情页隐藏裸上传+渲染知识工厂导入引导"
```

---

### Task 3: 容器内人工验证

**Files:** 无代码改动。

- [ ] **Step 1: 让容器吃到改动并验证**

前端 src 是 bind-mount 的,但 HMR 在 Docker 里可能不可靠——先重启:

```bash
docker compose -p eai-docker restart frontend
```

浏览器打开站点(dev 入口,nginx :2026 或当前环境实际使用的前端端口),用 admin@eai-flow.com / Admin@2026 登录,依次验证:

1. 知识库管理 → 打开「法规标准库 — 法律/法规/规章」详情:右上**无「添加文件」按钮**,描述下方有 ℹ️ 引导横幅,点「知识工厂 → 法规标准」跳到 `/knowledge-factory?tab=law`;
2. 同样验证「法规标准库 — 标准/规范」;
3. 打开任意普通 KB:**「添加文件」按钮仍在**,无引导横幅;
4. 知识工厂 → 法规标准 tab 功能不受影响(导入/同步照旧)。

- [ ] **Step 2: 收尾记录**

- 结果写回任务会话;若有偏差按 bug 流程记录到 `.wolf/buglog.json`。
- OpenWolf:更新 `.wolf/memory.md` 一行、`.wolf/anatomy.md` 新文件条目(`isLawKnowledgeBase.ts`)。

---

## Self-Review 记录

- **Spec coverage:** §2.1 helper→Task 1;§2.2 按钮→Task 2 Step 3;§2.3 横幅→Task 2 Step 4;§4 单测→Task 1、静态检查→Task 2 Step 5、人工验证→Task 3;§3 Non-goals 无对应任务(正确,均为"不做")。✓
- **Placeholder scan:** 无 TBD/TODO;所有代码步骤均含完整代码。✓
- **Type consistency:** helper 名 `isLawKnowledgeBase` 在 Task 1 定义、Task 2 导入使用一致;flag 名 `isLawKb` 仅 Task 2 内部。✓
