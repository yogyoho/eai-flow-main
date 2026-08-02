import { describe, expect, it } from "vitest";

import { allPageIds, resolveVisiblePages, serializePages } from "@/extensions/role/pageVisibility";
import type { RegistryModule } from "@/extensions/types";

const mods: RegistryModule[] = [
  { key: "knowledge_factory", display_name: "知识工厂", pages: [
    { id: "kf:page:sample", display_name: "样例管理", operations: [] },
    { id: "kf:page:law", display_name: "法规标准", operations: [] },
  ], permissions: [], data_scopes: [] },
];

describe("page visibility helpers", () => {
  it("allPageIds collects page ids", () => {
    expect(allPageIds(mods)).toEqual(["kf:page:sample", "kf:page:law"]);
  });
  it("* or missing → all visible", () => {
    expect(resolveVisiblePages(mods, ["*"])).toEqual(new Set(["kf:page:sample", "kf:page:law"]));
    expect(resolveVisiblePages(mods, undefined)).toEqual(new Set(["kf:page:sample", "kf:page:law"]));
    expect(resolveVisiblePages(mods, [])).toEqual(new Set(["kf:page:sample", "kf:page:law"]));
  });
  it("explicit list → that set (unknown ids dropped)", () => {
    expect(resolveVisiblePages(mods, ["kf:page:law", "bogus"])).toEqual(new Set(["kf:page:law"]));
  });
  it("serializePages → * when all visible, else explicit", () => {
    expect(serializePages(new Set(["kf:page:sample", "kf:page:law"]), mods)).toEqual(["*"]);
    expect(serializePages(new Set(["kf:page:law"]), mods)).toEqual(["kf:page:law"]);
  });
});
