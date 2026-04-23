import type { Range } from "@tiptap/react";
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";

export const SlashCommandPluginKey = new PluginKey("slashCommand");

export interface SlashCommandPluginState {
  active: boolean;
  query: string;
  range: Range | null;
}

export interface SlashCommandOptions {
  onActivate: (state: SlashCommandPluginState) => void;
}

export const SlashCommand = Extension.create<SlashCommandOptions>({
  name: "slashCommand",

  addOptions() {
    return {
      onActivate: () => {},
    };
  },

  addProseMirrorPlugins() {
    const extensionThis = this;

    return [
      new Plugin({
        key: SlashCommandPluginKey,

        state: {
          init(): SlashCommandPluginState {
            return { active: false, query: "", range: null };
          },

          apply(tr, prev): SlashCommandPluginState {
            const meta = tr.getMeta(SlashCommandPluginKey);
            if (meta) return meta;
            return prev;
          },
        },

        props: {
          handleKeyDown(view, event) {
            const pluginState = SlashCommandPluginKey.getState(view.state) as SlashCommandPluginState | undefined;

            if (event.key === "Escape" && pluginState?.active) {
              extensionThis.options.onActivate({
                active: false,
                query: "",
                range: null,
              });
              const tr = view.state.tr.setMeta(SlashCommandPluginKey, {
                active: false,
                query: "",
                range: null,
              });
              view.dispatch(tr);
              return true;
            }

            if (!pluginState?.active) {
              if (event.key === "/") {
                const { state } = view;
                const tr = state.tr.setMeta(SlashCommandPluginKey, {
                  active: true,
                  query: "",
                  range: {
                    from: state.selection.from,
                    to: state.selection.to,
                  },
                });
                view.dispatch(tr);
                // Insert the "/" character ourselves
                const insertTr = view.state.tr.insertText("/", state.selection.from);
                view.dispatch(insertTr);
                extensionThis.options.onActivate({
                  active: true,
                  query: "",
                  range: {
                    from: state.selection.from,
                    to: state.selection.to + 1,
                  },
                });
                return true;
              }
              return false;
            }

            if (event.key === "Backspace") {
              if (pluginState.query.length === 0) {
                extensionThis.options.onActivate({
                  active: false,
                  query: "",
                  range: null,
                });
                const tr = view.state.tr.setMeta(SlashCommandPluginKey, {
                  active: false,
                  query: "",
                  range: null,
                });
                view.dispatch(tr);
                return false;
              }
              const newQuery = pluginState.query.slice(0, -1);
              const tr = view.state.tr.setMeta(SlashCommandPluginKey, {
                active: true,
                query: newQuery,
                range: pluginState.range,
              });
              view.dispatch(tr);
              extensionThis.options.onActivate({
                active: true,
                query: newQuery,
                range: pluginState.range,
              });
              return false;
            }

            if (event.key === " " && pluginState.query === "") {
              extensionThis.options.onActivate({
                active: false,
                query: "",
                range: null,
              });
              const tr = view.state.tr.setMeta(SlashCommandPluginKey, {
                active: false,
                query: "",
                range: null,
              });
              view.dispatch(tr);
              return false;
            }

            return false;
          },

          handleTextInput(view, from, to, text) {
            const pluginState = SlashCommandPluginKey.getState(view.state) as SlashCommandPluginState | undefined;
            if (!pluginState?.active) return false;

            const newQuery = pluginState.query + text;
            extensionThis.options.onActivate({
              active: true,
              query: newQuery,
              range: pluginState.range,
            });

            const { state } = view;
            const tr = state.tr.setMeta(SlashCommandPluginKey, {
              active: true,
              query: newQuery,
              range: pluginState.range,
            });
            view.dispatch(tr);

            return false;
          },

          handleClick(view) {
            const pluginState = SlashCommandPluginKey.getState(view.state) as SlashCommandPluginState | undefined;
            if (pluginState?.active) {
              extensionThis.options.onActivate({
                active: false,
                query: "",
                range: null,
              });
            }
            return false;
          },
        },
      }),
    ];
  },
});
