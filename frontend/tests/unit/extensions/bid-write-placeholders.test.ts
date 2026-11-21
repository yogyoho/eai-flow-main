// 批卅六:占位符清单/空章节判定纯函数 golden——待填面板与「空」标记的数据源。
import { describe, expect, it } from "@rstest/core";

import { astSections } from "@/extensions/bid-write/editor/outline";
import {
  astPlaceholders,
  pendingPlaceholders,
  sameVariableInfo,
} from "@/extensions/bid-write/editor/placeholders";
import type { AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";

const ast = {
  type: "doc",
  content: [
    {
      type: "section",
      attrs: { title: "一、投标函", level: 1 },
      content: [
        {
          type: "para",
          content: [
            { type: "text", text: "编号" },
            {
              type: "placeholder",
              attrs: {
                slot_id: "a",
                label: "采购编号",
                placeholder_type: "str",
                value: "",
                required: true,
                source: "doc:1",
              },
            },
            {
              type: "placeholder",
              attrs: {
                slot_id: "b",
                label: "签署日期",
                placeholder_type: "date",
                value: "2026-11-20",
                required: true,
                source: "",
              },
            },
          ],
        },
        {
          type: "section",
          attrs: { title: "9.2服务方案", level: 2 },
          content: [{ type: "para", content: [] }],
        },
      ],
    },
  ],
} as unknown as AstJsonNode;

describe("astPlaceholders", () => {
  it("提取占位符并标注所在章节;空值过滤为待填", () => {
    const all = astPlaceholders(ast);
    expect(all).toHaveLength(2);
    expect(all[0]).toMatchObject({ slotId: "a", label: "采购编号", section: "一、投标函" });
    const pending = pendingPlaceholders(ast);
    expect(pending).toHaveLength(1);
    expect(pending[0].slotId).toBe("a");
  });
});

describe("astSections 空章节", () => {
  it("空 section textLength=0;父级不把子章节文本双算", () => {
    const sections = astSections(ast);
    expect(sections).toHaveLength(2);
    const letter = sections[0];
    const empty = sections[1];
    expect(empty.title).toBe("9.2服务方案");
    expect(empty.textLength).toBe(0);
    // 父级只含直接文本「编号」(2 字)+ 占位符无文本 = 2,不含子章节
    expect(letter.textLength).toBe(2);
  });
});

describe("sameVariableInfo 全局替换", () => {
  // 批卅六-b:签署日期裂成 N 个 slot(标签带全角空格变体)是「改 1 漏 N-1」根源
  const varAst = {
    type: "doc",
    content: [
      {
        type: "section",
        attrs: { title: "一、投标函", level: 1 },
        content: [
          {
            type: "para",
            content: [
              { type: "placeholder", attrs: { slot_id: "d1", label: "日期", placeholder_type: "date", value: "2026-11-20", required: true, source: "" } },
              { type: "placeholder", attrs: { slot_id: "d2", label: "日  期", placeholder_type: "date", value: "2026-11-20", required: true, source: "" } },
              { type: "placeholder", attrs: { slot_id: "d3", label: "日\u3000期", placeholder_type: "date", value: "", required: true, source: "" } },
              // 同标签但已填不同值=显式特例,不连带
              { type: "placeholder", attrs: { slot_id: "d4", label: "日期", placeholder_type: "date", value: "2026-12-01", required: true, source: "" } },
              // 同值但不同标签(成立时间≠签署日期),不连带
              { type: "placeholder", attrs: { slot_id: "f1", label: "成立时间", placeholder_type: "date", value: "2026-11-20", required: true, source: "" } },
            ],
          },
        ],
      },
    ],
  } as unknown as AstJsonNode;

  it("同归一化标签+同值/未填计入;不同值与不同标签排除", () => {
    const info = sameVariableInfo(varAst, "d1");
    expect(info.label).toBe("日期");
    // d1 自身 + d2(空白变体同值) + d3(未填) = 3;d4/d5 排除
    expect(info.total).toBe(3);
  });

  it("从待填清单(未填 slot)发起同样全局", () => {
    const info = sameVariableInfo(varAst, "d3");
    // 保守语义:未填起点只连带同标签的其他未填(d3 自身);
    // 已填不同值(2026-11-20)是显式结果,不连带覆盖
    expect(info.total).toBe(1);
  });
});
