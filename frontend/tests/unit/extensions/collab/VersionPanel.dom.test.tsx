
import { afterEach, expect, rs, test } from "@rstest/core";
import { act } from "react";
import ReactDOMClient from "react-dom/client";

import { VersionPanel } from "@/extensions/collab/VersionPanel";
import type { CollabVersion, VersionDiffResponse } from "@/extensions/types";

// Mock lucide-react icons
rs.mock("lucide-react", () => ({
  Eye: () => <span data-testid="icon-eye" />,
  GitCompare: () => <span data-testid="icon-compare" />,
  History: () => <span data-testid="icon-history" />,
  Loader2: () => <span data-testid="icon-loader" />,
  RotateCcw: () => <span data-testid="icon-rotate" />,
  Save: () => <span data-testid="icon-save" />,
  Sparkles: () => <span data-testid="icon-sparkles" />,
  ArrowRight: () => <span data-testid="icon-arrow" />,
}));

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement | null = null;
let root: ReactDOMClient.Root | null = null;

const defaultVersions: CollabVersion[] = [
  {
    id: 1,
    doc_id: "doc-1",
    version: 3,
    summary: "Third revision",
    created_by: "user-1",
    created_at: "2026-05-27T10:00:00Z",
    username: "alice",
    full_name: "Alice",
  },
  {
    id: 2,
    doc_id: "doc-1",
    version: 2,
    summary: "Second revision",
    created_by: "user-2",
    created_at: "2026-05-26T10:00:00Z",
    username: "bob",
    full_name: "Bob",
  },
  {
    id: 3,
    doc_id: "doc-1",
    version: 1,
    summary: null,
    created_by: "user-1",
    created_at: "2026-05-25T10:00:00Z",
    username: "alice",
  },
];

afterEach(() => {
  if (root && container) {
    act(() => {
      root?.unmount();
    });
  }
  container?.remove();
  root = null;
  container = null;
  rs.restoreAllMocks();
});

function render(element: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOMClient.createRoot(container);
  return act(async () => {
    root!.render(element);
  });
}

function defaultProps(
  overrides: Partial<Parameters<typeof VersionPanel>[0]> = {},
) {
  return {
    versions: defaultVersions,
    loading: false,
    diffLoading: false,
    diffResult: null as VersionDiffResponse | null,
    onCreateVersion: rs.fn(),
    onRestoreVersion: rs.fn(),
    onPreviewVersion: rs.fn(),
    onDiffVersions: rs.fn(),
    onClose: rs.fn(),
    ...overrides,
  };
}

test("renders version list with version numbers", async () => {
  await render(<VersionPanel {...defaultProps()} />);

  const html = container!.innerHTML;
  expect(html).toContain("v3");
  expect(html).toContain("v2");
  expect(html).toContain("v1");
});

test("renders '保存当前版本' button", async () => {
  await render(<VersionPanel {...defaultProps()} />);

  expect(container!.textContent).toContain("保存当前版本");
});

test("renders '对比' toggle button", async () => {
  await render(<VersionPanel {...defaultProps()} />);

  expect(container!.textContent).toContain("对比");
});

test("renders '关闭' button and calls onClose", async () => {
  const onClose = rs.fn();
  await render(<VersionPanel {...defaultProps({ onClose })} />);

  const closeButtons = container!.querySelectorAll("button");
  const closeButton = Array.from(closeButtons).find(
    (b) => b.textContent === "关闭",
  );
  expect(closeButton).toBeTruthy();

  await act(async () => {
    closeButton!.click();
  });

  expect(onClose).toHaveBeenCalled();
});

test("clicking version item calls onPreviewVersion", async () => {
  const onPreviewVersion = rs.fn();
  await render(<VersionPanel {...defaultProps({ onPreviewVersion })} />);

  // Find the "预览" button for the first version (v3)
  const buttons = container!.querySelectorAll("button");
  const previewButton = Array.from(buttons).find((b) =>
    b.textContent?.includes("预览"),
  );
  expect(previewButton).toBeTruthy();

  await act(async () => {
    previewButton!.click();
  });

  expect(onPreviewVersion).toHaveBeenCalledWith(3);
});

test("shows '保存当前版本' and calls onCreateVersion", async () => {
  const onCreateVersion = rs.fn().mockResolvedValue(undefined);
  await render(<VersionPanel {...defaultProps({ onCreateVersion })} />);

  const buttons = container!.querySelectorAll("button");
  const saveButton = Array.from(buttons).find((b) =>
    b.textContent?.includes("保存当前版本"),
  );
  expect(saveButton).toBeTruthy();

  await act(async () => {
    saveButton!.click();
  });

  expect(onCreateVersion).toHaveBeenCalled();
});

test("shows empty state when no versions", async () => {
  await render(
    <VersionPanel {...defaultProps({ versions: [], loading: false })} />,
  );

  expect(container!.textContent).toContain("暂无版本记录");
});

test("shows loading state when loading with no versions", async () => {
  await render(
    <VersionPanel {...defaultProps({ versions: [], loading: true })} />,
  );

  expect(container!.textContent).toContain("加载中");
});

test("toggling diff mode shows DiffViewer", async () => {
  const diffResult: VersionDiffResponse = {
    from_version: 1,
    to_version: 2,
    from_summary: null,
    to_summary: null,
    from_created_at: null,
    to_created_at: null,
    diff_blocks: [{ type: "added", content: "new content from diff" }],
    ai_summary: null,
    legacy_notice: null,
  };

  await render(<VersionPanel {...defaultProps({ diffResult })} />);

  // Before toggling diff mode, DiffViewer content should not be visible
  expect(container!.textContent).not.toContain("new content from diff");

  // Click the diff toggle button
  const buttons = container!.querySelectorAll("button");
  const diffButton = Array.from(buttons).find((b) =>
    b.textContent?.includes("对比"),
  );
  expect(diffButton).toBeTruthy();

  await act(async () => {
    diffButton!.click();
  });

  // Now the DiffViewer should be visible with the diff result
  expect(container!.textContent).toContain("new content from diff");
});

test("in diff mode, shows checkboxes for version selection", async () => {
  await render(<VersionPanel {...defaultProps()} />);

  // EAI-CUSTOM: the "AI 生成变更摘要" checkbox is always rendered (not gated
  // by diff mode), so before diff mode there is 1 checkbox, and after diff
  // mode the per-version checkboxes follow it.
  expect(container!.querySelectorAll('input[type="checkbox"]').length).toBe(1);

  // Enable diff mode
  const buttons = container!.querySelectorAll("button");
  const diffButton = Array.from(buttons).find((b) =>
    b.textContent?.includes("对比"),
  );

  await act(async () => {
    diffButton!.click();
  });

  // Checkboxes should now appear: AI-summary + one per version
  const checkboxes = container!.querySelectorAll('input[type="checkbox"]');
  expect(checkboxes.length).toBe(4);
});

test("selecting two versions in diff mode calls onDiffVersions", async () => {
  const onDiffVersions = rs.fn().mockResolvedValue(undefined);
  await render(<VersionPanel {...defaultProps({ onDiffVersions })} />);

  // Enable diff mode
  const buttons = container!.querySelectorAll("button");
  const diffButton = Array.from(buttons).find((b) =>
    b.textContent?.includes("对比"),
  );

  await act(async () => {
    (diffButton as HTMLElement).click();
  });

  // Click the v3 + v2 version checkboxes. checkboxes[0] is the always-rendered
  // "AI 生成变更摘要" checkbox; version checkboxes follow it in version order.
  const checkboxes = container!.querySelectorAll('input[type="checkbox"]');
  await act(async () => {
    (checkboxes[1] as HTMLElement).click(); // v3
  });

  const updatedCheckboxes = container!.querySelectorAll(
    'input[type="checkbox"]',
  );
  await act(async () => {
    (updatedCheckboxes[2] as HTMLElement).click(); // v2
  });

  // onDiffVersions should be called with the two selected version numbers
  expect(onDiffVersions).toHaveBeenCalledWith(3, 2);
});

test("shows version summary when present", async () => {
  await render(<VersionPanel {...defaultProps()} />);

  expect(container!.textContent).toContain("Third revision");
  expect(container!.textContent).toContain("Second revision");
});

test("shows author name for versions", async () => {
  await render(<VersionPanel {...defaultProps()} />);

  expect(container!.textContent).toContain("Alice");
  expect(container!.textContent).toContain("Bob");
});
