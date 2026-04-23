import { expect, test } from "vitest";

import { getSlashMenuViewportPosition } from "@/extensions/docmgr/utils/slashMenuPosition";

test("keeps the slash menu below the cursor when there is enough space", () => {
  expect(
    getSlashMenuViewportPosition(
      { top: 120, left: 160 },
      { width: 320, height: 240 },
      { width: 1280, height: 900 }
    )
  ).toEqual({ top: 120, left: 160 });
});

test("moves the slash menu upward when the bottom viewport space is insufficient", () => {
  expect(
    getSlashMenuViewportPosition(
      { top: 760, left: 160 },
      { width: 320, height: 240 },
      { width: 1280, height: 900 }
    )
  ).toEqual({ top: 504, left: 160 });
});

test("clamps the slash menu horizontally when it would overflow the viewport", () => {
  expect(
    getSlashMenuViewportPosition(
      { top: 120, left: 1180 },
      { width: 320, height: 240 },
      { width: 1280, height: 900 }
    )
  ).toEqual({ top: 120, left: 948 });
});
