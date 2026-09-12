// Vendored from semantica-agi/semantica@7057387775ecdf74c14e38d0067fd8e1267eaaf8 explorer/src/workspaces/GraphWorkspace/behaviors/clickSelectionBehavior.ts (MIT)
import type { GraphBehavior } from "./types";

export const clickSelectionBehavior: GraphBehavior = {
  id: "click-selection",
  attach: () => {},
  detach: () => {},
  onNodeClick: (context, nodeId) => {
    context.setHoveredNodeId(nodeId);
    context.onEdgeSelectionChange("");
    if (context.getInteractionState().selectedNodeId === nodeId) {
      context.onNodeSelectionChange("");
    } else {
      context.onNodeSelectionChange(nodeId);
    }
  },
  onEdgeClick: (context, edgeId) => {
    context.setHoveredNodeId(null);
    if (context.getInteractionState().selectedEdgeId === edgeId) {
      context.onEdgeSelectionChange("");
    } else {
      context.onEdgeSelectionChange(edgeId);
    }
  },
  onStageClick: (context) => {
    context.setHoveredNodeId(null);
    context.onEdgeSelectionChange("");
    context.onNodeSelectionChange("");
  },
};
