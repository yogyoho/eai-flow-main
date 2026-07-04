import { useQuery } from "@tanstack/react-query";

import { fetch } from "../api/fetcher";
import { getBackendBaseURL } from "../config";

/**
 * Backend-driven UI behavior toggles. Source of truth is `config.yaml`'s `ui:`
 * section, surfaced via GET /api/ui/config (hot-reloadable).
 */
export interface UIConfig {
  /** Show tool (bash) stdout in the chat UI. Default false (upstream deer-flow
   * hides it for chat cleanliness). Flip on for debugging execution-style skills. */
  show_tool_output: boolean;
}

const FALLBACK: UIConfig = { show_tool_output: false };

async function fetchUIConfig(): Promise<UIConfig> {
  const response = await fetch(`${getBackendBaseURL()}/api/ui/config`);
  if (!response.ok) {
    return FALLBACK;
  }
  const data = (await response.json()) as Partial<UIConfig>;
  return { show_tool_output: data.show_tool_output === true };
}

/**
 * Fetch UI config. TanStack Query dedupes by queryKey, so calling this in
 * multiple components issues one request. staleTime keeps it stable across
 * re-renders; config.yaml hot-reload still propagates within the window or on
 * refocus.
 */
export function useUIConfig() {
  return useQuery({
    queryKey: ["ui-config"],
    queryFn: fetchUIConfig,
    staleTime: 60_000,
    retry: 1,
  });
}
