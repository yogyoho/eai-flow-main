// EAI-CUSTOM 批廿六 M0——M0 演示文档(后端正文存储未接入;方案 §15② 最小样例:
// section/para/locked_paragraph/amount_cell/enum_cell/todo_block/toc_entry 全露脸)。
import { type AstJsonNode } from "./schema.gen";

export function demoWorkbenchAst(): AstJsonNode {
  return {
    type: "doc",
    content: [
      {
        type: "toc_entry",
        attrs: { title: "目录", page_placeholder: "—" },
      },
      {
        type: "section",
        attrs: { level: 1, title: "一、投标函", section_id: "S-bid-letter" },
        content: [
          {
            type: "para",
            attrs: { slot_id: "bl-opening" },
            content: [
              { type: "text", text: "致 " },
              {
                type: "text",
                text: "招标人",
                marks: [
                  {
                    type: "provenance",
                    attrs: {
                      clause_id: "B-014",
                      entity_id: "M-88",
                      anchor: "P.34",
                    },
                  },
                ],
              },
              {
                type: "text",
                text: ":根据贵方招标文件(编号 T-2026-118)要求,我方愿以人民币 ",
              },
              {
                type: "text",
                text: "1,280,000.00",
                marks: [
                  {
                    type: "status_mark",
                    attrs: { state: "D1", err_code: "SK-PS-003" },
                  },
                ],
              },
              {
                type: "text",
                text: " 元(大写:壹佰贰拾捌万元整)的投标总价,按招标文件要求完成全部工程内容。",
              },
            ],
          },
          {
            type: "locked_paragraph",
            attrs: { template_id: "BID-LOCK-001", similarity_floor: 0.98 },
            content: [
              {
                type: "text",
                text: "本投标函自开标之日起 90 个日历日内有效,我方确认已理解并接受招标文件全部条款。",
              },
            ],
          },
        ],
      },
      {
        type: "section",
        attrs: { level: 1, title: "二、报价表", section_id: "S-price" },
        content: [
          {
            type: "table",
            attrs: { table_type: "price" },
            content: [
              {
                type: "table_row",
                attrs: { row_id: "R-1" },
                content: [
                  {
                    type: "table_cell",
                    attrs: { col_role: "name" },
                    content: [{ type: "text", text: "设备 A" }],
                  },
                  {
                    type: "table_cell",
                    attrs: { col_role: "qty" },
                    content: [{ type: "text", text: "4" }],
                  },
                  {
                    type: "table_cell",
                    attrs: { col_role: "unit" },
                    content: [{ type: "text", text: "200,000.00" }],
                  },
                  {
                    type: "amount_cell",
                    attrs: {
                      readonly: true,
                      computed_expr: "qty*unit_price",
                      role: "amount",
                    },
                    content: [{ type: "text", text: "800,000.00" }],
                  },
                ],
              },
              {
                type: "table_row",
                attrs: { row_id: "R-2" },
                content: [
                  {
                    type: "table_cell",
                    attrs: { col_role: "name" },
                    content: [{ type: "text", text: "安装调试" }],
                  },
                  {
                    type: "table_cell",
                    attrs: { col_role: "qty" },
                    content: [{ type: "text", text: "1" }],
                  },
                  {
                    type: "table_cell",
                    attrs: { col_role: "unit" },
                    content: [{ type: "text", text: "460,000.00" }],
                  },
                  {
                    type: "amount_cell",
                    attrs: {
                      readonly: true,
                      computed_expr: "qty*unit_price",
                      role: "amount",
                    },
                    content: [{ type: "text", text: "460,000.00" }],
                  },
                ],
              },
              {
                type: "table_row",
                attrs: { row_id: "R-sum" },
                content: [
                  {
                    type: "table_cell",
                    attrs: { col_role: "name" },
                    content: [{ type: "text", text: "合计" }],
                  },
                  {
                    type: "enum_cell",
                    attrs: {
                      enum_values: ["完全响应", "正偏离", "负偏离"],
                      current: "完全响应",
                    },
                    content: [{ type: "text", text: "完全响应" }],
                  },
                  {
                    type: "amount_cell",
                    attrs: {
                      readonly: true,
                      computed_expr: "sum(amount)",
                      role: "total_num",
                    },
                    content: [{ type: "text", text: "1,260,000.00" }],
                  },
                  {
                    type: "amount_cell",
                    attrs: {
                      readonly: true,
                      computed_expr: "to_cn(total_num)",
                      role: "total_cn",
                    },
                    content: [{ type: "text", text: "壹佰贰拾陆万元整" }],
                  },
                ],
              },
            ],
          },
        ],
      },
      {
        type: "section",
        attrs: { level: 1, title: "三、供货承诺", section_id: "S-supply" },
        content: [
          {
            type: "todo_block",
            attrs: {
              missing: "供货期承诺函(关联 SK-CMN-005)",
              pending_item_id: "P-101",
              level: "D0",
              blocks_export: true,
            },
          },
        ],
      },
    ],
  };
}
