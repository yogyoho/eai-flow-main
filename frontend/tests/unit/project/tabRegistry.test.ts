import { describe, it, expect } from "vitest";

import type { ProjectPermissions } from "@/extensions/project/types";
import { getVisibleTabs, createProjectIdentity, TAB_REGISTRY } from "@/extensions/project/tabRegistry";

// Helper to create identity from partial permissions
function makeIdentity(overrides: Partial<ProjectPermissions> = {}) {
  return createProjectIdentity({
    role: overrides.role ?? "member",
    permissions: overrides.permissions ?? [],
    phaseDuties: overrides.phaseDuties ?? null,
    isAdmin: overrides.isAdmin ?? false,
  });
}

describe("tabRegistry", () => {
  describe("createProjectIdentity", () => {
    it("creates identity from admin permissions", () => {
      const ctx = makeIdentity({ role: "owner", isAdmin: true });
      expect(ctx.isAdmin).toBe(true);
      expect(ctx.projectRole).toBe("owner");
    });

    it("hasAnyPermission returns true for admin", () => {
      const ctx = makeIdentity({ isAdmin: true, permissions: [] });
      expect(ctx.hasAnyPermission(["anything"])).toBe(true);
    });

    it("hasAnyPermission returns false for member without perms", () => {
      const ctx = makeIdentity({ permissions: [] });
      expect(ctx.hasAnyPermission(["chapter:write_own"])).toBe(false);
    });

    it("hasAnyPermission returns true when permission exists", () => {
      const ctx = makeIdentity({ permissions: ["chapter:write_own", "approval:review"] });
      expect(ctx.hasAnyPermission(["chapter:write_own"])).toBe(true);
      expect(ctx.hasAnyPermission(["settings:edit"])).toBe(false);
    });

    it("hasAnyDuty returns true when duty matches", () => {
      const ctx = makeIdentity({
        permissions: [],
        phaseDuties: { "phase-a": { duty: "lead" }, "chapter-1": { duty: "writer" } },
      });
      expect(ctx.hasAnyDuty(["lead"])).toBe(true);
      expect(ctx.hasAnyDuty(["writer"])).toBe(true);
      expect(ctx.hasAnyDuty(["reviewer"])).toBe(false);
    });

    it("hasAnyDuty returns false when no phase duties", () => {
      const ctx = makeIdentity({ permissions: [], phaseDuties: null });
      expect(ctx.hasAnyDuty(["lead"])).toBe(false);
    });
  });

  describe("getVisibleTabs", () => {
    it("admin sees all tabs", () => {
      const ctx = makeIdentity({ isAdmin: true });
      const tabs = getVisibleTabs(ctx);
      const ids = tabs.map((t) => t.id);
      expect(ids).toContain("settings");
      expect(ids).toContain("workflow");
      expect(ids).toContain("review");
      expect(ids.length).toBe(TAB_REGISTRY.length);
    });

    it("owner sees all tabs", () => {
      const ctx = makeIdentity({ role: "owner", isAdmin: true });
      const tabs = getVisibleTabs(ctx);
      expect(tabs.length).toBe(TAB_REGISTRY.length);
    });

    it("writer member does not see settings or workflow", () => {
      const ctx = makeIdentity({
        role: "member",
        permissions: ["chapter:write_own"],
        phaseDuties: { "chapter-1": { duty: "writer" } },
      });
      const tabs = getVisibleTabs(ctx);
      const ids = tabs.map((t) => t.id);
      expect(ids).not.toContain("settings");
      expect(ids).not.toContain("workflow");
      expect(ids).toContain("editor"); // has chapter:write_own
    });

    it("reviewer member sees review tab", () => {
      const ctx = makeIdentity({
        role: "member",
        permissions: ["approval:review", "approval:view"],
      });
      const tabs = getVisibleTabs(ctx);
      const ids = tabs.map((t) => t.id);
      expect(ids).toContain("review");
      expect(ids).toContain("editor"); // approval:review triggers editor
      expect(ids).not.toContain("settings");
    });

    it("member with no permissions still sees overview, traceability, history", () => {
      const ctx = makeIdentity({ role: "member", permissions: [] });
      const tabs = getVisibleTabs(ctx);
      const ids = tabs.map((t) => t.id);
      expect(ids).toContain("overview");
      expect(ids).toContain("traceability");
      expect(ids).toContain("history");
      // Should NOT see workflow, editor, review, settings
      expect(ids).not.toContain("workflow");
      expect(ids).not.toContain("editor");
      expect(ids).not.toContain("review");
      expect(ids).not.toContain("settings");
    });

    it("phase lead gets workflow tab via member:add permission", () => {
      const ctx = makeIdentity({
        role: "member",
        permissions: ["chapter:write_own", "member:add", "outline:edit", "ai:start_writing"],
        phaseDuties: { "phase-a": { duty: "lead" } },
      });
      const tabs = getVisibleTabs(ctx);
      const ids = tabs.map((t) => t.id);
      expect(ids).toContain("workflow");
      expect(ids).toContain("settings"); // member:add triggers settings
    });

    it("tabs are sorted by order", () => {
      const ctx = makeIdentity({ isAdmin: true });
      const tabs = getVisibleTabs(ctx);
      for (let i = 1; i < tabs.length; i++) {
        expect(tabs[i]!.order).toBeGreaterThanOrEqual(tabs[i - 1]!.order);
      }
    });

    it("always has at least 3 tabs (overview, traceability, history)", () => {
      const ctx = makeIdentity({ role: "member", permissions: [], phaseDuties: null });
      const tabs = getVisibleTabs(ctx);
      expect(tabs.length).toBeGreaterThanOrEqual(3);
    });
  });
});
