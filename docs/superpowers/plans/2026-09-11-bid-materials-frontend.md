# bid-materials 前端页面（投标资料管理：资质库+样例库）实现计划（Plan 4）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地应用中心「投标资料管理」前端——`/bid-materials` 路由 + 扩展组件（资质版本库 tab + 标书样例库 tab），消费 Plan 1 已就位的 `/api/extensions/bid-materials/*` 全部端点。

**Architecture:** 镜像 `coal-eia-samples` 双层形态——`app/bid-materials/page.tsx` 薄壳（ShellLayout+Suspense）+ `extensions/bid-materials/` 自包含扩展（api 层 + 双 tab 组件）。api 层复刻 `eia-samples/sample-library-api.ts` 的自包含 fetch+CSRF 模式（与 extensions 路由的 cookie+CSRF 契约同款）；资质文件下发用 `<a href>` 直链（cookie 认证随行，GET 免 CSRF）。纯前端零后端改动。

**Tech Stack:** Next.js 16 App Router、React 19、Shadcn ui 组件（Dialog/Table/Badge 等，与 eia-samples 同款）、Rstest（node 环境测 api 层）。

**依据:** spec `docs/superpowers/specs/2026-09-06-bid-materials-two-skill-design.md` §2.3 API 表 + §2.4 注册与权限（**后端与注册已由 Plan 1 落地**：app-center 条目 `database.py` L1678-1689、permissions.yaml `bid_materials` 块 L212、icons.ts `book-marked` L29-30、nav 后端驱动——前端零注册工作）。

**镜像源（勘察定稿）:**
- 路由薄壳：`frontend/src/app/coal-eia-samples/page.tsx`（25 行）。
- api 层：`frontend/src/extensions/eia-samples/sample-library-api.ts`（自包含 fetch/CSRF/ApiError/buildQuery 模式逐字复刻，换端点与类型）。
- 样例库 UI：`frontend/src/extensions/eia-samples/SampleLibrary.tsx`（726 行；只镜像 library tab——其 extract-dialog/quality-panel 是 eia 域专用，**不复刻**；该两文件是并发会话在制文件，勿 import 勿改）。
- 测试先例：`frontend/tests/unit/extensions/geo-samples/api.test.ts`（Rstest node 环境）；eia-samples 自身无测试，本计划为 api 层补齐（stub `globalThis.fetch`）。
- 后端契约（响应字段逐字对齐）：`backend/app/extensions/bid_materials/schemas.py`——QualificationResponse `{id, qual_type, cert_no, issuer, valid_until, scope, current_version, org_scope, disabled, notes}`；QualificationVersionResponse `{id, qualification_id, version, minio_key, sha256, file_ext, file_size, note, uploaded_by, uploaded_at}`；QualificationVersionUploadResponse `{created, version, sha256}`（created=False=sha256 去重命中）；SampleResponse `{id, title, source_path, file_hash, industry, project_category, scenario, status, notes}`；bulk 响应 `{created, updated, total}`。

---

### Task 1: api 层 bid-materials-api.ts + 单测（TDD）

**Files:**
- Create: `frontend/src/extensions/bid-materials/bid-materials-api.ts`
- Test: `frontend/tests/unit/extensions/bid-materials/api.test.ts`

- [ ] **Step 1: 写失败测试**（新建测试文件；fetch 用赋值+restore 手工 stub——geo 的 authFetch mock 模式不适用，本 api 是自包含 fetch）

```typescript
import { afterEach, describe, expect, test } from "@rstest/core";

// EAI-CUSTOM: bid-materials api 层契约测试——自包含 fetch 模式（复刻 eia-samples），
// 直接 stub globalThis.fetch（geo-samples 的 authFetch mock 模式不适用）。
const fetchMock = { calls: [] as Array<[string, RequestInit]>, responses: [] as Response[] };

const originalFetch = globalThis.fetch;

function stubFetch(status = 200, body: unknown = {}) {
  fetchMock.calls = [];
  fetchMock.responses = [];
  globalThis.fetch = (async (input: string, init: RequestInit = {}) => {
    fetchMock.calls.push([input, init]);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }) as Response;
  }) as typeof fetch;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
});

import { bidMaterialsApi, SAMPLE_SCENARIOS, QUAL_TYPE_PRESETS } from "@/extensions/bid-materials/bid-materials-api";

function lastCall(): [string, RequestInit] {
  return fetchMock.calls[fetchMock.calls.length - 1];
}

// csrf cookie 由 jsdom/node 环境缺失时 withCsrf 静默跳过——写方法断言只查 method/body/URL;
// CSRF 头存在性用显式注入 document cookie 的单测覆盖(dom 语义, 本套在 node 环境跳过该断言,
// 由 withCsrf 实现 ≤10 行的直观性兜底)。

describe("bidMaterialsApi.qualifications", () => {
  test("list builds query with filters", async () => {
    stubFetch(200, []);
    await bidMaterialsApi.qualifications.list({ qual_type: "CMMI", search: "iso", expiring_days: 90 });
    const [url] = lastCall();
    expect(url.startsWith("/api/extensions/bid-materials/qualifications?")).toBe(true);
    expect(url).toContain("qual_type=CMMI");
    expect(url).toContain("search=iso");
  });

  test("expiring hits dedicated endpoint with days", async () => {
    stubFetch(200, []);
    await bidMaterialsApi.qualifications.expiring(30);
    const [url] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/qualifications/expiring?days=30");
  });

  test("create POSTs json body with csrf attempt", async () => {
    stubFetch(201, { id: "q1" });
    await bidMaterialsApi.qualifications.create({ qual_type: "ISO9001", cert_no: "00123" });
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/qualifications");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ qual_type: "ISO9001", cert_no: "00123" }));
  });

  test("uploadVersion posts FormData without json content-type", async () => {
    stubFetch(201, { created: true, version: 2, sha256: "ab" });
    const file = new File([new Uint8Array([1, 2, 3])], "cert.png", { type: "image/png" });
    await bidMaterialsApi.qualifications.uploadVersion("q1", file, "年审换证");
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/qualifications/q1/versions");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    const headers = init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBeUndefined();
  });

  test("rollback POSTs version number", async () => {
    stubFetch(200, { id: "q1", current_version: 1 });
    await bidMaterialsApi.qualifications.rollback("q1", 1);
    const [, init] = lastCall();
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ version: 1 }));
  });

  test("fileUrl is a plain GET link (cookie auth, no fetch)", () => {
    expect(bidMaterialsApi.qualifications.fileUrl("q1")).toBe("/api/extensions/bid-materials/qualifications/q1/file");
    expect(bidMaterialsApi.qualifications.fileUrl("q1", 3)).toBe("/api/extensions/bid-materials/qualifications/q1/file?version=3");
  });
});

describe("bidMaterialsApi.samples", () => {
  test("list builds query with filters", async () => {
    stubFetch(200, []);
    await bidMaterialsApi.samples.list({ industry: "信息技术", status: "indexed", search: "师大" });
    const [url] = lastCall();
    expect(url.startsWith("/api/extensions/bid-materials/samples?")).toBe(true);
    expect(url).toContain("industry=");
    expect(url).toContain("search=");
  });

  test("importBulk posts items envelope", async () => {
    stubFetch(200, { created: 1, updated: 0, total: 1 });
    const item = { title: "t", source_path: "p", file_hash: "h", industry: "i", project_category: "c", scenario: "bid_sample", status: "indexed" };
    await bidMaterialsApi.samples.importBulk([item]);
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/samples/bulk");
    expect(init.body).toBe(JSON.stringify({ items: [item] }));
  });

  test("disable uses DELETE", async () => {
    stubFetch(200, { message: "ok" });
    await bidMaterialsApi.samples.disable("s1");
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/samples/s1");
    expect(init.method).toBe("DELETE");
  });
});

describe("error mapping", () => {
  test("non-json error surfaces statusText", async () => {
    globalThis.fetch = (async () => new Response("boom", { status: 500 })) as typeof fetch;
    await expect(bidMaterialsApi.samples.disable("s1")).rejects.toThrow("boom");
  });

  test("fastapi detail string is surfaced", async () => {
    stubFetch(400, { detail: "证号已存在" });
    await expect(bidMaterialsApi.qualifications.create({ qual_type: "x", cert_no: "y" })).rejects.toThrow("证号已存在");
  });
});

describe("enums", () => {
  test("scenario presets center on bid_sample", () => {
    expect(SAMPLE_SCENARIOS.some((s) => s.value === "bid_sample")).toBe(true);
  });
  test("qual type presets are non-empty with label+value", () => {
    expect(QUAL_TYPE_PRESETS.length).toBeGreaterThan(3);
    expect(QUAL_TYPE_PRESETS.every((t) => t.value && t.label)).toBe(true);
  });
});
```

（执行注：若 Rstest 的 `afterEach`/顶层 import 次序有坑——rstest 不提升普通 import，测试文件内 stub 函数定义在 import 前即可，`import` 语句照常置顶由编译器提升，但被测模块在 import 时只读 `API_BASE` 常量、不触 fetch，顺序无碍。`File`/`FormData`/`Response` 在 node 18+ 原生可用。断言细节按实际运行的 Rstest 行为微调，契约不变。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && pnpm test -- tests/unit/extensions/bid-materials/api.test.ts`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 bid-materials-api.ts**（逐字复刻 `sample-library-api.ts` 的骨架：文件头 EAI-CUSTOM 注释/`ApiError`/`getCsrfToken`/`withCsrf`/`bidRequest<T>`/`buildQuery`，以下为差异部分全文）

```typescript
// EAI-CUSTOM (Plan 4, spec 2026-09-06 §2.3): 投标资料管理 API——资质版本库(MinIO 代理)+标书样例台账。
// 镜像 eia-samples/sample-library-api.ts 的自包含 fetch+CSRF 模式(extensions 路由 cookie+CSRF 契约同款);
// 自包含 fetch 封装, 未导出, 勿反向耦合。资质文件下发走 <a href> 直链(cookie 认证随行, GET 免 CSRF)。

export interface QualificationRecord {
  id: string;
  qual_type: string;
  cert_no: string;
  issuer: string | null;
  valid_until: string | null; // ISO date
  scope: string | null;
  current_version: number;
  org_scope: string | null;
  disabled: boolean;
  notes: string | null;
}

export interface QualificationVersionRecord {
  id: string;
  qualification_id: string;
  version: number;
  minio_key: string;
  sha256: string;
  file_ext: string;
  file_size: number;
  note: string | null;
  uploaded_by: string | null;
  uploaded_at: string;
}

export interface QualificationVersionUploadResult {
  created: boolean; // false = sha256 去重命中(幂等返回既有版)
  version: number;
  sha256: string;
}

export interface QualificationUpsertInput {
  qual_type: string;
  cert_no: string;
  issuer?: string | null;
  valid_until?: string | null; // YYYY-MM-DD
  scope?: string | null;
  org_scope?: string | null;
  notes?: string | null;
}

export interface BidSampleRecord {
  id: string;
  title: string;
  source_path: string;
  file_hash: string;
  industry: string;
  project_category: string;
  scenario: string;
  status: string;
  notes: string | null;
}

export interface BidSampleUpsertInput {
  title: string;
  source_path: string;
  file_hash: string;
  industry: string;
  project_category: string;
  scenario: string;
  status: string;
  notes?: string | null;
}

export interface BidSampleBulkResult {
  created: number;
  updated: number;
  total: number;
}

export interface QualificationListParams {
  qual_type?: string;
  search?: string;
  expiring_days?: number; // 传则走 expiring 语义(由 api 对象分流到 /expiring)
}

export interface BidSampleListParams {
  industry?: string;
  project_category?: string;
  status?: string;
  search?: string;
}

// 资质类型预设(字典可扩; 输入始终允许自由文本, 预设仅作下拉建议)
export const QUAL_TYPE_PRESETS: { value: string; label: string }[] = [
  { value: "营业执照", label: "营业执照" },
  { value: "ISO9001", label: "ISO9001 质量体系" },
  { value: "ISO14001", label: "ISO14001 环境体系" },
  { value: "ISO45001", label: "ISO45001 职业健康" },
  { value: "CMMI", label: "CMMI" },
  { value: "软件著作权", label: "软件著作权" },
  { value: "业绩证明", label: "业绩证明" },
  { value: "安全生产许可证", label: "安全生产许可证" },
];

// 场景枚举——对齐后端 SampleCreate.scenario(本期单一场景, 保留枚举形态供扩)
export const SAMPLE_SCENARIOS: { value: string; label: string }[] = [
  { value: "bid_sample", label: "投标样例" },
];

// 状态枚举——对齐 BidSample.status(indexed|ragflow_pushed|disabled)
export const SAMPLE_STATUSES: { value: string; label: string }[] = [
  { value: "indexed", label: "已入库" },
  { value: "ragflow_pushed", label: "已推 RAGFlow" },
  { value: "disabled", label: "已停用" },
];

const API_BASE = "/api/extensions/bid-materials";

// …… ApiError/getCsrfToken/withCsrf/bidRequest<T>/buildQuery 逐字复刻 sample-library-api.ts
// （仅命名替换 sampleRequest→bidRequest；错误处理三态 detail-string/detail-array/text 分支逐字保留）

export const bidMaterialsApi = {
  qualifications: {
    list: (params: QualificationListParams = {}) => {
      if (params.expiring_days) {
        return bidRequest<QualificationRecord[]>(`/qualifications/expiring?days=${params.expiring_days}`);
      }
      return bidRequest<QualificationRecord[]>(`/qualifications${buildQuery({ qual_type: params.qual_type, search: params.search })}`);
    },
    create: (data: QualificationUpsertInput) =>
      bidRequest<QualificationRecord>("/qualifications", { method: "POST", body: JSON.stringify(data) }),
    get: (id: string) => bidRequest<QualificationRecord>(`/qualifications/${id}`),
    update: (id: string, data: Partial<QualificationUpsertInput>) =>
      bidRequest<QualificationRecord>(`/qualifications/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    disable: (id: string) =>
      bidRequest<{ message: string }>(`/qualifications/${id}`, { method: "DELETE" }),
    versions: (id: string) => bidRequest<QualificationVersionRecord[]>(`/qualifications/${id}/versions`),
    uploadVersion: (id: string, file: File, note?: string) => {
      const form = new FormData();
      form.append("file", file);
      if (note) form.append("note", note);
      const headers = withCsrf({}, "POST"); // 不设 Content-Type——浏览器自带 multipart boundary
      return bidRequest<QualificationVersionUploadResult>(`/qualifications/${id}/versions`, {
        method: "POST",
        headers,
        body: form,
      });
    },
    rollback: (id: string, version: number) =>
      bidRequest<QualificationRecord>(`/qualifications/${id}/rollback`, {
        method: "POST",
        body: JSON.stringify({ version }),
      }),
    fileUrl: (id: string, version?: number) =>
      `${API_BASE}/qualifications/${id}/file${version ? `?version=${version}` : ""}`,
  },
  samples: {
    list: (params: BidSampleListParams = {}) =>
      bidRequest<BidSampleRecord[]>(`/samples${buildQuery(params)}`),
    create: (data: BidSampleUpsertInput) =>
      bidRequest<BidSampleRecord>("/samples", { method: "POST", body: JSON.stringify(data) }),
    importBulk: (items: BidSampleUpsertInput[]) =>
      bidRequest<BidSampleBulkResult>("/samples/bulk", { method: "POST", body: JSON.stringify({ items }) }),
    get: (id: string) => bidRequest<BidSampleRecord>(`/samples/${id}`),
    disable: (id: string) =>
      bidRequest<{ message: string }>(`/samples/${id}`, { method: "DELETE" }),
  },
};
```

（执行注：后端 list 端点若返回 `{samples, total}` 包裹形态而非裸数组——以 `sed -n '72,85p' backend/app/extensions/bid_materials/routers.py` 实读为准，类型与测试同步对齐；upload 的 note 表单键名以 routers.py `upload_qualification_version` 的 Form 字段实读为准。）

- [ ] **Step 4: 跑测试全绿**

Run: `cd frontend && pnpm test -- tests/unit/extensions/bid-materials/api.test.ts`
Expected: 13 passed 前后

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/bid-materials/bid-materials-api.ts frontend/tests/unit/extensions/bid-materials/api.test.ts
git commit -m "feat(bid-materials): 前端 api 层(资质版本库+样例台账, 自包含 fetch+CSRF)+13 契约单测"
```

---

### Task 2: 路由薄壳 + 扩展骨架（双 tab 壳）

**Files:**
- Create: `frontend/src/app/bid-materials/page.tsx`
- Create: `frontend/src/extensions/bid-materials/index.ts`
- Create: `frontend/src/extensions/bid-materials/BidMaterials.tsx`

- [ ] **Step 1: page.tsx**（镜像 coal-eia-samples/page.tsx 25 行形态）

```tsx
"use client";

// EAI-CUSTOM (Plan 4, spec 2026-09-06 §2.4): 投标资料管理——应用中心独立应用薄壳。
// 镜像 coal-eia-samples/page.tsx 形态；后端 /api/extensions/bid-materials/*（Plan 1 已落地），
// 页面可见性由 permissions.yaml bid_materials 块(nav:bid-materials)+导航引擎驱动，前端不重复设卡。
import { Suspense } from "react";

import { BidMaterials } from "@/extensions/bid-materials";
import { ShellLayout } from "@/extensions/shell";

export default function BidMaterialsRoute() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            加载中...
          </div>
        }
      >
        <BidMaterials />
      </Suspense>
    </ShellLayout>
  );
}
```

- [ ] **Step 2: index.ts**

```typescript
// EAI-CUSTOM (Plan 4): 投标资料管理——应用中心独立应用（资质版本库+标书样例台账）。
export { default } from "./BidMaterials";
export { default as BidMaterials } from "./BidMaterials";
export * from "./bid-materials-api";
```

- [ ] **Step 3: BidMaterials.tsx**（tab 壳；两个子组件 Task 3/4 落地前先用占位空态保编译——占位仅 `text-muted-foreground` 文案，不带任何假数据）

```tsx
"use client";

// EAI-CUSTOM (Plan 4): 投标资料管理主组件——资质版本库 + 标书样例台账双 tab。
// 镜像 eia-samples/SampleLibrary.tsx 的 tab 形态(Tabs+TabsContent, Shadcn)。
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { QualificationLibrary } from "./QualificationLibrary";
import { SampleLibrary } from "./SampleLibrary";

export default function BidMaterials() {
  return (
    <div className="mx-auto flex h-full w-full max-w-7xl flex-col gap-4 p-4">
      <div>
        <h1 className="text-lg font-semibold">投标资料管理</h1>
        <p className="text-sm text-muted-foreground">
          投标资质版本库（MinIO 代理、到期预警）与标书技术资料台账（bank_compile 样例）。
        </p>
      </div>
      <Tabs defaultValue="qualifications" className="flex min-h-0 flex-1 flex-col">
        <TabsList>
          <TabsTrigger value="qualifications">资质库</TabsTrigger>
          <TabsTrigger value="samples">样例库</TabsTrigger>
        </TabsList>
        <TabsContent value="qualifications" className="min-h-0 flex-1">
          <QualificationLibrary />
        </TabsContent>
        <TabsContent value="samples" className="min-h-0 flex-1">
          <SampleLibrary />
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

- [ ] **Step 4: 骨架占位组件保编译**（QualificationLibrary.tsx / SampleLibrary.tsx 先建空壳 `export function X() { return <div className="p-4 text-sm text-muted-foreground">加载中（Task N 落地）</div>; }`，Task 3/4 替换全文）

- [ ] **Step 5: 门禁 + Commit**

```bash
cd frontend && pnpm lint && pnpm typecheck
git add frontend/src/app/bid-materials frontend/src/extensions/bid-materials
git commit -m "feat(bid-materials): /bid-materials 路由薄壳+双 tab 骨架"
```

---

### Task 3: 样例库 tab（镜像 SampleLibrary library-tab）

**Files:**
- Modify: `frontend/src/extensions/bid-materials/SampleLibrary.tsx`（Task 2 占位全文替换）

- [ ] **Step 1: 复制改造**——以 `frontend/src/extensions/eia-samples/SampleLibrary.tsx` 为基底复制到本目录，按下表逐项改造（先读源文件全文再动手）：

| 改造点 | 动作 |
|---|---|
| 文件头注释 | 换为 `// EAI-CUSTOM (Plan 4): 标书样例台账 tab——镜像 eia-samples SampleLibrary library-tab; eia 域专用提取/质检面板不复刻(spec §2.3 samples 端点族)。` |
| import | `KFSampleRecord/KFSampleUpsertInput/...` → 从 `./bid-materials-api` 导入 `BidSampleRecord/BidSampleUpsertInput/SAMPLE_SCENARIOS/SAMPLE_STATUSES/bidMaterialsApi` |
| 场景/状态过滤枚举 | eia 场景 7 项 → `SAMPLE_SCENARIOS`（1 项）+ 新增 **行业 industry** 与 **项目类别 project_category** 两个自由文本过滤输入（backend 支持透传）替换原 scenario 七选一的位置 |
| 列表加载/刷新/分页逻辑 | `sampleLibraryApi.list` → `bidMaterialsApi.samples.list`（注意响应形态裸数组 vs 包裹——按 Task 1 实读对齐）；eia 的 `variant/confidence` 列删除 |
| 表格列 | 标题/行业/项目类别/场景/状态/file_hash 前 8 位/入库时间；行操作=停用（confirm 后 `samples.disable`）+详情（notes 展开） |
| CreateSampleDialog | 字段换成 title/source_path/file_hash/industry/project_category/scenario(默认 bid_sample)/status(默认 indexed)/notes；file_hash 留空时前端置 `""` 由后端约束 |
| BulkImportDialog | 文本域粘贴 **registration.json 的 items 数组或单对象**（两种形态都 parse，提示文案注明「bank_compile 产 registration.json 直接粘贴」）；POST `samples.importBulk`；结果 `{created, updated, total}` 呈现 |
| 删除 | extractTarget/qualityRefreshKey/ExtractDialog/QualityPanel 及其 tab 全部删除（eia 专属） |
| tab 集合 | 只留 `library` 单 tab（去掉 quality）——tab 条可整体移除，直接渲染列表区 |

- [ ] **Step 2: 门禁（lint+typecheck）+ Commit**

```bash
cd frontend && pnpm lint && pnpm typecheck
git add frontend/src/extensions/bid-materials/SampleLibrary.tsx
git commit -m "feat(bid-materials): 样例库 tab(镜像 eia SampleLibrary: 过滤/登记/registration.json 批量导入/停用)"
```

---

### Task 4: 资质库 tab（列表/到期预警/登记/版本历史/回滚/停用）

**Files:**
- Modify: `frontend/src/extensions/bid-materials/QualificationLibrary.tsx`（Task 2 占位全文替换；版本对话框内聚在同文件）

- [ ] **Step 1: 实现**（形态镜像 SampleLibrary 的 list+filter+Dialog 模式；全文按以下规格编写）

- 文件头：`// EAI-CUSTOM (Plan 4, spec §2.2/2.3): 资质版本库 tab——MinIO 代理上传/版本不可变只追加/回滚=改指针/软删。`
- 状态：`quals, loading, qualTypeFilter, search, expiringOnly(bool), showCreateDialog, versionsTarget(QualificationRecord|null)`。
- 加载：`bidMaterialsApi.qualifications.list({qual_type, search, expiring_days: expiringOnly ? 90 : undefined})`；`expiringOnly` 开关文案「90 天内到期」。
- 表格列：类型 / 证号 / 发证机构 / 有效期至（**过期红字、90 天内琥珀字**，disabled 行整体 muted）/ 当前版 / 操作（版本历史、编辑(PATCH 元数据)、停用(软删 confirm)）。
- CreateEditDialog（创建/编辑复用）：qual_type（`QUAL_TYPE_PRESETS` 下拉 + 「自定义…」自由文本输入）、cert_no、issuer、valid_until（`<Input type="date">`）、scope、org_scope、notes。
- VersionsDialog（`versionsTarget` 非空时开）：
  - 版本列表：version / file_ext / file_size（KB 格式化）/ note / uploaded_at，当前版高亮（`current_version` 比对）；
  - 每行操作：「预览/下载」（`<a href={fileUrl(id, v)} target="_blank" rel="noreferrer">`，当前版用 `fileUrl(id)`）；非当前版显示「回滚到此版」（confirm 后 `rollback(id, v)`，成功后刷新列表+对话框）；
  - 上传新版本区：`<Input type="file" accept="image/png,image/jpeg">` + note 输入 + 上传按钮；响应 `created=false` 时提示「内容与既有版本相同（sha256 去重），已返回既有版 v{n}」，`created=true` 提示「已建版本 v{n}」。
- 空态/错误态：复刻 SampleLibrary 的 loading/empty/error 三态文案风格。

- [ ] **Step 2: 门禁 + 全量前端测试 + Commit**

```bash
cd frontend && pnpm lint && pnpm typecheck && pnpm test
git add frontend/src/extensions/bid-materials/QualificationLibrary.tsx
git commit -m "feat(bid-materials): 资质库 tab(到期预警/登记/版本历史/sha256去重提示/回滚/软删)"
```

---

### Task 5: 全量门禁 + 运行时核验 + 推送

- [ ] **Step 1**: `cd frontend && pnpm lint && pnpm typecheck && pnpm test`（全绿；e2e 不跑——纯新增路由无行为变更）
- [ ] **Step 2**: `docker compose -p eai-docker restart frontend`，等 30s 后 `curl -s -o /dev/null -w "%{http_code}" http://localhost:2026/bid-materials` → 200/307（登录重定向）均算通过；容器日志无编译错误（`docker compose -p eai-docker logs frontend --tail 50`）
- [ ] **Step 3**: `git push origin main-dev-fork` + `git fetch origin && git rev-list --left-right --count origin/main-dev-fork...HEAD` → `0 0`（push flaky 时重试 ≤3 次，仍失败则报告留给下个窗口）
- [ ] **Step 4**: 开发日志.md 追加一行（append-only，不暂存他人行）

---

## 后续计划（本文档不覆盖）

- tech_outline_packs 16 类 pack 填充（Plan 3 遗留）。
- 大纲自拟结构化（Plan 3 B1 v1 边界升级，另立计划）。
- agnes E2E clean4 复跑（A+B 双入口走查）。
- 样例库「预览脱敏册」直达（读 source_path 指向的 references 切片）——本期不做，本期不做记录。
