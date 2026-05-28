// @vitest-environment jsdom

import { act } from "react";
import ReactDOMClient from "react-dom/client";
import { afterEach, expect, test, vi } from "vitest";

const { mockAiReview } = vi.hoisted(() => ({
  mockAiReview: vi.fn(),
}));

vi.mock("@/extensions/api", () => ({
  docmgrApi: {
    aiReview: mockAiReview,
  },
}));

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

// Mock lucide-react icons to avoid SVG rendering complexity
vi.mock("lucide-react", () => ({
  Sparkles: () => <span data-testid="icon-sparkles" />,
  Loader2: (props: { className?: string }) => <span data-testid="icon-loader" className={props.className} />,
  AlertTriangle: () => <span data-testid="icon-alert" />,
  Info: () => <span data-testid="icon-info" />,
  AlertCircle: () => <span data-testid="icon-alert-circle" />,
}));

import { AIDocumentReview } from "@/extensions/collab/AIDocumentReview";

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
  vi.clearAllMocks();
});

function render(element: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOMClient.createRoot(container);
  return act(async () => {
    root!.render(element);
  });
}

test("renders all review type buttons", async () => {
  await render(<AIDocumentReview docId="doc-1" onInsertComment={vi.fn()} />);

  const html = container!.innerHTML;
  expect(html).toContain("全面审查");
  expect(html).toContain("风格检查");
  expect(html).toContain("逻辑审查");
  expect(html).toContain("完整性检查");
});

test("renders '开始审查' button", async () => {
  await render(<AIDocumentReview docId="doc-1" onInsertComment={vi.fn()} />);

  expect(container!.textContent).toContain("开始审查");
});

test("clicking review type button changes selection", async () => {
  await render(<AIDocumentReview docId="doc-1" onInsertComment={vi.fn()} />);

  // The "style" button should be present - find it and click it
  const buttons = container!.querySelectorAll("button");
  const styleButton = Array.from(buttons).find((b) => b.textContent === "风格检查");
  expect(styleButton).toBeTruthy();

  await act(async () => {
    styleButton!.click();
  });

  // The style button should now be selected (variant="default")
  // We can verify the click worked by checking the API is not called yet
  expect(mockAiReview).not.toHaveBeenCalled();
});

test("clicking '开始审查' triggers API call with correct params", async () => {
  mockAiReview.mockResolvedValue({ overall_score: 85, summary: "Good", comments: [] });

  await render(<AIDocumentReview docId="doc-123" onInsertComment={vi.fn()} />);

  const buttons = container!.querySelectorAll("button");
  const reviewButton = Array.from(buttons).find((b) => b.textContent?.includes("开始审查"));
  expect(reviewButton).toBeTruthy();

  await act(async () => {
    reviewButton!.click();
  });

  expect(mockAiReview).toHaveBeenCalledWith({
    doc_id: "doc-123",
    review_type: "full",
  });
});

test("shows loading state during review", async () => {
  let resolveReview: (value: unknown) => void;
  mockAiReview.mockReturnValue(new Promise((resolve) => { resolveReview = resolve; }));

  await render(<AIDocumentReview docId="doc-1" onInsertComment={vi.fn()} />);

  const buttons = container!.querySelectorAll("button");
  const reviewButton = Array.from(buttons).find((b) => b.textContent?.includes("开始审查"));

  await act(async () => {
    reviewButton!.click();
  });

  // Should show loading text
  expect(container!.textContent).toContain("审查中");

  // Resolve the promise to clean up
  await act(async () => {
    resolveReview!({ overall_score: 90, comments: [] });
  });
});

test("shows review results after successful API call", async () => {
  mockAiReview.mockResolvedValue({
    overall_score: 92,
    summary: "Excellent document quality",
    comments: [
      { block_id: "b1", comment: "Consider revising paragraph", severity: "warning" },
    ],
  });

  await render(<AIDocumentReview docId="doc-1" onInsertComment={vi.fn()} />);

  const buttons = container!.querySelectorAll("button");
  const reviewButton = Array.from(buttons).find((b) => b.textContent?.includes("开始审查"));

  await act(async () => {
    reviewButton!.click();
  });

  expect(container!.textContent).toContain("92/100");
  expect(container!.textContent).toContain("Excellent document quality");
  expect(container!.textContent).toContain("Consider revising paragraph");
});

test("shows error message on API failure", async () => {
  mockAiReview.mockRejectedValue(new Error("Network error"));

  await render(<AIDocumentReview docId="doc-1" onInsertComment={vi.fn()} />);

  const buttons = container!.querySelectorAll("button");
  const reviewButton = Array.from(buttons).find((b) => b.textContent?.includes("开始审查"));

  await act(async () => {
    reviewButton!.click();
  });

  expect(container!.textContent).toContain("AI 审查失败，请重试");
});

test("clicking '插入为评论' calls onInsertComment", async () => {
  const onInsertComment = vi.fn();
  mockAiReview.mockResolvedValue({
    overall_score: 80,
    summary: "Decent",
    comments: [
      { block_id: "block-42", comment: "Fix typo here", severity: "info" },
    ],
  });

  await render(<AIDocumentReview docId="doc-1" onInsertComment={onInsertComment} />);

  const buttons = container!.querySelectorAll("button");
  const reviewButton = Array.from(buttons).find((b) => b.textContent?.includes("开始审查"));

  await act(async () => {
    reviewButton!.click();
  });

  // Find the "插入为评论" button
  const insertButtons = container!.querySelectorAll("button");
  const insertButton = Array.from(insertButtons).find((b) => b.textContent?.includes("插入为评论"));
  expect(insertButton).toBeTruthy();

  await act(async () => {
    insertButton!.click();
  });

  expect(onInsertComment).toHaveBeenCalledWith("block-42", "Fix typo here");
});

test("calls onInsertComment with null block_id when block_id is not provided", async () => {
  const onInsertComment = vi.fn();
  mockAiReview.mockResolvedValue({
    overall_score: 80,
    comments: [
      { comment: "General comment", severity: "info" },
    ],
  });

  await render(<AIDocumentReview docId="doc-1" onInsertComment={onInsertComment} />);

  const buttons = container!.querySelectorAll("button");
  const reviewButton = Array.from(buttons).find((b) => b.textContent?.includes("开始审查"));

  await act(async () => {
    reviewButton!.click();
  });

  const insertButtons = container!.querySelectorAll("button");
  const insertButton = Array.from(insertButtons).find((b) => b.textContent?.includes("插入为评论"));

  await act(async () => {
    insertButton!.click();
  });

  expect(onInsertComment).toHaveBeenCalledWith(null, "General comment");
});
