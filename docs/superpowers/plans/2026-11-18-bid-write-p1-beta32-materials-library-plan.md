# 批卅二(素材库独立页+废弃/bid-materials 清除)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans,逐任务勾 `- [ ]`。

**Goal:** 六类素材实体库从②素材核对页迁出为写作环独立「素材库」页(owner 级资产定位);连根删除废弃 `/bid-materials` 应用(DB 表不动)。

**Architecture:** `nav.ts` 扩 `WritePage` + 新路由页;MaterialsView 底部实体库区块迁出为 `LibraryView` 组件(含类型过滤 query `?type=`);②页缺口行「去素材库补录」带实体类型跳转;bid-materials 前后端模块+注册+权限块删除,引用 grep 归零。

**Tech Stack:** Next.js App Router / React Query(现有 useMaterials hooks)/ rstest dom / pytest

---

### Task 1: 导航与路由(WritePage 扩展 + 权限声明)

**Files:** Modify `frontend/src/extensions/bid-write/nav.ts`(WritePage union+PATHS)、`frontend/src/app/bid-write/layout.tsx`(导航项)、`config/permissions.yaml`、`deploy/offline/config/permissions.yaml`、Create `frontend/src/app/bid-write/materials-library/page.tsx`

- [x] **Step 1:** nav.ts:`WritePage` union 加 `"materials_library"`;`WRITE_PAGE_PATHS` 加 `materials_library: "/bid-write/materials-library"`(registry 行之前)。
- [x] **Step 2:** layout.tsx 导航数组:⑥导出之后、断言注册表之前插入,无序号:

```tsx
    {
      href: WRITE_PAGE_PATHS.materials_library,
      label: "素材库",
      taskPage: "materials_library",
    },
```

(对象字段形状与相邻条目一致;icon/label 跟现有条目模式。)
- [x] **Step 3:** 两份 permissions.yaml:bid_write 模块 `pages:` 列表加 `- id: "materials_library"`(display_name 素材库,operations: []);同时删除 `bid_materials:` 整块(253 行起,含 display_name/nav_id/pages)与角色 pages 里对 `bid:page:qualifications`/`bid:page:samples`/`nav:bid-materials` 的引用(执行时 grep 两份文件+roles_custom.yaml)。
- [x] **Step 4:** 新路由页 `frontend/src/app/bid-write/materials-library/page.tsx`(镜像相邻薄壳页形态,读 searchParams type 传 LibraryView):

```tsx
"use client";

import { Suspense } from "react";

import { LibraryView } from "@/extensions/bid-write/components/LibraryView";

export default function MaterialsLibraryRoute() {
  return (
    <Suspense fallback={<div className="bw-muted bw-p">加载中…</div>}>
      <LibraryView />
    </Suspense>
  );
}
```

- [x] **Step 5:** typecheck + eslint 四文件;Commit `feat(bid-write): 批卅二 T1 素材库导航+路由+权限声明(materials_library taskPage 两份 permissions;WritePage 扩展)`。

### Task 2: LibraryView 迁出

**Files:** Create `frontend/src/extensions/bid-write/components/LibraryView.tsx`;Modify `components/MaterialsView.tsx`

- [x] **Step 1:** 读 MaterialsView.tsx 当前树,钉出实体库区块精确行范围(「素材实体库」card-h 起,含过滤 tab/CRUD 对话框/列表;约 470 行起)与所用 hooks(useMaterials/useCreateMaterial 等已在该文件 import)。
- [x] **Step 2:** 整块剪切为 `LibraryView.tsx`(组件签名):

```tsx
"use client";

/** 批卅二:六类素材实体库独立页(owner 级资产;绑定判定仍归断言执行/导出门禁,本页不人工标记)。 */
export function LibraryView() {
  const search = useSearchParams();
  const initialType = search.get("type") ?? "all";
  // 原 MaterialsView 实体库区块 JSX+state 整体迁入,entityFilter 初始值=initialType
  ...
}
```

imports 从 MaterialsView 原样搬(api/primitives/materialEntityLabel/图标);MaterialsView 里被 LibraryView 独占的 import 若无他用则移除(eslint 会指)。
- [x] **Step 3:** MaterialsView 删区块+相关 state(entityFilter/CRUD 对话框 state)+独占 imports;页 subtitle 改「动笔前暴露缺件 · 三态缺口清单」;指标条删「素材实体 N 条」格。
- [x] **Step 4:** typecheck+eslint 两文件+rstest 既有 materials 相关测试(bid-write-materials-drawer.dom.test 若涉实体库区块则同步改);Commit `feat(bid-write): 批卅二 T2 LibraryView 迁出(六类实体库独立组件;MaterialsView 瘦身为缺口核对)`。

### Task 3: 缺口行跳转带上下文

**Files:** Modify `components/MaterialsView.tsx`(缺口行);LibraryView 已吃 `?type=`

- [x] **Step 1:** 缺口 items 形态核对(gaps builder,crud/routers):确认每条含实体类型(无则从 requirement 关键词映射到六类,映射表放 helpers);跳转:

```tsx
import { WRITE_PAGE_PATHS } from "@/extensions/bid-write/nav";
// 缺口行按钮:
onClick={() =>
  router.push(`${WRITE_PAGE_PATHS.materials_library}?type=${encodeURIComponent(gapEntityType)}${taskId ? `&task_id=${encodeURIComponent(taskId)}` : ""}`)
}
```

按钮文案「去素材库补录」。
- [x] **Step 2:** dom 测试(改造既有②页测试或新 `bid-write-materials-check.dom.test.tsx`):缺口行渲染跳转按钮且 href 带 type;实体库区块不再渲染(查询 `.card-h` 无「素材实体库」)。
- [x] **Step 3:** rstest 绿;Commit `feat(bid-write): 批卅二 T3 缺口行带类型跳转素材库+②页瘦身断言`。

### Task 4: 删除废弃 /bid-materials(连根,DB 表不动)

**Files:** Delete `frontend/src/app/bid-materials/page.tsx`、`frontend/src/extensions/bid-materials/`(index/bid-materials-api/OutlineCandidates/QualificationLibrary/SampleLibrary 5 文件)、`backend/app/extensions/bid_materials/`(routers/schemas/storage/service/__init__);Modify `backend/app/gateway/app.py`(注册行)、`backend/app/extensions/database.py`(模型 import/create_all 引用)

- [x] **Step 1:** 引用清单 grep:`grep -rn "bid_materials\|bid-materials" backend/app frontend/src config deploy frontend/tests backend/tests --include="*.py" --include="*.ts" --include="*.tsx" --include="*.yaml"` 逐处处置(注册行删/import 删/测试删)。
- [x] **Step 2:** 删文件(模块目录整删,`__pycache__` 随之;git rm)。
- [x] **Step 3:** 引用 grep 归零(bug-4402 DNR);backend pytest 全量 bid 相关(`-k "bid" -q`)+ 前端 grep e2e 引用清理。
- [x] **Step 4:** Commit `feat(bid-write): 批卅二 T4 删除废弃/bid-materials 应用(前后端模块+注册+权限块;DB 表不动)`。

### Task 5: 全量验证 + 实机

- [x] 后端 `-k bid_write` pytest 全绿;前端 bid-write rstest 全绿 + typecheck/eslint。
- [x] 实机(:3000 dev;gateway 本批后端零改动不需重启):UI 看①导航「素材库」在②缺口页跳转带过滤、③旧 /bid-materials 路由 404、④截图。
- [x] 全量 rstest 兜底(task-form-dialog flake 单跑基线核对)。

### Task 6: 收口

- [x] plan 全勾(add -f)+ wolf 四件套 + auto-memory + docs commit;**不推,等「push」**。

---

## Self-Review
1. 覆盖:①②③④ spec 四节 ↔ T1-T4 一一对应;边界(不做绑定展示/API 零改动)在 T2/T3 未越。
2. 占位:Step 2(区块行范围)与 Step 3(缺口 items 形态)标注「执行时钉精确值」——迁移类任务无法预写目标代码,指令为精确行范围钉定+签名代码,非 TBD。
3. 类型:WritePage 扩展 materials_library 与 layout taskPage、PATHS 三处一致;LibraryView 签名无 props(useSearchParams 自取)。


---

## T5 实测结果(2026-11-18)

- **实机 9/9**:素材库独立页(标题/7 过滤 tab/添加按钮)、②页(缺口在/实体库 0/承诺策略保留)、侧栏「素材库」入口、旧 /bid-materials → **404**(截图 bidwrite-m32.png)
- **后端** bid_write pytest 42/42;引用 grep 归零(含 app 中心 seed/database.py 注释/测试目录)
- **全量 rstest** 4704 过;唯一失败文件 task-form-dialog(超时形态、断言推进、零改动、内存压力负载超时=已知 flake 家族,非本批回归)
- **追加踩坑**:rstest 构建缓存 dist/.rstest-temp 持握已删模块旧产物(清缓存无用——真因=残留未跟踪测试目录被某次 checkout 复活,rm 后保持);frontend tests/unit/extensions/bid-materials/ 漏扫二犯,已删净
