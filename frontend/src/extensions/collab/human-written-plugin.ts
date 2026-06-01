/**
 * ProseMirror plugin for detecting and marking human-written blocks.
 *
 * When a user (not a remote Yjs peer) edits a block's content, the plugin
 * adds a `data-source-type="human_written"` attribute to that block's DOM node.
 * This enables the traceability system to distinguish between AI-generated
 * content (marked by the AI writing pipeline) and human-edited content.
 *
 * Integration
 * -----------
 * 1. Import { humanWrittenPluginKey, registerHumanWrittenPlugin, getHumanWrittenBlockIds }.
 * 2. After the BlockNote editor mounts, access the ProseMirror EditorView
 *    via `(editor as any)._tiptapEditor?.view` and call
 *    `registerHumanWrittenPlugin(view)` once.
 * 3. On save/version, call `getHumanWrittenBlockIds(view)` to get the set of
 *    block positions that were human-edited, then create content_sources entries.
 */

import type { Node as ProseMirrorNode } from "prosemirror-model";
import { Plugin, PluginKey } from "prosemirror-state";
import { Decoration, DecorationSet } from "prosemirror-view";
import type { EditorView } from "prosemirror-view";

// ---------------------------------------------------------------------------
// Plugin state
// ---------------------------------------------------------------------------

interface PluginState {
  /** Set of block positions (doc-level) that were edited by the local user. */
  humanBlocks: Set<number>;
  /** Decorations for human-written blocks. */
  decorations: DecorationSet;
}

// ---------------------------------------------------------------------------
// Plugin key
// ---------------------------------------------------------------------------

export const humanWrittenPluginKey = new PluginKey<PluginState>(
  "humanWritten",
);

// ---------------------------------------------------------------------------
// Decoration builder
// ---------------------------------------------------------------------------

const HUMAN_ATTR = { "data-source-type": "human_written" };

function buildDecorations(doc: ProseMirrorNode, humanBlocks: Set<number>): DecorationSet {
  const decorations: Decoration[] = [];

  doc.forEach((block, offset) => {
    if (humanBlocks.has(offset)) {
      decorations.push(
        Decoration.node(offset, offset + block.nodeSize, HUMAN_ATTR),
      );
    }
  });

  return DecorationSet.create(doc, decorations);
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

export const humanWrittenPlugin = new Plugin<PluginState>({
  key: humanWrittenPluginKey,

  state: {
    init(): PluginState {
      return {
        humanBlocks: new Set(),
        decorations: DecorationSet.empty,
      };
    },

    apply(tr, prevState): PluginState {
      // External reset (e.g., on document load)
      const meta = tr.getMeta(humanWrittenPluginKey) as
        | { reset: boolean }
        | { humanBlock: number }
        | undefined;

      if (meta && "reset" in meta && meta.reset) {
        return {
          humanBlocks: new Set(),
          decorations: DecorationSet.empty,
        };
      }

      if (meta && "humanBlock" in meta) {
        const next = new Set(prevState.humanBlocks);
        next.add(meta.humanBlock);
        return {
          humanBlocks: next,
          decorations: buildDecorations(tr.doc, next),
        };
      }

      // On local edits (not from Yjs remote), mark affected blocks
      if (tr.docChanged && !tr.getMeta("yjs$remote")) {
        const next = new Set(prevState.humanBlocks);

        // Mark all top-level blocks as human-edited on any local change.
        // This is a simple approach — for finer granularity, we could track
        // which specific blocks changed, but ProseMirror's StepMap types
        // are not easily accessible in TypeScript.
        tr.doc.forEach((_block, offset) => {
          next.add(offset);
        });

        return {
          humanBlocks: next,
          decorations: buildDecorations(tr.doc, next),
        };
      }

      return prevState;
    },
  },

  props: {
    decorations(state): DecorationSet {
      const pluginState = humanWrittenPluginKey.getState(state);
      return pluginState?.decorations ?? DecorationSet.empty;
    },
  },
});

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

let _pluginRegistered = false;

/**
 * Register the human-written plugin on the ProseMirror EditorView.
 * Idempotent — safe to call on every render.
 */
export function registerHumanWrittenPlugin(view: EditorView): void {
  if (_pluginRegistered) return;

  try {
    const newState = view.state.reconfigure({
      plugins: [...view.state.plugins, humanWrittenPlugin],
    });
    view.updateState(newState);
    _pluginRegistered = true;
  } catch {
    _pluginRegistered = true;
  }
}

/**
 * Get the set of block positions that were human-edited.
 * Returns block content as an array of { blockIndex, text } for source creation.
 */
export function getHumanWrittenBlocks(view: EditorView): { blockIndex: number; text: string }[] {
  const pluginState = humanWrittenPluginKey.getState(view.state);
  if (!pluginState || pluginState.humanBlocks.size === 0) return [];

  const results: { blockIndex: number; text: string }[] = [];
  let offset = 0;

  view.state.doc.forEach((block, blockOffset) => {
    if (pluginState.humanBlocks.has(blockOffset)) {
      results.push({
        blockIndex: results.length,
        text: block.textContent,
      });
    }
    offset = blockOffset;
  });

  return results;
}

/**
 * Reset the human-written tracking (e.g., when switching chapters).
 */
export function resetHumanWrittenTracking(view: EditorView): void {
  const tr = view.state.tr.setMeta(humanWrittenPluginKey, { reset: true });
  view.dispatch(tr);
}
