import { describe, expect, it } from "vitest";

import { sortSourcesByScore } from "@/app/knowledge/_components/sources-sort";

describe("sortSourcesByScore", () => {
  it("sorts by score descending, missing scores last (stable)", () => {
    const srcs = [
      { content: "a", score: 0.1 },
      { content: "b", score: 0.9 },
      { content: "c" },
      { content: "d", score: 0.5 },
    ];
    const out = sortSourcesByScore(srcs);
    expect(out.map((s) => s.content)).toEqual(["b", "d", "a", "c"]);
  });

  it("does not mutate input", () => {
    const srcs = [{ content: "a", score: 0.1 }, { content: "b", score: 0.9 }];
    sortSourcesByScore(srcs);
    expect(srcs.map((s) => s.content)).toEqual(["a", "b"]);
  });
});
