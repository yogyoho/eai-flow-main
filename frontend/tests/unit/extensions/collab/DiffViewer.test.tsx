// @vitest-environment jsdom

import { act } from "react";
import ReactDOMClient from "react-dom/client";
import { afterEach, expect, test } from "vitest";

import { DiffViewer } from "@/extensions/collab/DiffViewer";
import type { VersionDiffResponse } from "@/extensions/types";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

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

function render(element: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOMClient.createRoot(container);
  return act(async () => {
    root!.render(element);
  });
}

test("renders loading state when loading=true", async () => {
  await render(<DiffViewer diff={null} loading={true} />);

  expect(container!.textContent).toContain("加载差异对比");
});

test("renders empty state when diff=null and not loading", async () => {
  await render(<DiffViewer diff={null} loading={false} />);

  expect(container!.textContent).toContain("选择两个版本进行差异对比");
});

test("renders version arrows header with from/to version numbers", async () => {
  const diff: VersionDiffResponse = {
    from_version: 2,
    to_version: 5,
    from_summary: null,
    to_summary: null,
    from_created_at: null,
    to_created_at: null,
    diff_blocks: [],
    ai_summary: null,
  };

  await render(<DiffViewer diff={diff} loading={false} />);

  expect(container!.textContent).toContain("v2");
  expect(container!.textContent).toContain("v5");
});

test("renders AI summary when present", async () => {
  const diff: VersionDiffResponse = {
    from_version: 1,
    to_version: 2,
    from_summary: null,
    to_summary: null,
    from_created_at: null,
    to_created_at: null,
    diff_blocks: [],
    ai_summary: "AI summary of changes",
  };

  await render(<DiffViewer diff={diff} loading={false} />);

  expect(container!.textContent).toContain("AI summary of changes");
});

test("renders diff blocks with correct content", async () => {
  const diff: VersionDiffResponse = {
    from_version: 1,
    to_version: 2,
    from_summary: null,
    to_summary: null,
    from_created_at: null,
    to_created_at: null,
    diff_blocks: [
      { type: "added", content: "new line added" },
      { type: "removed", content: "old line removed" },
      { type: "changed", content: "modified line", from_content: "original", to_content: "modified line" },
    ],
    ai_summary: null,
  };

  await render(<DiffViewer diff={diff} loading={false} />);

  const html = container!.innerHTML;

  // Added block should have green background class
  expect(html).toContain("bg-green-100");
  expect(container!.textContent).toContain("+ new line added");

  // Removed block should have red background class and line-through
  expect(html).toContain("bg-red-100");
  expect(html).toContain("line-through");
  expect(container!.textContent).toContain("- old line removed");

  // Changed block should have yellow background class
  expect(html).toContain("bg-yellow-100");
  expect(container!.textContent).toContain("~ modified line");
});

test("renders 'no differences' message when diff_blocks is empty", async () => {
  const diff: VersionDiffResponse = {
    from_version: 1,
    to_version: 2,
    from_summary: null,
    to_summary: null,
    from_created_at: null,
    to_created_at: null,
    diff_blocks: [],
    ai_summary: null,
  };

  await render(<DiffViewer diff={diff} loading={false} />);

  expect(container!.textContent).toContain("两个版本无差异");
});
