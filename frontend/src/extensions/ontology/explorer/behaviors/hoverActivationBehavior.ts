// Vendored from semantica-agi/semantica@7057387775ecdf74c14e38d0067fd8e1267eaaf8 explorer/src/workspaces/GraphWorkspace/behaviors/hoverActivationBehavior.ts (MIT)
import type { GraphBehavior } from "./types";

export const hoverActivationBehavior: GraphBehavior = {
  id: "hover-activation",
  attach: () => {},
  detach: () => {},
  onNodeEnter: (context, nodeId) => {
    context.setHoveredNodeId(nodeId);
  },
  onNodeLeave: (context, nodeId) => {
    if (context.getInteractionState().hoveredNodeId === nodeId) {
      context.setHoveredNodeId(null);
    }
  },
};
