import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "@rstest/core";

const css = readFileSync(
  resolve(__dirname, "../../src/app/bid-write/bid-write.css"),
  "utf-8",
);

describe("bid-write.css anchor decoration", () => {
  it("no longer renders the template-anchor line", () => {
    expect(css.includes('content: "锁定模板 " attr(data-template-id)')).toBe(
      false,
    );
    expect(css.includes("锁定模板")).toBe(false);
  });
});
