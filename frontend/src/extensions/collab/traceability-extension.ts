/**
 * ProseMirror plugin for inline traceability decorations.
 *
 * Scans document text for ``[N]`` footnote markers (where N is an integer),
 * looks up source metadata, and applies inline decorations:
 *   - Coloured background based on source_type
 *   - Superscript rendering of the marker number
 *   - Hover tooltip showing source details (via native ``title`` attribute)
 *
 * Integration
 * -----------
 * 1. Import { traceabilityPluginKey, registerTraceabilityPlugin, updateTraceabilitySources }.
 * 2. In a useEffect after the BlockNote editor mounts, access the underlying
 *    ProseMirror EditorView via ``(editor as any)._tiptapEditor?.view`` and
 *    call ``registerTraceabilityPlugin(view)`` once.
 * 3. Fetch source data from the workflow API and call
 *    ``updateTraceabilitySources(view, sources)`` whenever the chapter
 *    changes or sources are refreshed.
 */

import type { Node } from "prosemirror-model";
import { Plugin, PluginKey } from "prosemirror-state";
import { Decoration, DecorationSet } from "prosemirror-view";
import type { EditorView } from "prosemirror-view";

// ---------------------------------------------------------------------------
// Source data types
// ---------------------------------------------------------------------------

export interface TraceabilitySource {
  /** 1-based footnote index matching ``[N]`` in the text. */
  index: number;
  sourceType: string;
  sourceRef: string;
  snippet: string | null;
  confidence: number | null;
}

interface PluginState {
  decorations: DecorationSet;
  sources: Map<number, TraceabilitySource>;
}

// ---------------------------------------------------------------------------
// Colour palette per source type (matching SourceAnnotation.tsx)
// ---------------------------------------------------------------------------

const TYPE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  rag_retrieval: { bg: "#dbeafe", border: "#3b82f6", text: "#1e40af" },
  knowledge_base: { bg: "#eff6ff", border: "#93c5fd", text: "#1e3a5f" },
  regulation: { bg: "#dcfce7", border: "#22c55e", text: "#166534" },
  ai_generated: { bg: "#fef3c7", border: "#f59e0b", text: "#92400e" },
  human_written: { bg: "#f3e8ff", border: "#a855f7", text: "#6b21a8" },
  template: { bg: "#f3f4f6", border: "#9ca3af", text: "#4b5563" },
  external_data: { bg: "#cffafe", border: "#06b6d4", text: "#155e75" },
};

const DEFAULT_COLOR = { bg: "#f3f4f6", border: "#9ca3af", text: "#4b5563" };

// ---------------------------------------------------------------------------
// Plugin key
// ---------------------------------------------------------------------------

export const traceabilityPluginKey = new PluginKey<PluginState>(
  "traceability",
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Regex matching ``[N]`` markers where N is one or more digits. */
const MARKER_RE = /\[(\d+)\]/g;

/**
 * Walk the ProseMirror document and build a DecorationSet that wraps every
 * ``[N]`` marker whose index is present in *sources*.
 */
function buildDecorations(
  doc: Node,
  sources: Map<number, TraceabilitySource>,
): DecorationSet {
  const decorations: Decoration[] = [];

  doc.descendants((node, pos) => {
    if (!node.isText) return;

    const text = node.text ?? "";
    let match: RegExpExecArray | null;
    MARKER_RE.lastIndex = 0; // reset regex for each text node

    while ((match = MARKER_RE.exec(text)) !== null) {
      const idx = Number(match[1]);
      if (!sources.has(idx)) continue;

      const from = pos + match.index;
      const to = from + match[0].length;
      const source = sources.get(idx)!;
      const colors = TYPE_COLORS[source.sourceType] ?? DEFAULT_COLOR;

      const tooltipLines = [
        `${source.sourceType}: ${source.sourceRef.slice(0, 80)}`,
        source.snippet ? `"${source.snippet.slice(0, 120)}"` : null,
        source.confidence !== null
          ? `置信度: ${(source.confidence * 100).toFixed(0)}%`
          : null,
      ].filter(Boolean);

      decorations.push(
        Decoration.inline(from, to, {
          style: [
            `background-color: ${colors.bg}`,
            `border-bottom: 2px solid ${colors.border}`,
            `color: ${colors.text}`,
            "border-radius: 2px",
            "padding: 0 1px",
            "cursor: help",
            "font-size: 0.75em",
            "vertical-align: super",
          ].join("; "),
          title: tooltipLines.join("\n"),
        }),
      );
    }
  });

  return DecorationSet.create(doc, decorations);
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

export const traceabilityPlugin = new Plugin<PluginState>({
  key: traceabilityPluginKey,

  state: {
    init(): PluginState {
      return {
        decorations: DecorationSet.empty,
        sources: new Map(),
      };
    },

    apply(tr, prevState): PluginState {
      const meta = tr.getMeta(traceabilityPluginKey) as
        | { sources: Map<number, TraceabilitySource> }
        | undefined;

      if (meta?.sources) {
        return {
          decorations: buildDecorations(tr.doc, meta.sources),
          sources: meta.sources,
        };
      }

      if (tr.docChanged) {
        return {
          decorations: buildDecorations(tr.doc, prevState.sources),
          sources: prevState.sources,
        };
      }

      return prevState;
    },
  },

  props: {
    decorations(state): DecorationSet {
      const pluginState = traceabilityPluginKey.getState(state);
      return pluginState?.decorations ?? DecorationSet.empty;
    },
  },
});

// ---------------------------------------------------------------------------
// Public API for React integration
// ---------------------------------------------------------------------------

let _pluginRegistered = false;

/**
 * Register the traceability plugin on the ProseMirror EditorView.
 * Idempotent — safe to call on every render.
 */
export function registerTraceabilityPlugin(view: EditorView): void {
  if (_pluginRegistered) return;

  try {
    const newState = view.state.reconfigure({
      plugins: [...view.state.plugins, traceabilityPlugin],
    });
    view.updateState(newState);
    _pluginRegistered = true;
  } catch {
    // Plugin may already be registered; ignore silently.
    _pluginRegistered = true;
  }
}

/**
 * Push source metadata into the plugin state so that decorations are
 * rebuilt for the current document.  Call this from React whenever the
 * traceability data for the active chapter changes.
 */
export function updateTraceabilitySources(
  view: EditorView,
  sources: TraceabilitySource[],
): void {
  const sourceMap = new Map<number, TraceabilitySource>();
  for (const s of sources) {
    sourceMap.set(s.index, s);
  }

  const tr = view.state.tr.setMeta(traceabilityPluginKey, {
    sources: sourceMap,
  });
  view.dispatch(tr);
}
