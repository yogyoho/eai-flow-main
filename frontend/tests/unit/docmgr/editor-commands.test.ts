import { expect, test } from "vitest";

import { filterCommands, normalizeSlashQuery } from "@/extensions/docmgr/utils/editorCommands";

test("normalizeSlashQuery strips the trigger slash before filtering", () => {
  expect(normalizeSlashQuery("/")).toBe("");
  expect(normalizeSlashQuery("/hea")).toBe("hea");
  expect(normalizeSlashQuery("heading")).toBe("heading");
});

test("filterCommands shows all commands for a bare slash trigger", () => {
  const commands = filterCommands("/");
  expect(commands.length).toBeGreaterThan(0);
});

test("filterCommands matches commands after slash-prefixed input", () => {
  const commands = filterCommands("/1");
  expect(commands.some((command) => command.title.includes("1"))).toBe(true);
});
