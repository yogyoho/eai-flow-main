import { afterEach, beforeEach, describe, expect, it } from "@rstest/core";

import { STEP_BACK } from "@/extensions/bid-write/copy";
import {
  continueHref,
  continueLabel,
  effectiveWriteTaskId,
  lastVisitedPage,
  PAGE_LABELS,
  rememberTaskPage,
  WRITE_PAGE_PATHS,
} from "@/extensions/bid-write/nav";
import type { WriteTaskOut } from "@/extensions/bid-write/types";

const originalStorage = Object.getOwnPropertyDescriptor(
  globalThis,
  "localStorage",
);

function installStorage(
  behavior: "map" | "throw" = "map",
): Map<string, string> {
  const storageMap = new Map<string, string>();
  const localStorage: Storage = {
    get length() {
      return storageMap.size;
    },
    clear: () => storageMap.clear(),
    getItem: (key) =>
      behavior === "throw"
        ? (() => {
            throw new Error("localStorage is disabled");
          })()
        : (storageMap.get(key) ?? null),
    key: (index) => Array.from(storageMap.keys())[index] ?? null,
    removeItem: (key) => {
      if (behavior === "throw") {
        throw new Error("localStorage is disabled");
      }
      storageMap.delete(key);
    },
    setItem: (key, value) => {
      if (behavior === "throw") {
        throw new Error("localStorage is disabled");
      }
      storageMap.set(key, value);
    },
  };

  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: localStorage,
  });
  return storageMap;
}

function writeTasks(ids: string[]): WriteTaskOut[] {
  return ids.map(
    (id) =>
      ({
        id,
        status: "created",
      }) as WriteTaskOut,
  );
}

function writeTask(id: string, status: string): WriteTaskOut {
  return {
    id,
    status,
  } as WriteTaskOut;
}

describe("bid-write nav task memory", () => {
  beforeEach(() => {
    installStorage();
  });

  afterEach(() => {
    if (originalStorage) {
      Object.defineProperty(globalThis, "localStorage", originalStorage);
    } else {
      Reflect.deleteProperty(globalThis, "localStorage");
    }
  });

  it("requested task id wins when it exists", () => {
    installStorage().set("bw-last-task", "task-a");

    expect(effectiveWriteTaskId(writeTasks(["task-a", "task-b"]), "task-b"))
      .toBe("task-b");
  });

  it("falls back to remembered task when request is invalid", () => {
    installStorage().set("bw-last-task", "task-a");

    expect(effectiveWriteTaskId(writeTasks(["task-a", "task-b"]), "missing"))
      .toBe("task-a");
  });

  it("falls back to the first task when request and memory are invalid", () => {
    installStorage().set("bw-last-task", "missing");

    expect(effectiveWriteTaskId(writeTasks(["task-a", "task-b"]), null)).toBe(
      "task-a",
    );
  });

  it("falls back to the first task when storage access throws", () => {
    installStorage("throw");

    expect(effectiveWriteTaskId(writeTasks(["task-a"]), null)).toBe("task-a");
  });

  it("records and reads the last visited task page", () => {
    const storageMap = installStorage();
    storageMap.set("bw-last-task", "missing");

    expect(lastVisitedPage("task-a")).toBeNull();
    rememberTaskPage("task-a", "workbench");
    expect(storageMap.get("bw-task-page:task-a")).toBe("workbench");
    expect(storageMap.get("bw-last-task")).toBe("task-a");
    expect(lastVisitedPage("task-a")).toBe("workbench");
  });

  it("returns null before the page is remembered", () => {
    installStorage();

    expect(lastVisitedPage("task-a")).toBeNull();
  });

  it("stays silent when localStorage is unavailable", () => {
    installStorage("throw");

    expect(lastVisitedPage("task-a")).toBeNull();
    expect(() => rememberTaskPage("task-a", "workbench")).not.toThrow();
  });

  it("ignores remembered page values outside the page registry", () => {
    installStorage().set("bw-task-page:task-a", "not-a-page");

    expect(lastVisitedPage("task-a")).toBeNull();
  });
});

describe("bid-write project continue nav", () => {
  beforeEach(() => {
    installStorage();
  });

  afterEach(() => {
    if (originalStorage) {
      Object.defineProperty(globalThis, "localStorage", originalStorage);
    } else {
      Reflect.deleteProperty(globalThis, "localStorage");
    }
  });

  it("resumes a matrix-ready task from its remembered page", () => {
    const task = writeTask("task-a", "matrix_ready");
    installStorage().set("bw-task-page:task-a", "workbench");

    expect(continueHref(task)).toBe("/bid-write/workbench?task_id=task-a");
    expect(continueLabel(task)).toBe("继续：写作工作台");
  });

  it("labels an intake memory as a resumable step", () => {
    const task = writeTask("task-a", "matrix_ready");
    installStorage().set("bw-task-page:task-a", "intake");

    expect(continueHref(task)).toBe("/bid-write/intake?task_id=task-a");
    expect(continueLabel(task)).toBe("继续：解析确认");
  });

  it("sends a matrix-ready task without memory to intake", () => {
    const task = writeTask("task-a", "matrix_ready");

    expect(continueHref(task)).toBe("/bid-write/intake?task_id=task-a");
    expect(continueLabel(task)).toBe("进入解析确认");
  });

  it("sends a failed task to its failure reason", () => {
    const task = writeTask("task-a", "failed");

    expect(continueHref(task)).toBe("/bid-write/intake?task_id=task-a");
    expect(continueLabel(task)).toBe("查看失败原因");
  });

  it("shows progress for in-flight statuses", () => {
    for (const status of ["created", "parsing", "extracting"]) {
      const task = writeTask("task-a", status);

      expect(continueHref(task)).toBe("/bid-write/intake?task_id=task-a");
      expect(continueLabel(task)).toBe("查看进度");
    }
  });

  it("maps every registered write page to its user-facing name", () => {
    expect(PAGE_LABELS).toEqual({
      projects: "项目列表",
      intake: "解析确认",
      materials: "素材核对",
      materials_library: "资质素材库",
      generate: "生成配置",
      workbench: "写作工作台",
      review: "预审查",
      export: "导出适配",
      registry: "质量规则中心",
    });
    expect(Object.keys(PAGE_LABELS)).toEqual(Object.keys(WRITE_PAGE_PATHS));
  });
});

describe("bid-write page step-back nav", () => {
  it("maps each main-flow page to its previous page and omits entry pages", () => {
    expect(STEP_BACK).toEqual({
      materials: "intake",
      generate: "materials",
      workbench: "generate",
      review: "workbench",
      export: "review",
    });
    expect(Object.hasOwn(STEP_BACK, "projects")).toBe(false);
    expect(Object.hasOwn(STEP_BACK, "intake")).toBe(false);
  });
});
