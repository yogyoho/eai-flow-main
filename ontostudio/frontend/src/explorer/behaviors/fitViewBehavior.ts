// Vendored from semantica-agi/semantica@7057387775ecdf74c14e38d0067fd8e1267eaaf8 explorer/src/workspaces/GraphWorkspace/behaviors/fitViewBehavior.ts (MIT)
import type { GraphBehavior } from "./types";

export const fitViewBehavior: GraphBehavior = {
  id: "fit-view",
  attach: () => {},
  detach: () => {},
  performAction: (context, action) => {
    if (action.type !== "fitView") {
      return false;
    }

    context.fitCurrentView();
    return true;
  },
};
