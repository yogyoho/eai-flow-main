// 批廿九 UX:DocLocateBody 段内命中摘录精确高亮(用户反馈 2026-11-18 一目了然)。
// 段级 hit 泛黄不够——<mark class="loc-hit"> 须精确圈出摘录原文(空白折叠口径)。
import { afterEach, describe, expect, it } from "@rstest/core";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import {
  type BidDocContent,
} from "@/extensions/bid-review/api";
import {
  DocLocateBody,
  locateHitRange,
} from "@/extensions/bid-review/components/DocLocateModal";

const doc: BidDocContent["doc"] = {
  doc_id: "T",
  role: "tender",
  kind: "docx",
  pages: 1,
  chars: 100,
  assets: 0,
  status: "parsed",
};

const content: BidDocContent = {
  doc,
  page: null,
  seq: 1,
  segments: [
    {
      seq: 1,
      page: null,
      kind: "text",
      text: "前文无关内容。投标人须知前附表要求缴纳保证金伍万元整,后文继续。",
      asset_id: null,
    },
    {
      seq: 2,
      page: null,
      kind: "text",
      text: "完全无命中的一段文字。",
      asset_id: null,
    },
  ],
};

// rstest 无自动 DOM 清理:共享 document,不 cleanup 会把上一例的 mark 泄进下一例
afterEach(cleanup);

describe("locateHitRange", () => {
  it("跨空白命中:折叠后子串 → 原文偏移含中间空白", () => {
    const range = locateHitRange(
      "缴纳 保证金\n伍万元整,逾期不退",
      "保证金伍万元整",
    );
    expect(range).not.toBeNull();
    const [s, e] = range!;
    expect("缴纳 保证金\n伍万元整,逾期不退".slice(s, e)).toBe(
      "保证金\n伍万元整",
    );
  });

  it("无命中返回 null(段级 hit 但逐字对上不了时如实不高亮)", () => {
    expect(locateHitRange("完全不同的文字", "保证金伍万元")).toBeNull();
    expect(locateHitRange("任意文字", "")).toBeNull();
  });
});

describe("DocLocateBody 段内高亮", () => {
  it("命中段内 <mark.loc-hit> 精确圈出摘录;未命中段无 mark", async () => {
    render(
      <DocLocateBody
        taskId="t1"
        target={{ docId: "T", page: null, quote: "保证金伍万元整" }}
        fetchContent={async () => content}
        assetUrl={() => "/asset"}
      />,
    );
    await waitFor(() =>
      expect(screen.getAllByText(/无关内容/).length).toBeGreaterThan(0),
    );
    const mark = document.querySelector("mark.loc-hit");
    if (!mark) throw new Error("命中 mark 未渲染");
    expect((mark.textContent ?? "").replace(/\s+/g, "")).toContain(
      "保证金伍万元整",
    );
    // mark 只出现在命中段内(前后是段内上下文文本)
    expect(mark.previousSibling?.textContent).toContain("要求缴纳");
    // 未命中段整体无 mark
    const segs = document.querySelectorAll(".loc-seg");
    expect(segs.length).toBe(2);
    expect(segs[1]!.querySelectorAll("mark").length).toBe(0);
    // 命中段保持段级 hit + meta 提示
    expect(segs[0]!.className).toContain("hit");
    expect(screen.getByText(/黄色高亮为命中摘录/)).toBeTruthy();
  });

  it("无 quote(页码定位)→ 不渲染任何 mark", async () => {
    render(
      <DocLocateBody
        taskId="t1"
        target={{ docId: "T", page: 3, quote: "" }}
        fetchContent={async () => content}
        assetUrl={() => "/asset"}
      />,
    );
    await waitFor(() =>
      expect(screen.getAllByText(/无关内容/).length).toBeGreaterThan(0),
    );
    expect(document.querySelectorAll("mark.loc-hit").length).toBe(0);
  });
});
