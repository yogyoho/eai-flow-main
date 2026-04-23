// @vitest-environment jsdom

import React, { createRef } from "react";
import { act } from "react";
import ReactDOMClient from "react-dom/client";
import { afterEach, expect, test, vi } from "vitest";

import TiptapEditor, { type TiptapEditorRef } from "@/extensions/docmgr/TiptapEditor";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
window.HTMLElement.prototype.scrollIntoView = vi.fn();
window.scrollBy = vi.fn();

function createRect(): DOMRect {
  return {
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    bottom: 1,
    right: 1,
    width: 1,
    height: 1,
    toJSON: () => ({}),
  } as DOMRect;
}

function createRectList(): DOMRectList {
  const firstRect = createRect();
  const rectList = {
    0: firstRect,
    length: 1,
    item: (index: number) => (index === 0 ? firstRect : null),
    [Symbol.iterator]: () => [firstRect][Symbol.iterator](),
  };

  return rectList as unknown as DOMRectList;
}

window.HTMLElement.prototype.getBoundingClientRect = vi.fn(createRect);
window.HTMLElement.prototype.getClientRects = vi.fn(createRectList);

if ("Range" in window) {
  window.Range.prototype.getBoundingClientRect = vi.fn(createRect);
  window.Range.prototype.getClientRects = vi.fn(createRectList);
}

if ("Text" in window) {
  (window.Text.prototype as Text & {
    getBoundingClientRect?: () => DOMRect;
    getClientRects?: () => DOMRectList;
  }).getBoundingClientRect = vi.fn(createRect);
  (window.Text.prototype as Text & {
    getBoundingClientRect?: () => DOMRect;
    getClientRects?: () => DOMRectList;
  }).getClientRects = vi.fn(createRectList);
}

let container: HTMLDivElement | null = null;
let root: ReactDOMClient.Root | null = null;

async function waitFor<T>(getValue: () => T | null, timeoutMs = 3000): Promise<T> {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const value = getValue();
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }

  throw new Error("Timed out waiting for editor to render");
}

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

test("pasting markdown renders structured blocks in the editor", async () => {
  const onChange = vi.fn();
  const editorRef = createRef<TiptapEditorRef>();

  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOMClient.createRoot(container);

  await act(async () => {
    root?.render(
      <div style={{ width: "960px", height: "720px" }}>
        <TiptapEditor ref={editorRef} initialContent="" onChange={onChange} />
      </div>
    );
  });

  const proseMirror = await waitFor(
    () => container?.querySelector(".ProseMirror") as HTMLElement | null
  );
  const editor = await waitFor(() => editorRef.current?.getEditor() ?? null);

  await act(async () => {
    editor.commands.focus("end");
  });

  const clipboardData = {
    getData: (type: string) => {
      if (type === "text/plain") return "# 标题\n- 列表";
      return "";
    },
  };

  const pasteEvent = new Event("paste", {
    bubbles: true,
    cancelable: true,
  }) as Event & { clipboardData: typeof clipboardData };

  Object.defineProperty(pasteEvent, "clipboardData", {
    value: clipboardData,
  });

  await act(async () => {
    proseMirror.dispatchEvent(pasteEvent);
    await new Promise((resolve) => setTimeout(resolve, 50));
  });

  expect(proseMirror.querySelector("h1")?.textContent).toBe("标题");
  expect(proseMirror.querySelector("ul li")?.textContent).toBe("列表");
  expect(editor.getHTML()).toContain("<h1");
  expect(editor.getHTML()).toContain("<ul");
});
