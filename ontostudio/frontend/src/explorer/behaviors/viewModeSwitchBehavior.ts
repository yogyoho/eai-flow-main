// Vendored from semantica-agi/semantica@7057387775ecdf74c14e38d0067fd8e1267eaaf8 explorer/src/workspaces/GraphWorkspace/behaviors/viewModeSwitchBehavior.ts (MIT)
import type { GraphBehavior } from "./types";
import type { GraphViewMode } from "../types";

export function createViewModeSwitchBehavior(): GraphBehavior {
  let lastViewMode: GraphViewMode | null = null;

  return {
    id: "view-mode-switch",
    attach: () => {},
    detach: () => {
      lastViewMode = null;
    },
    onStateChange: (context, interactionState) => {
      if (interactionState.viewMode === lastViewMode) {
        return;
      }

      lastViewMode = interactionState.viewMode;
      const nextFocusedNodeId = interactionState.focusedNodeId;

      if (interactionState.viewMode === "focused" && nextFocusedNodeId) {
        context.dispatchAction({ type: "focusNode", nodeId: nextFocusedNodeId });
        return;
      }

      context.dispatchAction({ type: "fitView" });
    },
  };
}
