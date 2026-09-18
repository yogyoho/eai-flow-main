// Vendored from semantica-agi/semantica@7057387775ecdf74c14e38d0067fd8e1267eaaf8 explorer/src/workspaces/GraphWorkspace/behaviors/searchFocusBehavior.ts (MIT)
import type { GraphBehavior } from "./types";

export function createSearchFocusBehavior(): GraphBehavior {
  let lastSelectedNodeId = "";
  let lastViewMode = "";

  return {
    id: "search-focus",
    attach: () => {},
    detach: () => {
      lastSelectedNodeId = "";
      lastViewMode = "";
    },
    onStateChange: (context, interactionState) => {
      const nextSelectedNodeId = interactionState.selectedNodeId;
      const nextViewMode = interactionState.viewMode;
      if (nextViewMode !== lastViewMode) {
        lastViewMode = nextViewMode;
        lastSelectedNodeId = nextSelectedNodeId;
        return;
      }
      if (!nextSelectedNodeId || nextSelectedNodeId === lastSelectedNodeId) {
        lastSelectedNodeId = nextSelectedNodeId;
        lastViewMode = nextViewMode;
        return;
      }

      lastSelectedNodeId = nextSelectedNodeId;
      lastViewMode = nextViewMode;
      context.dispatchAction({
        type: nextViewMode === "grouped" ? "centerGroupedSelection" : "centerSelection",
        nodeId: nextSelectedNodeId,
      });
    },
  };
}
