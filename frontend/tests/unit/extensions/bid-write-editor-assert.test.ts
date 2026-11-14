// 批廿八 M2 T2:editorLocalAssert 本地确定性演示执行器(纯 AST,不碰 PM/DOM)。
// demo 文档自带面:行 4×200,000=800,000 ✓;合计 1,260,000=和 ✓;投标函金额
// 1,280,000 ≠ 合计(故意 SK-PS-003 面,且带 status_mark D1);todo P-101 level D0。
// doc.content 结构:[toc_entry, section投标函, section报价表, section供货承诺]。
import { describe, expect, test } from "@rstest/core";

import { editorLocalAssert, summarize } from "@/extensions/bid-write/editor/decor";
import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { hydrateAst, serializeDoc } from "@/extensions/bid-write/editor/doc";
import { type AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";

const demo = () => demoWorkbenchAst();

/** 结构守卫:noUncheckedIndexedAccess 下的显式收窄(结构漂移即抛) */
function at<T>(value: T | undefined): T {
  if (value === undefined) throw new Error("demo 结构漂移");
  return value;
}

/** 取 price 表第 i 行(AST JSON 形) */
function priceRow(ast: AstJsonNode, i: number) {
  const table = at(at(ast.content)[2]).content;
  return at(at(table)[0]).content![i];
}

function letterPara(ast: AstJsonNode) {
  return at(at(at(at(ast.content)[1]).content)[0]);
}

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
    expect(sum.d2).toBe(0);
  });

  test("行金额被改 → 行 D0 SK-PS-008 + 合计失配 D0 SK-PS-003", () => {
    const ast = demo();
    const row = at(priceRow(ast, 0));
    at(at(at(row.content)[3]).content![0]).text = "700,000.00";
    const payload = editorLocalAssert(ast);
    expect(payload.states["price:R-1"]).toMatchObject({ state: "D0", err_code: "SK-PS-008" });
    expect(payload.states["price:R-sum"]).toMatchObject({ state: "D0", err_code: "SK-PS-003" });
  });

  test("投标函金额改成合计值 → 失配消失(status_mark 反射 D1 仍在)", () => {
    const ast = demo();
    const para = letterPara(ast);
    for (const t of at(para.content)) {
      if (t.text === "1,280,000.00") t.text = "1,260,000.00";
    }
    const payload = editorLocalAssert(ast);
    expect(payload.states["bl-opening"]).toMatchObject({ state: "D1", err_code: "SK-PS-003" });
    expect(payload.states["price:R-sum"]).toBeUndefined();
  });

  test("金额格非法(非金额文本)→ SK-PS-007 D0", () => {
    const ast = demo();
    at(at(at(at(priceRow(ast, 1)).content)[3]).content![0]).text = "待定";
    const payload = editorLocalAssert(ast);
    expect(payload.states["price:R-2"]).toMatchObject({ state: "D0", err_code: "SK-PS-007" });
  });

  test("severity 合并:D0 压过 D1(同 key:todo 已 D0,status_mark D1 不降级)", () => {
    const payload = editorLocalAssert(demo());
    expect(payload.states["todo:P-101"]?.state).toBe("D0");
  });

  test("往返稳定:serialize∘hydrate 后断言键集一致(装饰前数据面纯函数)", () => {
    const rt = serializeDoc(hydrateAst(demoWorkbenchAst()));
    const a = editorLocalAssert(demo());
    const b = editorLocalAssert(rt);
    expect(Object.keys(b.states).sort()).toEqual(Object.keys(a.states).sort());
  });
});
