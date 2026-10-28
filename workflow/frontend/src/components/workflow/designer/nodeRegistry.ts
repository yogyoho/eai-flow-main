import {
  CircleNode,
  CircleNodeModel,
  DiamondNode,
  DiamondNodeModel,
  PolylineEdge,
  PolylineEdgeModel,
  RectNode,
  RectNodeModel,
  h,
  type LogicFlow,
} from "@logicflow/core";
import type { NodeTypeName } from "@/lib/types";

export const NODE_TYPE_BY_NAME: Record<NodeTypeName, number> = {
  start: 0,
  between: 1,
  end: 2,
  serial: 3,
  parallel: 4,
  inclusive: 5,
};

export const NODE_TYPE_META: Record<
  NodeTypeName,
  { label: string; short: string; description: string; rgb: string; color: string }
> = {
  start: {
    label: "开始节点",
    short: "开始",
    description: "流程唯一的入口",
    rgb: "103,194,58",
    color: "#67c23a",
  },
  between: {
    label: "审批节点",
    short: "审批",
    description: "人工审批 / 办理",
    rgb: "64,158,255",
    color: "#409eff",
  },
  end: {
    label: "结束节点",
    short: "结束",
    description: "流程在此完成",
    rgb: "245,108,108",
    color: "#f56c6c",
  },
  serial: {
    label: "互斥网关",
    short: "互斥",
    description: "按条件选择一个分支",
    rgb: "245,158,11",
    color: "#f59e0b",
  },
  parallel: {
    label: "并行网关",
    short: "并行",
    description: "多个分支同时流转",
    rgb: "19,194,194",
    color: "#13c2c2",
  },
  inclusive: {
    label: "包容网关",
    short: "包容",
    description: "满足条件的分支都执行",
    rgb: "146,84,222",
    color: "#9254de",
  },
};

const DONE = "56,161,105";
const TODO = "245,158,11";
const IDLE = "107,114,128";
const SELECTION_SHADOW = "drop-shadow(0 2px 7px rgba(15, 23, 42, 0.22))";

const DESIGN_THEME = {
  rect: { radius: 10, stroke: "#c7d0de", strokeWidth: 1.5, fill: "#ffffff" },
  circle: { r: 26, stroke: "#c7d0de", strokeWidth: 1.5, fill: "#ffffff" },
  diamond: { stroke: "#c7d0de", strokeWidth: 1.5, fill: "#ffffff" },
  nodeText: { color: "#344054", fontSize: 12, lineHeight: 1.3, overflowMode: "default" },
  edgeText: {
    color: "#667085",
    fontSize: 11,
    background: { fill: "#ffffff", stroke: "transparent", radius: 4 },
  },
  // LogicFlow defaults polyline corners to radius 8. The designer uses
  // orthogonal routes, so force sharp right-angle corners.
  polyline: { stroke: "#98a2b3", strokeWidth: 1.6, radius: 0 },
  // LogicFlow's "hollow" end arrow is a zero-area open chevron, so it renders
  // as a V instead of a filled triangle. The end-arrow view ignores fill.
  arrow: {
    offset: 10,
    verticalLength: 5,
    endArrowType: "hollow",
    strokeLinecap: "round",
    strokeLinejoin: "round",
  },
  anchor: { stroke: "#2f6fed", fill: "#ffffff", r: 3.6, strokeWidth: 1.5 },
  // Temporary line shown while dragging from an anchor to a target node.
  anchorLine: {
    stroke: "#2f6fed",
    strokeWidth: 1.8,
    strokeDasharray: "5 4",
    strokeLinecap: "round",
  },
  snapline: { stroke: "#2f6fed", strokeWidth: 1 },
  // LogicFlow's boxed selection overlays are disabled in FlowDesigner. Keep
  // these transparent as a fallback so no sharp black rectangle can flash.
  outline: { fill: "none", stroke: "transparent", strokeWidth: 0 },
  edgeOutline: {
    fill: "transparent",
    stroke: "transparent",
    strokeWidth: 0,
    strokeDasharray: "none",
    hover: { stroke: "transparent" },
  },
  edgeAdjust: { r: -1 },
};

interface NodeStyleProps {
  status?: number | string | null;
  chartStatusColor?: string[];
}

interface EdgeStyleProps extends NodeStyleProps {
  skipType?: string | null;
}

function palette(props: NodeStyleProps, type: NodeTypeName) {
  const status = Number(props.status);
  const colors =
    Array.isArray(props.chartStatusColor) && props.chartStatusColor.length === 3
      ? props.chartStatusColor
      : [DONE, TODO, IDLE];
  if (status === 2) return { rgb: colors[0], dashed: false };
  if (status === 1) return { rgb: colors[1], dashed: true };
  return { rgb: NODE_TYPE_META[type].rgb, dashed: false };
}

function applyNodeStyle(
  style: Record<string, unknown>,
  props: NodeStyleProps,
  type: NodeTypeName,
  state?: { isSelected?: boolean; isHovered?: boolean },
) {
  const { rgb, dashed } = palette(props, type);
  style.stroke = `rgb(${rgb})`;
  style.strokeWidth = 1.6;
  style.fill = `rgba(${rgb}, 0.055)`;
  style.radius = type === "between" ? 10 : style.radius;
  if (dashed) style.strokeDasharray = "5 4";
  style.shadow = `drop-shadow(0 2px 7px rgba(${rgb}, 0.14))`;
  if (state?.isSelected) {
    // Selection keeps the node's own palette. A heavier stroke plus a soft
    // neutral shadow is enough to read as selected without a colored overlay.
    style.strokeWidth = 2.4;
    style.filter = SELECTION_SHADOW;
  } else if (state?.isHovered) {
    style.filter = "drop-shadow(0 4px 10px rgba(15, 23, 42, 0.14))";
  }
  return style;
}

function textStyle(style: Record<string, unknown>, props: NodeStyleProps, type: NodeTypeName) {
  const { rgb } = palette(props, type);
  style.fontSize = 12;
  style.fontWeight = 500;
  style.color = type === "between" ? "#344054" : `rgb(${rgb})`;
  style.fill = style.color;
  return style;
}

/* Anchors sit on the node border, so their ring follows the node's own
   palette (including progress/status colors) instead of a fixed accent. */
function anchorStyle(props: NodeStyleProps, type: NodeTypeName) {
  const { rgb } = palette(props, type);
  return {
    ...DESIGN_THEME.anchor,
    stroke: `rgb(${rgb})`,
    fill: "#ffffff",
  } as never;
}

/* Loading and property changes keep the label at the center of the node. */
function centerLabel(model: {
  x: number;
  y: number;
  text: { x: number; y: number };
  properties: NodeStyleProps;
}) {
  model.text.x = model.x;
  model.text.y = model.y;
}

function iconColor(style: Record<string, unknown>) {
  return typeof style.stroke === "string" ? style.stroke : "#409eff";
}

/* Small rounded badge with a check mark, drawn at the top-left of an approval
   node — same position as the reference classic chart. */
function approvalBadge(cx: number, cy: number, color: string) {
  return h("g", { className: "lf-node-badge" }, [
    h("rect", {
      x: cx - 9,
      y: cy - 9,
      width: 18,
      height: 18,
      rx: 5,
      fill: "rgba(255,255,255,0.92)",
      stroke: color,
      "stroke-opacity": 0.35,
      "stroke-width": 1,
    }),
    h("path", {
      d: `M ${cx - 3.6} ${cy + 0.2} l 2.6 2.6 l 4.8 -5.2`,
      fill: "none",
      stroke: color,
      "stroke-width": 1.7,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    }),
  ]);
}

/* Gateway glyphs: × for exclusive, + for parallel, ◎ for inclusive. */
function gatewayBadge(cx: number, cy: number, color: string, type: NodeTypeName) {
  const stroke = {
    fill: "none",
    stroke: color,
    "stroke-width": 1.8,
    "stroke-linecap": "round",
  };
  if (type === "parallel") {
    return h("g", { className: "lf-node-badge" }, [
      h("line", { x1: cx - 8, y1: cy, x2: cx + 8, y2: cy, ...stroke }),
      h("line", { x1: cx, y1: cy - 8, x2: cx, y2: cy + 8, ...stroke }),
    ]);
  }
  if (type === "inclusive") {
    return h("g", { className: "lf-node-badge" }, [
      h("circle", { cx, cy, r: 8.5, fill: "none", stroke: color, "stroke-width": 1.6 }),
      h("circle", { cx, cy, r: 3.2, fill: color, "fill-opacity": 0.9 }),
    ]);
  }
  return h("g", { className: "lf-node-badge" }, [
    h("line", {
      x1: cx - 7,
      y1: cy - 7,
      x2: cx + 7,
      y2: cy + 7,
      ...stroke,
    }),
    h("line", {
      x1: cx - 7,
      y1: cy + 7,
      x2: cx + 7,
      y2: cy - 7,
      ...stroke,
    }),
  ]);
}

class BetweenNodeView extends RectNode {
  getShape() {
    const model = this.props.model;
    const shape = super.getShape();
    const style = model.getNodeStyle() as Record<string, unknown>;
    return h("g", {}, [
      shape,
      approvalBadge(
        model.x - model.width / 2 + 16,
        model.y - model.height / 2 + 16,
        iconColor(style),
      ),
    ]) as never;
  }
}

class GatewayNodeView extends DiamondNode {
  getShape() {
    const model = this.props.model;
    const shape = super.getShape();
    const style = model.getNodeStyle() as Record<string, unknown>;
    const type = (model.type as NodeTypeName) || "serial";
    return h("g", {}, [
      shape,
      gatewayBadge(model.x, model.y, iconColor(style), type),
    ]) as never;
  }
  getText() {
    return null;
  }
}

class StartNodeModel extends CircleNodeModel {
  setAttributes() {
    this.r = 28;
    centerLabel(this as never);
  }
  getNodeStyle() {
    return applyNodeStyle(
      super.getNodeStyle() as Record<string, unknown>,
      this.properties as NodeStyleProps,
      "start",
      this,
    );
  }
  getAnchorStyle() {
    return anchorStyle(this.properties as NodeStyleProps, "start");
  }
  getTextStyle() {
    const style = textStyle(
      super.getTextStyle() as Record<string, unknown>,
      this.properties as NodeStyleProps,
      "start",
    );
    style.fontSize = 11;
    return style as never;
  }
}

class EndNodeModel extends CircleNodeModel {
  setAttributes() {
    this.r = 28;
    centerLabel(this as never);
  }
  getNodeStyle() {
    return applyNodeStyle(
      super.getNodeStyle() as Record<string, unknown>,
      this.properties as NodeStyleProps,
      "end",
      this,
    );
  }
  getAnchorStyle() {
    return anchorStyle(this.properties as NodeStyleProps, "end");
  }
  getTextStyle() {
    const style = textStyle(
      super.getTextStyle() as Record<string, unknown>,
      this.properties as NodeStyleProps,
      "end",
    );
    style.fontSize = 11;
    return style as never;
  }
}

class BetweenNodeModel extends RectNodeModel {
  setAttributes() {
    const sized = this as unknown as { width: number; height: number };
    sized.width = 176;
    sized.height = 52;
    this.radius = 10;
    centerLabel(this as never);
  }
  getNodeStyle() {
    return applyNodeStyle(
      super.getNodeStyle() as Record<string, unknown>,
      this.properties as NodeStyleProps,
      "between",
      this,
    );
  }
  getAnchorStyle() {
    return anchorStyle(this.properties as NodeStyleProps, "between");
  }
  getTextStyle() {
    return textStyle(
      super.getTextStyle() as Record<string, unknown>,
      this.properties as NodeStyleProps,
      "between",
    ) as never;
  }
}

class GatewayNodeModel extends DiamondNodeModel {
  setAttributes() {
    super.setAttributes();
    /* DiamondNodeModel.width / height are mobx computed getters derived from
       rx / ry — assigning width or height directly throws. */
    this.rx = 30;
    this.ry = 30;
    centerLabel(this as never);
    /* Gateway views render only the branch glyph, so there is no visible
       label to edit. Keep LogicFlow from opening an invisible inline editor. */
    this.text.editable = false;
  }
  getNodeStyle() {
    const type = (this.type as NodeTypeName) || "serial";
    return applyNodeStyle(
      super.getNodeStyle() as Record<string, unknown>,
      this.properties as NodeStyleProps,
      type,
      this,
    );
  }
  getAnchorStyle() {
    const type = (this.type as NodeTypeName) || "serial";
    return anchorStyle(this.properties as NodeStyleProps, type);
  }
  getTextStyle() {
    const type = (this.type as NodeTypeName) || "serial";
    return textStyle(
      super.getTextStyle() as Record<string, unknown>,
      this.properties as NodeStyleProps,
      type,
    ) as never;
  }
}

class SerialNodeModel extends GatewayNodeModel {}
class ParallelNodeModel extends GatewayNodeModel {}
class InclusiveNodeModel extends GatewayNodeModel {}

/* Selected edges show a single hollow connector circle at each endpoint. It
   uses the same radius and stroke width as the node anchor dots so both
   connector affordances read as one system. */
function edgeEndpoint(x: number, y: number, color: string) {
  return h(
    "g",
    {
      className: "lf-edge-endpoint",
      transform: `translate(${x} ${y})`,
    },
    [
      h("circle", {
        r: 3.6,
        fill: "none",
        stroke: color,
        "stroke-width": 1.5,
      }),
    ],
  );
}

/* Draw the endpoint handles on top of the polyline. They are hollow so the
   edge line and its arrow head stay readable underneath. */
class SkipEdgeView extends PolylineEdge {
  getShape() {
    const shape = super.getShape();
    const model = this.props.model as PolylineEdgeModel;
    const style = model.getEdgeStyle() as Record<string, unknown>;
    const color = typeof style.stroke === "string" ? style.stroke : "#94a3b8";
    const start = model.getAdjustStart();
    const end = model.getAdjustEnd();
    return h("g", {}, [
      shape,
      edgeEndpoint(start.x, start.y, color),
      edgeEndpoint(end.x, end.y, color),
    ]) as never;
  }
}

class SkipEdgeModel extends PolylineEdgeModel {
  getArrowStyle() {
    const style = super.getArrowStyle() as Record<string, unknown>;
    style.endArrowType = "hollow";
    style.strokeWidth = this.isSelected ? 2.2 : 1.8;
    return style as never;
  }

  getEdgeStyle() {
    const style = super.getEdgeStyle() as Record<string, unknown>;
    const props = this.properties as EdgeStyleProps;
    const status = Number(props.status);
    const colors =
      Array.isArray(props.chartStatusColor) && props.chartStatusColor.length === 3
        ? props.chartStatusColor
        : [DONE, TODO, IDLE];
    let rgb = "148,163,184";
    if (status === 2) rgb = colors[0];
    else if (status === 1) rgb = colors[1];
    else if (props.skipType === "REJECT") rgb = "244,63,94";
    style.stroke = `rgb(${rgb})`;
    style.strokeWidth = 1.7;
    style.endArrow = true;
    if (status === 1) style.strokeDasharray = "5 4";
    if (this.isSelected) {
      // Preserve the edge's status/reject color and dash pattern.
      style.strokeWidth = 2.4;
      style.filter = SELECTION_SHADOW;
    } else if (this.isHovered) {
      style.strokeWidth = 2;
      style.filter = "drop-shadow(0 1px 3px rgba(15, 23, 42, 0.14))";
    }
    return style;
  }
  getTextStyle() {
    const style = super.getTextStyle() as Record<string, unknown>;
    const props = this.properties as EdgeStyleProps;
    if (props.skipType === "REJECT") style.color = "#e11d48";
    else if (Number(props.status) === 1) style.color = "#b45309";
    else if (Number(props.status) === 2) style.color = "#15803d";
    else style.color = "#667085";
    style.fontSize = 11;
    style.fill = style.color;
    return style as never;
  }
}

export function registerWorkflowNodes(lf: LogicFlow) {
  lf.register({ type: "start", view: CircleNode, model: StartNodeModel } as never);
  lf.register({ type: "end", view: CircleNode, model: EndNodeModel } as never);
  lf.register({ type: "between", view: BetweenNodeView, model: BetweenNodeModel } as never);
  lf.register({ type: "serial", view: GatewayNodeView, model: SerialNodeModel } as never);
  lf.register({ type: "parallel", view: GatewayNodeView, model: ParallelNodeModel } as never);
  lf.register({ type: "inclusive", view: GatewayNodeView, model: InclusiveNodeModel } as never);
  lf.register({ type: "skip", view: SkipEdgeView, model: SkipEdgeModel } as never);
}

export const DESIGNER_THEME = DESIGN_THEME;
