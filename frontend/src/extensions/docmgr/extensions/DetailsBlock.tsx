// EAI-CUSTOM (计算书): <details><summary> 折叠块——给排水计算书技能
// (render_calc_blocks.py) 特意生成该 HTML 格式，工件区契约保留折叠；
// BlockNote 无原生折叠块，自研 detailsBlock 以在编辑器内保住折叠语义。
// 导入/导出转换见 utils/detailsMarkdown.ts。

import { createReactBlockSpec } from "@blocknote/react";

export const DetailsBlock = createReactBlockSpec(
  {
    type: "detailsBlock",
    content: "inline",
    propSchema: {
      collapsed: { default: false, values: [false, true] },
    },
  },
  {
    meta: { selectable: true },
    render: (props) => {
      const { block, editor, contentRef } = props;
      const collapsed = block.props.collapsed === true;

      const toggle = () => {
        editor.updateBlock(block, {
          props: { collapsed: !collapsed },
        } as Parameters<typeof editor.updateBlock>[1]);
      };

      return (
        <div
          className="details-block-wrapper"
          data-details-collapsed={collapsed ? "true" : "false"}
        >
          <span
            className="details-block-toggle"
            role="button"
            tabIndex={0}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "展开计算过程" : "收起计算过程"}
            onClick={toggle}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggle();
              }
            }}
            contentEditable={false}
          >
            <span className={`details-block-marker${collapsed ? " is-collapsed" : ""}`} aria-hidden="true">
              {collapsed ? "▸" : "▾"}
            </span>
          </span>
          <div
            ref={contentRef}
            className="details-block-summary-text"
            data-placeholder="摘要"
          />
        </div>
      );
    },
  },
)();
