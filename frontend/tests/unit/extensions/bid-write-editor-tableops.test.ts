// 批卅三 T1:表格行操作 golden——非价格表加/删行;价格表拒绝;表外 null;单行表保底。
import { describe, expect, it } from "@rstest/core";
import { TextSelection } from "prosemirror-state";

import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { createBidWriteEditorState } from "@/extensions/bid-write/editor/state";
import { addRowInSelection, deleteRowInSelection } from "@/extensions/bid-write/editor/tableOps";

function posInFirstTableCell(s: ReturnType<typeof createBidWriteEditorState>): number {
  let hit = -1;
  s.doc.descendants((n, p) => {
    if (hit < 0 && n.type.name === "table_cell") hit = p + 1;
  });
  if (hit < 0) throw new Error("no table_cell");
  return hit;
}

function selectAt(s: ReturnType<typeof createBidWriteEditorState>, pos: number) {
  const tr = s.tr.setSelection(TextSelection.near(s.doc.resolve(pos)));
  return s.apply(tr);
}

describe("tableOps", () => {
  it("demo 价格表:加行/删行均拒绝(price 保护)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s = selectAt(s0, posInFirstTableCell(s0));
    expect(addRowInSelection(s)).toBeNull();
    expect(deleteRowInSelection(s)).toBeNull();
  });

  it("表外段落 → 两操作均 null", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    let paraPos = -1;
    s0.doc.descendants((n, p) => {
      if (paraPos < 0 && n.type.name === "para") paraPos = p + 1;
    });
    if (paraPos < 0) throw new Error("no para");
    const s = selectAt(s0, paraPos);
    expect(addRowInSelection(s)).toBeNull();
    expect(deleteRowInSelection(s)).toBeNull();
  });

  it("响应表:加行→行数+1 全空新行;删行→行数-1;单行表删→null", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const mk = (text: string) =>
      s0.schema.nodes.table_row!.create({ row_id: "" }, [
        s0.schema.nodes.table_cell!.create({ col_role: "name" }, [s0.schema.text(text)]),
        s0.schema.nodes.table_cell!.create({ col_role: "remark" }, [s0.schema.text(text)]),
      ]);
    const table = s0.schema.nodes.table!.create({ table_type: "response" }, [mk("行1"), mk("行2")]);
    const doc2 = s0.schema.nodes.doc!.create({}, [
      s0.schema.nodes.section!.create({ level: 1 }, [table]),
    ]);
    const s1 = createBidWriteEditorState(doc2.toJSON() as never, {});
    const s = selectAt(s1, posInFirstTableCell(s1));
    const countRows = (st: ReturnType<typeof createBidWriteEditorState>) => {
      let c = 0;
      st.doc.descendants((n) => {
        if (n.type.name === "table_row") c++;
      });
      return c;
    };
    const addTr = addRowInSelection(s);
    expect(addTr).not.toBeNull();
    const s3 = s.apply(addTr!);
    expect(countRows(s3)).toBe(3);
    const delTr = deleteRowInSelection(s3);
    expect(delTr).not.toBeNull();
    const s4 = s3.apply(delTr!);
    expect(countRows(s4)).toBe(2);
    // 删除光标所在行后选区落在表外——重新选入单元格再删(真实交互路径)
    const s4r = selectAt(s4, posInFirstTableCell(s4));
    const delTr2 = deleteRowInSelection(s4r);
    expect(delTr2, `pos=${s4r.selection.$from.pos}`).not.toBeNull();
    const s5 = s4r.apply(delTr2!);
    expect(countRows(s5)).toBe(1);
    // 只剩 1 行:先重新选入,再删 → null(保底)
    const s5r = selectAt(s5, posInFirstTableCell(s5));
    expect(deleteRowInSelection(s5r)).toBeNull();
  });
});
