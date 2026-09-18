// Vendored from semantica-agi/semantica@7057387775ecdf74c14e38d0067fd8e1267eaaf8 explorer/src/workspaces/GraphWorkspace/behaviors/types.ts (MIT)
import type Graph from "graphology";
import type Sigma from "sigma";

import { graph, type EdgeAttributes, type NodeAttributes } from "../graphStore";
import type { GraphCameraState, GraphInteractionState } from "../types";

export type GraphBehaviorActionRequest =
  | { type: "fitView" }
  | { type: "focusNode"; nodeId: string }
  | { type: "centerSelection"; nodeId: string }
  | { type: "centerGroupedSelection"; nodeId: string };

export interface GraphBehaviorContext {
  sigma: Sigma;
  graph: typeof graph | Graph<NodeAttributes, EdgeAttributes>;
  displayGraph: typeof graph | Graph<NodeAttributes, EdgeAttributes>;
  getInteractionState: () => GraphInteractionState;
  setHoveredNodeId: (nodeId: string | null) => void;
  onNodeSelectionChange: (nodeId: string) => void;
  onEdgeSelectionChange: (edgeId: string) => void;
  focusNodeInView: (nodeId: string) => void;
  centerSelectionInView: (nodeId: string) => void;
  centerGroupedSelectionInView: (nodeId: string) => void;
  fitCurrentView: () => void;
  dispatchAction: (action: GraphBehaviorActionRequest) => void;
}

export interface GraphBehavior {
  id: string;
  attach: (context: GraphBehaviorContext) => void;
  detach: (context: GraphBehaviorContext) => void;
  onNodeEnter?: (context: GraphBehaviorContext, nodeId: string) => void;
  onNodeLeave?: (context: GraphBehaviorContext, nodeId: string) => void;
  onNodeClick?: (context: GraphBehaviorContext, nodeId: string) => void;
  onEdgeClick?: (context: GraphBehaviorContext, edgeId: string) => void;
  onStageClick?: (context: GraphBehaviorContext) => void;
  onCameraChange?: (context: GraphBehaviorContext, cameraState: GraphCameraState) => void;
  onStateChange?: (context: GraphBehaviorContext, interactionState: GraphInteractionState) => void;
  apply?: (context: GraphBehaviorContext, interactionState: GraphInteractionState) => void;
  performAction?: (context: GraphBehaviorContext, action: GraphBehaviorActionRequest) => boolean;
}
