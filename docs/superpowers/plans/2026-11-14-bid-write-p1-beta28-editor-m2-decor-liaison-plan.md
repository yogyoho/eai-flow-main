# bid_write P1 批廿八 —— 编辑器 M2 装饰联动 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地方案 §十三 M2——后端正文 AST 存储(GET/PUT)+ 编辑器装饰联动三件(provenance 角标 / liveAssert 侧信道纯 decoration 回写 / 本地确定性演示执行器)+ 工作台保存/加载接线。

**Architecture:** 三层契约(方案 §三/§六):唯一真值=AST;断言结果走 assertion_states 侧信道,编辑器只映射成 decoration(`meta: assert:apply` 纯装饰事务,**绝不写回节点文本**);后端新增 1:1 表 `bid_write_task_documents`(create_all 承接零迁移,不动共享 database.py)。本地演示执行器只做结构一致面(行 qty×unit=amount / 加总=合计 / 投标函金额=合计 / 缺件占位),不重复实现后端业务断言;真执行器(依赖图增量)挂后续批。

**Tech Stack:** FastAPI + SQLAlchemy(JSON 列,异步);ProseMirror Decoration(widget/inline/node)+ PluginKey 侧信道;React 19 前端 rstest node 环境单测;Playwright 实机脚本(宿主 :3000 拓扑)。

**边界(诚实面):**
- 负偏离展开(§5.4 appendTransaction 展开+approval_required)需 schema 扩展 → **批廿九**,本批不做。
- 增量重审「依赖图→受影响断言子集」需真执行器接线 → 本批演示执行器为全量重建 O(n)(400 行预算内,`ponytail:` 上限已注),接口 `assertRunner(ast)=>AssertPayload|null` 已留好替换位。
- 编辑锁 TTL/version 乐观锁(§七)挂后续批;M2 单写者(保存=PUT 幂等全量)。
- provenance.broken 判定 M2 = entity_id 为空;登记实体反查(素材库)挂后续批。

---

### Task 1: 后端正文 AST 存储(models+crud+schemas+routers+pytest)

**Files:**
- Modify: `backend/app/extensions/bid_write/models.py`(追加 TaskDocument)
- Modify: `backend/app/extensions/bid_write/crud.py`(追加 get_document/put_document)
- Modify: `backend/app/extensions/bid_write/schemas.py`(追加 DocumentIn)
- Modify: `backend/app/extensions/bid_write/routers.py`(追加 GET/PUT `/tasks/{task_id}/document`)
- Test: `backend/tests/test_bid_write_document.py`(新)

- [x] **Step 1: 写失败测试**(独立夹具:两表定点建,不碰既有 test_bid_write_routers 夹具)

```python
"""批廿八 M2 T1:正文 AST 存储(bid_write_task_documents 新表 create_all 零迁移)。
GET 未保存=ast:null(不造空文档冒充生成产物);PUT 幂等全量;ast 根/schema_version
校验 422;owner 过滤 404(routers 先 get_task 卡 owner,put 不会越权插行)。"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_write import crud, models
from app.extensions.bid_write import routers as R
from app.extensions.database import Base, get_db

DOC = {"type": "doc", "content": [{"type": "para", "attrs": {"slot_id": "s1"}}]}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=[models.WriteTask.__table__, models.TaskDocument.__table__])
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _seed(db):
    return (await crud.create_task(db, "u1")).id


@pytest.mark.asyncio
async def test_get_before_put_returns_null_ast(client, db):
    tid = await _seed(db)
    r = await client.get(f"/api/extensions/bid-write/tasks/{tid}/document")
    assert r.status_code == 200
    body = r.json()
    assert body["ast"] is None and body["updated_at"] is None and body["schema_version"] == ""


@pytest.mark.asyncio
async def test_put_get_roundtrip_and_overwrite(client, db):
    tid = await _seed(db)
    r = await client.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": DOC, "schema_version": "0.1.0"})
    assert r.status_code == 200 and r.json()["updated_at"]
    r2 = await client.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": {**DOC, "content": []}, "schema_version": "0.2.0"})
    assert r2.status_code == 200
    body = (await client.get(f"/api/extensions/bid-write/tasks/{tid}/document")).json()
    assert body["ast"]["content"] == [] and body["schema_version"] == "0.2.0"


@pytest.mark.asyncio
async def test_put_validations(client, db):
    tid = await _seed(db)
    assert (await client.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": {"type": "para"}, "schema_version": "0.1.0"})).status_code == 422
    assert (await client.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": DOC, "schema_version": "abc"})).status_code == 422


@pytest.mark.asyncio
async def test_owner_isolation(client, db):
    tid = await _seed(db)
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u2"
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c2:
        assert (await c2.get(f"/api/extensions/bid-write/tasks/{tid}/document")).status_code == 404
        assert (await c2.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": DOC, "schema_version": "0.1.0"})).status_code == 404
```

- [x] **Step 2: 跑红** `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_write_document.py -v` → AttributeError: TaskDocument 不存在
- [x] **Step 3: models.py 追加**

```python
class TaskDocument(Base):
    """正文 AST 存储(批廿八 M2;方案 §三 唯一真值=AST)。任务 1:1,create_all
    承接零迁移(独立新表);owner_id 冗余列=owner 过滤同矩阵行口径。"""

    __tablename__ = "bid_write_task_documents"

    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("bid_write_tasks.id"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    ast: Mapped[dict] = mapped_column(JSON, default=dict)
    schema_version: Mapped[str] = mapped_column(String(20), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
```

- [x] **Step 4: crud.py 追加**(import select 若缺)

```python
async def get_document(session: AsyncSession, task_id: str, owner_id: str) -> TaskDocument | None:
    res = await session.execute(select(TaskDocument).where(TaskDocument.task_id == task_id, TaskDocument.owner_id == owner_id))
    return res.scalar_one_or_none()


async def put_document(session: AsyncSession, task_id: str, owner_id: str, *, ast: dict, schema_version: str) -> TaskDocument:
    doc = await get_document(session, task_id, owner_id)
    if doc is None:
        doc = TaskDocument(task_id=task_id, owner_id=owner_id, ast=ast, schema_version=schema_version)
        session.add(doc)
    else:
        doc.ast = ast
        doc.schema_version = schema_version
    await session.commit()
    await session.refresh(doc)
    return doc
```

- [x] **Step 5: schemas.py 追加**

```python
class DocumentIn(BaseModel):
    """正文 AST 保存(M2;PUT 幂等全量)。ast 根 type 必须=="doc"( routers 校验)。"""

    ast: dict
    schema_version: str = ""
```

- [x] **Step 6: routers.py 追加**(import re 若缺;放在 get_gaps 之后)

```python
_AST_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


@router.get("/tasks/{task_id}/document")
async def get_task_document(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """正文 AST 读取(M2 装饰联动数据面;方案 §三 唯一真值=AST)。未保存过=
    ast:null——前端回退演示文档(诚实面:不造空文档冒充生成产物)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    doc = await crud.get_document(db, task_id=task_id, owner_id=owner_id)
    if doc is None:
        return {"ast": None, "schema_version": "", "updated_at": None}
    return {"ast": doc.ast, "schema_version": doc.schema_version, "updated_at": doc.updated_at.isoformat() if doc.updated_at else None}


@router.put("/tasks/{task_id}/document")
async def put_task_document(task_id: str, body: schemas.DocumentIn, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """正文 AST 保存(M2 工作台保存接线)。校验:ast 根 type=="doc" + semver
    schema_version(422)——防把任意 JSON 当文档落库。编辑锁/version 乐观锁挂后续批。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not isinstance(body.ast, dict) or body.ast.get("type") != "doc":
        raise HTTPException(status_code=422, detail='ast 根节点 type 必须为 "doc"')
    if not _AST_VERSION_RE.match(body.schema_version or ""):
        raise HTTPException(status_code=422, detail=f"schema_version 需为 semver(收到:{body.schema_version!r})")
    doc = await crud.put_document(db, task_id=task_id, owner_id=owner_id, ast=body.ast, schema_version=body.schema_version)
    return {"ast": doc.ast, "schema_version": doc.schema_version, "updated_at": doc.updated_at.isoformat() if doc.updated_at else None}
```

- [x] **Step 7: 跑绿** 同 Step 2 → 4 PASS;`uv run pytest tests/test_bid_write_document.py tests/test_bid_write_routers.py -v` 回归旧端点不破
- [x] **Step 8: 提交**

```bash
git add backend/app/extensions/bid_write/models.py backend/app/extensions/bid_write/crud.py backend/app/extensions/bid_write/schemas.py backend/app/extensions/bid_write/routers.py backend/tests/test_bid_write_document.py
git commit -m "feat(bid-write): 批廿八 M2-a 正文 AST 存储——bid_write_task_documents 1:1 表(create_all 零迁移)+GET/PUT /tasks/{id}/document(ast 根/semver 校验 422;未保存 ast:null 诚实面)+4 例单测"
```

---

### Task 2: 编辑器装饰层(decor.ts:provenancePlugin + liveAssertPlugin + editorLocalAssert)+ state/BidWriteEditor 挂接

**Files:**
- Create: `frontend/src/extensions/bid-write/editor/decor.ts`
- Modify: `frontend/src/extensions/bid-write/editor/state.ts`(挂两插件)
- Modify: `frontend/src/extensions/bid-write/editor/BidWriteEditor.tsx`(assertRunner/onAssert/onProvenanceJump)
- Test: `frontend/tests/unit/extensions/bid-write-editor-assert.test.ts`(新,纯 AST)
- Test: `frontend/tests/unit/extensions/bid-write-editor-decor.test.ts`(新,node env PM)

- [x] **Step 1: 写失败测试(assert)**

```ts
// 批廿八 M2 T2:editorLocalAssert 本地确定性演示执行器(纯 AST,不碰 PM/DOM)。
// demo 文档自带面:行 4×200,000=800,000 ✓;合计 1,260,000=和 ✓;投标函金额
// 1,280,000 ≠ 合计(故意 SK-PS-003 面,且带 status_mark D1);todo P-101 level D0。
import { describe, expect, test } from "rstest";

import { editorLocalAssert, summarize } from "@/extensions/bid-write/editor/decor";
import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { serializeDoc, hydrateAst } from "@/extensions/bid-write/editor/doc";
import { schema } from "@/extensions/bid-write/editor/schema.gen";

const demo = () => demoWorkbenchAst() as Parameters<typeof editorLocalAssert>[0];

describe("editorLocalAssert", () => {
  test("demo 基线:无行级 D0;bl-opening 有 D1 SK-PS-003;todo D0;skipped 面", () => {
    const payload = editorLocalAssert(demo());
    expect(payload.states["price:R-1"]).toBeUndefined();
    expect(payload.states["price:R-2"]).toBeUndefined();
    expect(payload.states["bl-opening"]).toMatchObject({ state: "D1", err_code: "SK-PS-003" });
    expect(payload.states["todo:P-101"]).toMatchObject({ state: "D0" });
    expect(payload.skipped.some((s) => s.code === "SK-PS-006" && s.count > 0)).toBe(true);
    const sum = summarize(payload);
    expect(sum.d0).toBe(1);
    expect(sum.d1).toBe(1);
  });

  test("行金额被改 → 行 D0 SK-PS-008 + 合计失配 D0 SK-PS-003", () => {
    const ast = demo();
    const row = ast.content![0].content!.find((n) => n.type === "table")!.content![0];
    const amount = row.content![3];
    amount.content![0].text = "700,000.00";
    const payload = editorLocalAssert(ast);
    expect(payload.states["price:R-1"]).toMatchObject({ state: "D0", err_code: "SK-PS-008" });
    expect(payload.states["price:R-sum"]).toMatchObject({ state: "D0", err_code: "SK-PS-003" });
  });

  test("投标函金额改成合计值 → bl-opening 失配消失(status_mark 反射仍在)", () => {
    const ast = demo();
    const para = ast.content![0].content![0].content![0];
    for (const t of para.content!) if (t.text === "1,280,000.00") t.text = "1,260,000.00";
    const payload = editorLocalAssert(ast);
    // status_mark 反射(D1)仍在,但不再叠加计算失配——仍 D1(Serial 反射口径)
    expect(payload.states["bl-opening"]).toMatchObject({ state: "D1", err_code: "SK-PS-003" });
    expect(payload.states["price:R-sum"]).toBeUndefined();
  });

  test("severity 合并:D0 优先于 D1(同 key 双源)", () => {
    const ast = demo();
    const row = ast.content![0].content!.find((n) => n.type === "table")!.content![0];
    row.content![3].content![0].text = "700,000.00";
    const payload = editorLocalAssert(ast);
    // bl-opening:计算失配 D1(1,280,000≠1,260,000)+ status_mark D1 → 仍 D1;
    // 若把合计改坏到连投标函也失配则维持 D1;此处只锁合并函数不降级
    expect(payload.states["bl-opening"].state).toBe("D1");
  });

  test("往返纯函数:serializeDoc∘hydrateAst 后再断言结果一致(装饰前数据面稳定)", () => {
    const ast = serializeDoc(hydrateAst(demoWorkbenchAst())).toJSON();
    const a = editorLocalAssert(demo());
    const b = editorLocalAssert(ast as never);
    expect(Object.keys(b.states).sort()).toEqual(Object.keys(a.states).sort());
  });
});
```

- [x] **Step 2: 跑红** `python ../scripts/pnpm.py exec rstest tests/unit/extensions/bid-write-editor-assert.test.ts` → 模块不存在
- [x] **Step 3: 写 decor.ts(完整实现)**

```ts
// EAI-CUSTOM 批廿八 M2——装饰联动层(方案 §5.1/§六):
//  · provenancePlugin:provenance mark → widget 角标 [B-014][M-88];entity_id 空=未登记
//    broken 红 ⚠;点击标记文本 dispatch meta「provenance:jump」(decor 事务不进撤销栈)。
//  · liveAssertPlugin:assertion_states 侧信道(meta「assert:apply」)→ D0 红/D1 黄
//    inline/node decoration;绝不写回节点文本;D2/SKIPPED 不渲染(SKIPPED 只进状态栏,
//    不得当作通过——§六降级面)。
//  · editorLocalAssert:本地确定性演示执行器(行 qty×unit=amount SK-PS-008 / 加总=合计
//    SK-PS-003 / 投标函金额=合计 SK-PS-003 D1 / 缺件占位 / status_mark 反射)。
//    ponytail: 全量重建 O(n)——依赖图增量(受影响断言子集)挂真执行器批,接口已留。
import {
  type EditorState,
  Plugin,
  type Transaction,
} from "prosemirror-state";
import { Decoration, DecorationSet, type EditorView } from "prosemirror-view";
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- PMNode 仅类型位
import type { Node as PMNode } from "prosemirror-model";

import { type AstJsonNode } from "./schema.gen";
import { decorTr } from "./state";

export interface AssertState {
  state: "D0" | "D1" | "D2";
  err_code?: string;
  message?: string;
}

export interface AssertSkipped {
  code: string;
  count: number;
  reason?: string;
}

export interface AssertPayload {
  states: Record<string, AssertState>;
  skipped: AssertSkipped[];
  run_at: string;
}

export interface AssertSummary {
  d0: number;
  d1: number;
  d2: number;
  skipped: AssertSkipped[];
}

export interface ProvenanceHit {
  clause_id: string;
  entity_id: string;
  anchor: string;
}

export const ASSERT_APPLY_META = "assert:apply";
export const PROVENANCE_JUMP_META = "provenance:jump";

const SEVERITY: Record<AssertState["state"], number> = { D0: 3, D1: 2, D2: 1 };

function mergeState(map: Record<string, AssertState>, key: string, next: AssertState): void {
  const cur = map[key];
  if (!cur || SEVERITY[next.state] > SEVERITY[cur.state]) map[key] = next;
}

function anchorKey(node: PMNode, parent: PMNode | null): string | null {
  if (node.type.name === "para") {
    const slot = String(node.attrs.slot_id ?? "");
    return slot ? slot : null;
  }
  if (node.type.name === "locked_paragraph") {
    const tpl = String(node.attrs.template_id ?? "");
    return tpl ? tpl : null;
  }
  if (
    node.type.name === "table_row" &&
    parent?.type.name === "table" &&
    String(parent.attrs.table_type ?? "") === "price"
  ) {
    return `price:${String(node.attrs.row_id ?? "")}`;
  }
  if (node.type.name === "todo_block") {
    return `todo:${String(node.attrs.pending_item_id ?? "")}`;
  }
  return null;
}

export function buildAssertDecorations(doc: PMNode, states: Record<string, AssertState>): DecorationSet {
  const decos: Decoration[] = [];
  doc.descendants((node, pos, parent) => {
    if (node.type.name === "text") return;
    const key = anchorKey(node, parent);
    const st = key ? states[key] : undefined;
    if (!st || st.state === "D2") return;
    const cls = st.state === "D0" ? "bwx-assert-d0" : "bwx-assert-d1";
    const title = [st.err_code, st.message].filter(Boolean).join(" · ");
    const spec = { class: cls, "data-err": st.err_code ?? "", title };
    if (node.isLeaf || node.type.name === "table_row") {
      decos.push(Decoration.node(pos, pos + node.nodeSize, spec));
    } else if (node.content.size > 0) {
      decos.push(Decoration.inline(pos + 1, pos + 1 + node.content.size, spec));
    } else {
      decos.push(Decoration.node(pos, pos + node.nodeSize, spec));
    }
  });
  return DecorationSet.create(doc, decos);
}

export const liveAssertKey = new PluginKey<DecorationSet>("liveAssert");

export function liveAssertPlugin(): Plugin<DecorationSet> {
  return new Plugin<DecorationSet>({
    key: liveAssertKey,
    state: {
      init: (_config, state) => buildAssertDecorations(state.doc, {}),
      apply(tr, old) {
        const payload = tr.getMeta(ASSERT_APPLY_META) as AssertPayload | undefined;
        if (payload) return buildAssertDecorations(tr.doc, payload.states);
        if (!tr.docChanged) return old;
        return old.map(tr.mapping, tr.doc);
      },
    },
    props: {
      decorations(state: EditorState) {
        return liveAssertKey.getState(state) ?? DecorationSet.empty;
      },
    },
  });
}

/** 纯构造侧信道事务(可测);applyAssertionStates=构造+dispatch */
export function assertionTr(state: EditorState, payload: AssertPayload): Transaction {
  const tr = decorTr(state.tr);
  tr.setMeta(ASSERT_APPLY_META, payload);
  return tr;
}

export function applyAssertionStates(view: EditorView, payload: AssertPayload): void {
  view.dispatch(assertionTr(view.state, payload));
}

export function summarize(payload: AssertPayload | null): AssertSummary {
  if (!payload) return { d0: 0, d1: 0, d2: 0, skipped: [] };
  let d0 = 0;
  let d1 = 0;
  let d2 = 0;
  for (const st of Object.values(payload.states)) {
    if (st.state === "D0") d0 += 1;
    else if (st.state === "D1") d1 += 1;
    else d2 += 1;
  }
  return { d0, d1, d2, skipped: payload.skipped };
}

// ── provenance(方案 §5.1)──────────────────────────────────────────────

function buildProvenanceDecorations(doc: PMNode): DecorationSet {
  const decos: Decoration[] = [];
  doc.descendants((node, pos) => {
    if (node.type.name !== "text" || !node.marks.length) return;
    const mark = node.marks.find((m) => m.type.name === "provenance");
    if (!mark) return;
    const entityId = String(mark.attrs.entity_id ?? "");
    const clauseId = String(mark.attrs.clause_id ?? "");
    const broken = !entityId;
    decos.push(
      Decoration.widget(
        pos + node.nodeSize,
        () => {
          const sup = document.createElement("sup");
          sup.className = broken ? "bwe-prov-badge broken" : "bwe-prov-badge";
          sup.textContent = broken ? `⚠ [${clauseId}]` : `[${clauseId}][${entityId}]`;
          sup.contentEditable = "false";
          return sup;
        },
        { side: 1, marks: [] },
      ),
    );
  });
  return DecorationSet.create(doc, decos);
}

export function provenanceAt(state: EditorState, pos: number): ProvenanceHit | null {
  for (const p of [pos, pos - 1]) {
    const node = state.doc.nodeAt(p);
    const mark = node?.marks.find((m) => m.type.name === "provenance");
    if (mark) {
      return {
        clause_id: String(mark.attrs.clause_id ?? ""),
        entity_id: String(mark.attrs.entity_id ?? ""),
        anchor: String(mark.attrs.anchor ?? ""),
      };
    }
  }
  return null;
}

export const provenanceKey = new PluginKey<DecorationSet>("provenance");

export function provenancePlugin(options: { onJump?: (hit: ProvenanceHit) => void } = {}): Plugin<DecorationSet> {
  return new Plugin<DecorationSet>({
    key: provenanceKey,
    state: {
      init: (_c, state) => buildProvenanceDecorations(state.doc),
      apply(tr, old) {
        if (tr.docChanged) return buildProvenanceDecorations(tr.doc);
        return old;
      },
    },
    props: {
      decorations(state: EditorState) {
        return provenanceKey.getState(state) ?? DecorationSet.empty;
      },
      handleClick(view, pos) {
        const hit = provenanceAt(view.state, pos);
        if (!hit) return false;
        const tr = decorTr(view.state.tr);
        tr.setMeta(PROVENANCE_JUMP_META, hit);
        view.dispatch(tr);
        options.onJump?.(hit);
        return true;
      },
    },
  });
}

// ── 本地确定性演示执行器(纯 AST JSON)────────────────────────────────

type LooseNode = {
  type?: string;
  attrs?: Record<string, unknown>;
  content?: LooseNode[];
  text?: string;
  marks?: { type?: string; attrs?: Record<string, unknown> }[];
};

const AMOUNT_RE = /^\d{1,3}(?:,\d{3})*\.\d{2}$/;

function parseAmount(text: string): number | null {
  const t = text.trim();
  return AMOUNT_RE.test(t) ? Number(t.replace(/,/g, "")) : null;
}

function nodeText(node: LooseNode): string {
  if (typeof node.text === "string") return node.text;
  return (node.content ?? []).map(nodeText).join("");
}

function cellByRole(row: LooseNode, role: string): LooseNode | null {
  for (const cell of row.content ?? []) {
    const cellRole = String(cell.attrs?.col_role ?? cell.attrs?.role ?? "");
    if (cellRole === role) return cell;
  }
  return null;
}

function walkSections(ast: LooseNode, visit: (section: LooseNode, idx: number) => void): void {
  (ast.content ?? []).forEach((section, idx) => visit(section, idx));
}

export function editorLocalAssert(ast: AstJsonNode): AssertPayload {
  const root = ast as unknown as LooseNode;
  const states: Record<string, AssertState> = {};
  let total: number | null = null;
  let bidLetterAmount: { value: number; slot: string } | null = null;

  walkSections(root, (section) => {
    for (const block of section.content ?? []) {
      if (block.type === "table" && String(block.attrs?.table_type ?? "") === "price") {
        const rows = block.content ?? [];
        const detailAmounts: number[] = [];
        for (const row of rows) {
          const rowId = String(row.attrs?.row_id ?? "");
          const qty = parseAmount(nodeText(cellByRole(row, "qty") ?? {}));
          const unit = parseAmount(nodeText(cellByRole(row, "unit") ?? {}));
          const amountCell = cellByRole(row, "amount");
          const amount = amountCell ? parseAmount(nodeText(amountCell)) : null;
          if (qty !== null && unit !== null && amount !== null) {
            detailAmounts.push(amount);
            // ponytail: 0.005 浮点阈——内核口径为 Decimal 4 位落表 2 位,本地演示面够用
            if (Math.abs(qty * unit - amount) > 0.005) {
              states[`price:${rowId}`] = {
                state: "D0",
                err_code: "SK-PS-008",
                message: `行金额失配:${qty}×${unit}≠${amount}`,
              };
            }
          } else if (amountCell && amount === null) {
            states[`price:${rowId}`] = { state: "D0", err_code: "SK-PS-007", message: "金额格非法/空" };
          }
          if (String(cellByRole(row, "total_num")?.attrs?.role ?? "") === "total_num" || rowId.endsWith("sum")) {
            const t = cellByRole(row, "total_num") ? parseAmount(nodeText(cellByRole(row, "total_num")!)) : null;
            if (t !== null) total = t;
            if (total !== null && detailAmounts.length > 0) {
              const sum = detailAmounts.reduce((a, b) => a + b, 0);
              if (Math.abs(sum - total) > 0.005) {
                states[`price:${rowId}`] = {
                  state: "D0",
                  err_code: "SK-PS-003",
                  message: `合计失配:明细和 ${sum}≠合计 ${total}`,
                };
              }
            }
          }
        }
      }
      if (block.type === "todo_block") {
        const key = `todo:${String(block.attrs?.pending_item_id ?? "")}`;
        states[key] = {
          state: String(block.attrs?.level ?? "D1") === "D0" ? "D0" : "D1",
          err_code: "",
          message: `缺件:${String(block.attrs?.missing ?? "待补")}`,
        };
      }
      // 投标函金额(表外 amount 形文本):与合计比 → D1 SK-PS-003(只读引用口径 SK-BL-002)
      const para = (block.content ?? []).find((n) => n.type === "para");
      const slot = String(para?.attrs?.slot_id ?? "");
      if (para && slot && section === root.content?.[0]) {
        for (const t of para.content ?? []) {
          const v = parseAmount(String(t.text ?? ""));
          if (v !== null) bidLetterAmount = { value: v, slot };
        }
      }
    }
  });

  if (bidLetterAmount && total !== null && Math.abs(bidLetterAmount.value - total) > 0.005) {
    mergeState(states, bidLetterAmount.slot, {
      state: "D1",
      err_code: "SK-PS-003",
      message: `投标函金额(${bidLetterAmount.value})与报价合计(${total})不一致——金额只读引用,请回报价侧修正`,
    });
  }

  // status_mark 反射:文中既存 D 态并入 live map(生成器/真执行器的持久通道)
  walkSections(root, (section) => {
    for (const block of section.content ?? []) {
      const para = (block.content ?? []).find((n) => n.type === "para" || n.type === "locked_paragraph");
      const slot = String(para?.attrs?.slot_id ?? para?.attrs?.template_id ?? "");
      if (!para || !slot) continue;
      for (const t of para.content ?? []) {
        const mark = (t.marks ?? []).find((m) => m.type === "status_mark");
        if (!mark) continue;
        const st = String(mark.attrs?.state ?? "D1");
        if (st === "D0" || st === "D1") {
          mergeState(states, slot, {
            state: st,
            err_code: String(mark.attrs?.err_code ?? ""),
            message: "文中既存标记(生成器快照)",
          });
        }
      }
    }
  });

  return {
    states,
    skipped: [{ code: "SK-PS-006", count: 1, reason: "限价未确认(本地演示执行器不核限价)" }],
    run_at: new Date().toISOString(),
  };
}
```

注意:`PluginKey` 需 `import { PluginKey } from "prosemirror-state"`(并入顶部 import);`editorLocalAssert` 内 `bidLetterAmount` TS 窄化需 `let ... : {...} | null` + 比较 `bidLetterAmount.value` 前非空(实现时按 tsc 报错微调)。

- [x] **Step 4: 跑绿 assert 测试**(微调实现至全绿)
- [x] **Step 5: 写失败测试(decor,node env PM)**

```ts
// 批廿八 M2 T2:装饰层——assert:apply 侧信道映射 + 纯装饰不污染(方案 §六/§十二)。
import { describe, expect, test } from "rstest";

import {
  ASSERT_APPLY_META,
  applyAssertionStatesNotUsed, // 占位防误导入(实现删)
  assertionTr,
  buildAssertDecorations,
  buildProvenanceDecorations,
  liveAssertKey,
  provenanceKey,
  provenanceAt,
  PROVENANCE_JUMP_META,
} from "@/extensions/bid-write/editor/decor";
import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { hydrateAst, serializeDoc } from "@/extensions/bid-write/editor/doc";
import { createBidWriteEditorState } from "@/extensions/bid-write/editor/state";
import { EditorState } from "prosemirror-state";
import type { EditorView } from "prosemirror-view";

function demoState() {
  return createBidWriteEditorState(demoWorkbenchAst(), {});
}

function findSlotRange(state: EditorState, slotId: string): [number, number] | null {
  let hit: [number, number] | null = null;
  state.doc.descendants((node, pos) => {
    if (node.type.name === "para" && String(node.attrs.slot_id ?? "") === slotId) {
      hit = [pos + 1, pos + 1 + node.content.size];
    }
  });
  return hit;
}

describe("liveAssert side-channel", () => {
  test("assert:apply → bl-opening 挂 D1 inline decoration;doc 文本零污染", () => {
    const state = demoState();
    const beforeJson = state.doc.toJSON();
    const tr = assertionTr(state, {
      states: { "bl-opening": { state: "D1", err_code: "SK-PS-003" } },
      skipped: [],
      run_at: "2026-11-14T00:00:00Z",
    });
    expect(tr.getMeta(ASSERT_APPLY_META)).toBeTruthy();
    expect(tr.getMeta("source")).toBe("decor");
    expect(tr.getMeta("addToHistory")).toBe(false);
    const s2 = state.apply(tr);
    const decos = (liveAssertKey.getState(s2) ?? { find: () => [] }).find() as { from: number; to: number; type: { attrs: Record<string, unknown> } }[];
    const range = findSlotRange(state, "bl-opening")!;
    const hit = decos.find((d) => d.from === range[0] && d.to === range[1]);
    expect(hit).toBeTruthy();
    expect(String(hit!.type.attrs.class)).toContain("bwx-assert-d1");
    expect(s2.doc.toJSON()).toEqual(beforeJson); // 装饰绝不写回节点文本(§六)
    expect(serializeDoc(s2.doc).toJSON()).toEqual(serializeDoc(state.doc).toJSON());
  });

  test("undo 栈不受侧信道污染(canUndo 不翻转)", () => {
    const state = demoState();
    const s2 = state.apply(assertionTr(state, { states: {}, skipped: [], run_at: "x" }));
    expect(s2).toBe(state); // addToHistory:false + 无文档变化 → apply 拒? 不,decor tr 无 step…decor tr 含 meta 无 steps,apply 返回新 state 但 history 不增长
  });

  test("后续用户编辑 tr 将既有装饰 map 到新位置(不丢)", () => {
    const state = demoState();
    const s2 = state.apply(assertionTr(state, { states: { "bl-opening": { state: "D1" } }, skipped: [], run_at: "x" }));
    const decosBefore = (liveAssertKey.getState(s2) ?? { find: () => [] }).find().length;
    const range = findSlotRange(s2, "bl-opening")!;
    const s3 = s2.apply(s2.tr.insertText("Z", range[0]));
    const decosAfter = (liveAssertKey.getState(s3) ?? { find: () => [] }).find().length;
    expect(decosAfter).toBe(decosBefore);
  });
});

describe("provenance", () => {
  test("widget 角标挂在标记文本尾;provenanceAt 命中 [B-014][M-88];普通文本 null", () => {
    const state = demoState();
    const widgets = (provenanceKey.getState(state) ?? { find: () => [] }).find() as { type: string }[];
    expect(widgets.filter((d) => d.type === "widget").length).toBe(1);
    let markedPos = -1;
    state.doc.descendants((node, pos) => {
      if (node.type.name === "text" && node.marks.some((m) => m.type.name === "provenance") && markedPos < 0) markedPos = pos;
    });
    expect(provenanceAt(state, markedPos)).toEqual({ clause_id: "B-014", entity_id: "M-88", anchor: "P.34" });
    expect(provenanceAt(state, findSlotRange(state, "bl-opening")![0])).toBeNull(); // 非标记文本(粗位)
  });

  test("jump meta 通道:构造 decor tr 带 provenance:jump", () => {
    const state = demoState();
    const tr = state.tr;
    tr.setMeta(PROVENANCE_JUMP_META, { clause_id: "B-014", entity_id: "M-88", anchor: "P.34" });
    tr.setMeta("source", "decor");
    tr.setMeta("addToHistory", false);
    const s2 = state.apply(tr);
    expect(s2.doc.eq(state.doc)).toBe(true);
  });
});
```

(实现时按 tsc/rstest 报错微调:`applyAssertionStatesNotUsed` 占位不要真导出——删掉该 import 行;EditorView 类型 import 若未用也删。)

- [x] **Step 6: 跑绿** decor + assert 两个文件;constraints 旧 12 例回归
- [x] **Step 7: state.ts 挂插件**

```ts
import { liveAssertPlugin, provenancePlugin, type ProvenanceHit } from "./decor";
// options: { onViolation?: OnViolation; onProvenanceJump?: (hit: ProvenanceHit) => void } = {}
plugins: [
  history(),
  keymap({ "Mod-z": undo, "Mod-Z": redo, "Mod-y": redo }),
  keymap(baseKeymap),
  constraintsPlugin(options),
  provenancePlugin({ onJump: options.onProvenanceJump }),
  liveAssertPlugin(),
],
```

- [x] **Step 8: BidWriteEditor.tsx** props 追加 `assertRunner?: (ast: AstJsonNode) => AssertPayload | null` / `onAssert?: (summary: AssertSummary | null, error: boolean) => void` / `onProvenanceJump?: (hit: ProvenanceHit) => void`;latest-ref 三件;mount 后与防抖回传后各跑一次:

```ts
const runAssert = (view: EditorView) => {
  try {
    const payload = assertRunnerRef.current ? assertRunnerRef.current(serializeDoc(view.state.doc)) : null;
    if (payload) applyAssertionStates(view, payload);
    onAssertRef.current?.(payload ? summarize(payload) : null, false);
  } catch {
    onAssertRef.current?.(null, true); // 校验未完成——绝不默认放行(§六降级)
  }
};
```

(dispatchTransaction 防抖回调里 onDocChange 之后调用 `runAssert(view)`;effect 建视图后 `runAssert(view)` 初跑;createBidWriteEditorState 传 onProvenanceJump adapter。)

- [x] **Step 9: 提交**

```bash
git add frontend/src/extensions/bid-write/editor/decor.ts frontend/src/extensions/bid-write/editor/state.ts frontend/src/extensions/bid-write/editor/BidWriteEditor.tsx frontend/tests/unit/extensions/bid-write-editor-assert.test.ts frontend/tests/unit/extensions/bid-write-editor-decor.test.ts
git commit -m "feat(bid-write): 批廿八 M2-b 装饰联动层——provenance 角标 widget(jump meta+broken 面)+liveAssert 侧信道(assert:apply 纯装饰,doc 零污染,undo 栈干净)+editorLocalAssert 演示执行器(SK-PS-003/008/007 行面+合计面+投标函金额 D1+todo+status_mark 反射+SKIPPED 面)+13 例单测"
```

---

### Task 3: 工作台接线(api/types/WorkbenchView/CSS)

**Files:**
- Modify: `frontend/src/extensions/bid-write/types.ts`(TaskDocumentResponse)
- Modify: `frontend/src/extensions/bid-write/api.ts`(getTaskDocument/putTaskDocument)
- Modify: `frontend/src/extensions/bid-write/components/WorkbenchView.tsx`
- Modify: `frontend/src/app/bid-write/bid-write.css`(角标/断言装饰 token 化样式,`.bwx` 前缀)

- [x] **Step 1: types.ts**

```ts
export interface TaskDocumentResponse {
  ast: AstJsonNode | null;
  schema_version: string;
  updated_at: string | null;
}
```

(顶部 `import type { AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";`)

- [x] **Step 2: api.ts**(镜像 putPolicy 的 PUT 写法)

```ts
export async function getTaskDocument(taskId: string): Promise<TaskDocumentResponse> {
  return requestJson(`/tasks/${taskId}/document`);
}

export async function putTaskDocument(
  taskId: string,
  input: { ast: AstJsonNode; schema_version: string },
): Promise<TaskDocumentResponse> {
  return requestJson(`/tasks/${taskId}/document`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}
```

- [x] **Step 3: WorkbenchView**:

```ts
// 新 state
const [loadedAst, setLoadedAst] = useState<AstJsonNode | null>(null);
const [docEpoch, setDocEpoch] = useState(0);
const [docSource, setDocSource] = useState<"demo" | "cloud" | "cloud-error">("demo");
const [saving, setSaving] = useState(false);
const [assertSummary, setAssertSummary] = useState<AssertSummary | null>(null);
const [assertError, setAssertError] = useState(false);
const [provJump, setProvJump] = useState<string | null>(null);
const provTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

// 加载(taskId 变化重取;stale 忽略)
useEffect(() => {
  if (!taskId) return;
  let alive = true;
  getTaskDocument(taskId)
    .then((doc) => {
      if (!alive) return;
      if (doc.ast) {
        setLoadedAst(doc.ast);
        setDocSource("cloud");
        setDocEpoch((e) => e + 1); // key 重挂=服务端文档替换演示文档
      }
    })
    .catch(() => alive && setDocSource("cloud-error"));
  return () => {
    alive = false;
  };
}, [taskId]);

const initialAst = useMemo(() => loadedAst ?? demoWorkbenchAst(), [loadedAst]);

const handleAssert = useCallback((s: AssertSummary | null, err: boolean) => {
  setAssertSummary(s);
  setAssertError(err);
}, []);
const handleProvJump = useCallback((hit: ProvenanceHit) => {
  setProvJump(`溯源跳转:${hit.clause_id} → ${hit.anchor || "锚点未登记"}`);
  if (provTimer.current) clearTimeout(provTimer.current);
  provTimer.current = setTimeout(() => setProvJump(null), 3000);
}, []);
useEffect(() => () => { if (provTimer.current) clearTimeout(provTimer.current); }, []);

const handleSave = useCallback(async () => {
  const ast = editorRef.current?.serializeNow() ?? latestAstRef.current;
  if (!ast || !taskId || saving) return;
  latestAstRef.current = ast;
  setSaving(true);
  try {
    const doc = await putTaskDocument(taskId, { ast, schema_version: AST_SCHEMA_VERSION });
    setSavedAt(doc.updated_at ? new Date(doc.updated_at).toLocaleTimeString("zh-CN", { hour12: false }) : new Date().toLocaleTimeString("zh-CN", { hour12: false }));
  } catch (e) {
    setViolation(e instanceof ApiError ? e.message : "保存失败,请重试");
    if (violationTimer.current) clearTimeout(violationTimer.current);
    violationTimer.current = setTimeout(() => setViolation(null), 3000);
  } finally {
    setSaving(false);
  }
}, [taskId, saving]);
```

- 渲染:`<BidWriteEditor key={docEpoch} initialAst={initialAst} assertRunner={editorLocalAssert} onAssert={handleAssert} onProvenanceJump={handleProvJump} …>`;保存按钮 `disabled={saving}` 文案「保存中…」;演示数据 Badge → `docSource === "cloud" ? "云端文档" : docSource === "cloud-error" ? "云端加载失败(演示文档)" : "演示文档"`;violation notice 后加 `{provJump ? <div className="ed-notice" role="status">{provJump}</div> : null}`;状态栏追加:

```tsx
<span className="sep" />
{assertError ? (
  <span title="断言服务不可用——导出判定以预审查为准,不默认放行">校验未完成</span>
) : assertSummary ? (
  <span title={assertSummary.skipped.map((s) => `${s.code}:${s.reason ?? ""}`).join(";")}>
    校验 D0 {assertSummary.d0} · D1 {assertSummary.d1} · D2 {assertSummary.d2}
    {assertSummary.skipped.length > 0
      ? ` · 因 ${assertSummary.skipped.map((s) => s.code).join("/")} 跳过 ${assertSummary.skipped.reduce((a, b) => a + b.count, 0)}(不算通过)`
      : ""}
  </span>
) : (
  <span>校验待运行</span>
)}
```

- banner/capability 说明文案 M0/M1 → M2(「断言联动与 AST 存储已接入(演示执行器)」)。
- [x] **Step 4: bid-write.css 追加**(token 对齐 M1 `.bwx` 段;红/黄 token 复用既有 `--warn-*`/危险色变量,实现时先 grep 确认变量名)

```css
/* ── 批廿八 M2:provenance 角标 + liveAssert 断言装饰 ─────────────────── */
.bwx .bwe-prov-badge {
  display: inline-block;
  margin-left: 2px;
  padding: 0 3px;
  font-size: 11px;
  line-height: 16px;
  color: var(--main-600, #4f6bed);
  background: var(--surface-1, #fff);
  border: 1px solid var(--hairline, #e2e8f0);
  border-radius: 4px;
  vertical-align: super;
  user-select: none;
  cursor: pointer;
}
.bwx .bwe-prov-badge.broken {
  color: var(--bad-600, #dc2626);
  border-color: var(--bad-200, #fecaca);
  background: var(--bad-50, #fef2f2);
}
.bwx .bwx-assert-d1 {
  background: var(--warn-50, #fffbeb);
  border-bottom: 2px solid var(--warn-700, #b45309);
}
.bwx .bwx-assert-d0 {
  background: var(--bad-50, #fef2f2);
  border-bottom: 2px solid var(--bad-600, #dc2626);
}
```

- [x] **Step 5:** `pnpm typecheck`(本模块 0 错)/`pnpm lint`/editor 全量 rstest 绿
- [x] **Step 6: 提交**

```bash
git add frontend/src/extensions/bid-write/types.ts frontend/src/extensions/bid-write/api.ts frontend/src/extensions/bid-write/components/WorkbenchView.tsx frontend/src/app/bid-write/bid-write.css
git commit -m "feat(bid-write): 批廿八 M2-c 工作台接线——taskId 加载云端 AST(key 重挂,失败回退演示文档面)+保存=PUT(保存中态+失败提示)+校验状态栏(D0/D1/D2+SKIPPED 不算通过+校验未完成降级)+溯源跳转提示+token 化装饰样式"
```

---

### Task 4: gateway 重启 + 实机验证(宿主 :3000)

- [x] **Step 1:** `cd docker && docker compose -p eai-docker -f docker-compose-dev.yaml -f docker-compose.extensions.yaml -f docker-compose.ragflow.yaml restart gateway`
- [x] **Step 2:** curl 冒烟 `PUT/GET document` 登录态(cookie jar)或 pytest 已盖 → 至少确认 gateway 起来(`/health` 200)
- [x] **Step 3:** 写并跑 `C:/Users/admin/.claude/jobs/d2aa6c7f/tmp/qa-bidwrite-m2.mjs`(宿主 :3000,M1 脚本登录段复用):断言 ①校验状态栏出现(`D0 1 · D1 1`,todo P-101 D0+投标函 D1)②`.bwe-prov-badge` 文本 `[B-014][M-88]` ③点击标记文本→溯源提示出现且 3s 消退 ④编辑 name 列→校验 chip 仍在(未进「校验未完成」)⑤保存→PUT 200→状态栏「保存」更新 ⑥reload→`云端文档` badge+编辑内容仍在(往返实证)⑦截图
- [x] **Step 4:** 全量 rstest(components 单独跑——已知 task-form-dialog 全量并发隔离 flake 基线)

---

### Task 5: 收口(plan 勾选+wolf 四件套+memory)

- [x] plan 全勾;`git add -f` plan 文件
- [x] `.wolf/cerebrum.md`(Key Learnings:PluginKey.getState 侧信道测试法/Decoration.node vs inline 选型/演示执行器上限注记);`.wolf/memory.md` 批线;buglog(如有);anatomy(decor.ts 新文件)
- [x] auto-memory `bid-write-p1-beta28-m2-decor-liaison-landed.md` + MEMORY.md 索引行
- [x] **不推**(等「push」)

```bash
git add -f docs/superpowers/plans/2026-11-14-bid-write-p1-beta28-editor-m2-decor-liaison-plan.md
git add .wolf/cerebrum.md .wolf/memory.md .wolf/anatomy.md .wolf/buglog.json
git commit -m "docs(bid-write): 批廿八 M2 收口——plan 全勾+wolf 四件套(decor.ts 入 anatomy/cerebrum 侧信道测试法);NEXT=负偏离展开 schema 扩展(§5.4)+真执行器增量接线"
```

---

## Self-Review

- §5.1 provenance 角标/jump meta/broken → T2 ✓;登记实体反查挂后续批(诚实面已注)。
- §6 assert:apply 侧信道/纯装饰/SKIPPED 不当通过/校验未完成降级 → T2/T3 ✓。
- §13 M2=provenanceDecor/statusDecor/liveAssert+增量校验接线 → statusDecor 合并入 liveAssert(文中 status_mark 反射=持久通道,decoration=live 通道),M2 里程碑三件全覆盖 ✓。
- §5.4 负偏离展开 → 显式批廿九(边界声明)✓。
- 类型一致性:AssertPayload/AssertSummary/ProvenanceHit 于 T2 定义、T3 引用一致 ✓。
