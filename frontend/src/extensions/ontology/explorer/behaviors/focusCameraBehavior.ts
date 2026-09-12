// Vendored from semantica-agi/semantica@7057387775ecdf74c14e38d0067fd8e1267eaaf8 explorer/src/workspaces/GraphWorkspace/behaviors/focusCameraBehavior.ts (MIT)
import type { GraphBehavior } from "./types";

export const focusCameraBehavior: GraphBehavior = {
  id: "focus-camera",
  attach: () => {},
  detach: () => {},
  performAction: (context, action) => {
    if (action.type === "focusNode") {
      context.focusNodeInView(action.nodeId);
      return true;
    }

    if (action.type === "centerSelection") {
      context.centerSelectionInView(action.nodeId);
      return true;
    }

    if (action.type === "centerGroupedSelection") {
      context.centerGroupedSelectionInView(action.nodeId);
      return true;
    }

    return false;
  },
};
