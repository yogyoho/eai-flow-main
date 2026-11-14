import { describe, expect, it } from "@rstest/core";

import {
  effectiveWriteTaskId,
  writeNavBadges,
  writeTaskHref,
} from "@/extensions/bid-write/nav";
import type { WriteTaskOut } from "@/extensions/bid-write/types";

// 侧栏契约：任务链页 J 保留 task_id；徽标只读后端真实 matrix_counts；
// 未指定/失效 task_id 回退最新任务，不伪造选中项。
function task(partial: Partial<WriteTaskOut>): WriteTaskOut {
  return {
    id: "t0",
    biz_no: null,
    status: "matrix_ready",
    progress: {},
    error: null,
    project_name: "项目",
    lot_name: null,
    tender_no: null,
    created_at: "2026-11-13T00:00:00Z",
    engine_meta: {},
    ...partial,
  };
}

describe("writeTaskHref", () => {
  it("任务链页附带并编码 task_id", () => {
    expect(writeTaskHref("intake", "abc")).toBe(
      "/bid-write/intake?task_id=abc",
    );
    expect(writeTaskHref("export", "a b/c")).toBe(
      "/bid-write/export?task_id=a%20b%2Fc",
    );
  });

  it("项目列表与注册表保持裸路径", () => {
    expect(writeTaskHref("projects", "x")).toBe("/bid-write?task_id=x");
    expect(writeTaskHref("registry", "x")).toBe(
      "/bid-write/registry?task_id=x",
    );
  });
});

describe("writeNavBadges", () => {
  it("进行中计入 created/parsing/extracting，终态不计", () => {
    const badges = writeNavBadges(
      [
        task({ id: "a", status: "created" }),
        task({ id: "b", status: "parsing" }),
        task({ id: "c", status: "extracting" }),
        task({ id: "d", status: "matrix_ready" }),
        task({ id: "e", status: "failed" }),
      ],
      "d",
    );
    expect(badges.active).toBe(3);
  });

  it("阻断徽标取选中任务真实 matrix_counts；缺失按 0", () => {
    const tasks = [
      task({
        id: "a",
        engine_meta: { matrix_counts: { total: 10, star: 2, blocked: 4 } },
      }),
      task({ id: "b" }),
    ];
    expect(writeNavBadges(tasks, "a").blocked).toBe(4);
    expect(writeNavBadges(tasks, "b").blocked).toBe(0);
    expect(writeNavBadges([], null).blocked).toBe(0);
  });
});

describe("effectiveWriteTaskId", () => {
  it("URL 指定且存在时优先；否则回退首个（最新）任务", () => {
    const tasks = [task({ id: "new" }), task({ id: "old" })];
    expect(effectiveWriteTaskId(tasks, "old")).toBe("old");
    expect(effectiveWriteTaskId(tasks, "missing")).toBe("new");
    expect(effectiveWriteTaskId(tasks, null)).toBe("new");
    expect(effectiveWriteTaskId([], "x")).toBeNull();
  });
});
