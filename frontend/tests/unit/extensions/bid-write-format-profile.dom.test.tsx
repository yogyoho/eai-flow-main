import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";

const calls: string[] = [];

const emptyResponse = {
  profile: null,
  profile_hash: "",
  schema_version: "",
  source: null,
  updated_at: null,
};

const profileResponse = {
  profile: {
    supported: true,
    schema_version: "1.0.0",
    source: { name: "招标文件.docx", kind: "docx", sha256: "a".repeat(64) },
    format_section: {
      detected: true,
      chapter_count: 9,
      toc_entry_count: 9,
      heading_count: 26,
      chapter_titles: ["一  投标函", "二  投标保证金", "三  投标一览表"],
    },
    gap_report: {
      summary: {
        table_count: 8,
        merged_table_count: 7,
        placeholder_count: 41,
        fixed_text_count: 51,
        signature_count: 32,
        image_slot_count: 12,
      },
      capabilities: [
        {
          id: "chapter_structure",
          label: "招标章节结构与顺序",
          tender_demand: "目录 9 项",
          current_support: "products_to_ast 固定四章节",
          status: "partial",
          evidence: [],
        },
      ],
      blocking_gaps: ["chapter_structure"],
      blocking_reasons: { chapter_structure: "products_to_ast 固定四章节" },
      note: "P0 只做格式档案与差距清单。",
    },
    profile_hash: "b".repeat(64),
  },
  profile_hash: "b".repeat(64),
  schema_version: "1.0.0",
  source: { name: "招标文件.docx", kind: "docx", sha256: "a".repeat(64) },
  updated_at: "2026-11-15T02:00:00Z",
};

let currentResponse: typeof emptyResponse | typeof profileResponse =
  emptyResponse;

rs.mock("@/extensions/bid-write/api", () => ({
  getFormatProfile: async (taskId: string) => {
    calls.push(`get:${taskId}`);
    return currentResponse;
  },
  extractFormatProfile: async (taskId: string) => {
    calls.push(`extract:${taskId}`);
    currentResponse = profileResponse;
    return profileResponse;
  },
}));

import { FormatProfileCard } from "@/extensions/bid-write/components/FormatProfileCard";

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => {
  cleanup();
  calls.length = 0;
  currentResponse = emptyResponse;
});

describe("FormatProfileCard", () => {
  it("renders extracted chapters, stats and blocking gaps", async () => {
    currentResponse = profileResponse;
    render(<FormatProfileCard taskId="t1" />, { wrapper });

    expect(await screen.findByText("招标商务卷格式档案")).toBeTruthy();
    expect(await screen.findByText("商务卷章节")).toBeTruthy();
    expect(await screen.findByText(/一\s+投标函/)).toBeTruthy();
    expect(await screen.findByText("招标章节结构与顺序")).toBeTruthy();
    expect(await screen.findByText("1 项能力差距")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重新提取" })).toBeTruthy();
    expect(calls).toContain("get:t1");
  });

  it("starts empty and extracts on demand", async () => {
    render(<FormatProfileCard taskId="t1" />, { wrapper });

    expect(await screen.findByText("尚未提取格式档案")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "提取格式档案" }));

    expect(await screen.findByText("商务卷章节")).toBeTruthy();
    expect(
      await screen.findByRole("button", { name: "重新提取" }),
    ).toBeTruthy();
    expect(calls).toContain("extract:t1");
  });
});
