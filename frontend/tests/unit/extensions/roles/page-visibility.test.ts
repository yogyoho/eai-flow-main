import { describe, expect, it } from "vitest";

import { allPageIds, isSinglePageModule, resolveVisiblePages, serializePages, shouldHideModule } from "@/extensions/role/pageVisibility";
import type { RegistryModule } from "@/extensions/types";

const mods: RegistryModule[] = [
  { key: "knowledge_factory", display_name: "知识工厂", pages: [
    { id: "kf:page:sample", display_name: "样例管理", operations: [] },
    { id: "kf:page:law", display_name: "法规标准", operations: [] },
  ], permissions: [], data_scopes: [] },
];

const singlePageMod: RegistryModule = {
  key: "dashboard", display_name: "工作台",
  pages: [{ id: "dashboard:page:overview", display_name: "工作台概览", operations: [{ id: "dashboard:view", display_name: "查看工作台" }] }],
  permissions: [], data_scopes: [],
};

const emptyMod: RegistryModule = { key: "app_center", display_name: "应用中心", pages: [], permissions: [], data_scopes: [] };

describe("page visibility helpers", () => {
  it("allPageIds collects page ids", () => {
    expect(allPageIds(mods)).toEqual(["kf:page:sample", "kf:page:law"]);
  });
  it("* or missing → all visible", () => {
    expect(resolveVisiblePages(mods, ["*"])).toEqual(new Set(["kf:page:sample", "kf:page:law"]));
    expect(resolveVisiblePages(mods, undefined)).toEqual(new Set(["kf:page:sample", "kf:page:law"]));
  });
  it("[] (explicit none) → empty set (all hidden, matches runtime canPage)", () => {
    expect(resolveVisiblePages(mods, [])).toEqual(new Set());
  });
  it("wildcard with extras → all (wildcard short-circuits)", () => {
    expect(resolveVisiblePages(mods, ["*", "bogus"])).toEqual(new Set(["kf:page:sample", "kf:page:law"]));
  });
  it("explicit list → that set (unknown ids dropped)", () => {
    expect(resolveVisiblePages(mods, ["kf:page:law", "bogus"])).toEqual(new Set(["kf:page:law"]));
  });
  it("serializePages → * when all visible, else explicit", () => {
    expect(serializePages(new Set(["kf:page:sample", "kf:page:law"]), mods)).toEqual(["*"]);
    expect(serializePages(new Set(["kf:page:law"]), mods)).toEqual(["kf:page:law"]);
  });
  it("serializePages empty set → [] (none visible)", () => {
    expect(serializePages(new Set(), mods)).toEqual([]);
  });
});

describe("single-page fold + hidden modules", () => {
  it("module with exactly 1 page folds to 2 levels", () => {
    expect(isSinglePageModule(singlePageMod)).toBe(true);
  });
  it("module with 0 or 2+ pages does not fold", () => {
    expect(isSinglePageModule(emptyMod)).toBe(false);
    expect(isSinglePageModule(mods[0])).toBe(false);
  });
  it("module with no pages (app_center) is hidden", () => {
    expect(shouldHideModule(emptyMod)).toBe(true);
  });
  it("module with pages is not hidden", () => {
    expect(shouldHideModule(singlePageMod)).toBe(false);
    expect(shouldHideModule(mods[0])).toBe(false);
  });
});
