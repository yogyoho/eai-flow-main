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
            <svg
              className={`details-block-chevron${collapsed ? " is-collapsed" : ""}`}
              viewBox="0 0 16 16"
              width="12"
              height="12"
              aria-hidden="true"
            >
              <path
                d="M6 4l4 4-4 4"
                stroke="currentColor"
                strokeWidth="1.5"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
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
