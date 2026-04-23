// @vitest-environment jsdom

import { act } from "react";
import ReactDOMClient from "react-dom/client";
import { afterEach, expect, test, vi } from "vitest";

import SlashMenu from "@/extensions/docmgr/components/SlashMenu";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
window.HTMLElement.prototype.scrollIntoView = vi.fn();

let container: HTMLDivElement | null = null;
let root: ReactDOMClient.Root | null = null;

afterEach(() => {
  if (root && container) {
    act(() => {
      root?.unmount();
    });
  }

  container?.remove();
  root = null;
  container = null;
});

test("slash menu supports keyboard navigation and enter to execute a command", async () => {
  const onClose = vi.fn();
  const onCommand = vi.fn();
  const dispatch = vi.fn();
  const setMeta = vi.fn(() => ({ meta: "slash" }));
  const fakeEditor = {
    state: {
      tr: {
        setMeta,
      },
    },
    view: {
      dispatch,
    },
  } as never;

  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOMClient.createRoot(container);

  await act(async () => {
    root?.render(
      <SlashMenu
        editor={fakeEditor}
        visible
        position={{ top: 24, left: 48 }}
        query="/"
        onClose={onClose}
        onCommand={onCommand}
      />
    );
  });

  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  });

  expect(onCommand).toHaveBeenCalledTimes(1);
  expect(onClose).toHaveBeenCalled();
  expect(setMeta).not.toHaveBeenCalled();
  expect(dispatch).not.toHaveBeenCalled();
});
