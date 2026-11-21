import { afterEach, beforeEach, describe, expect, it } from "@rstest/core";

import {
  effectiveWriteTaskId,
  lastVisitedPage,
  rememberTaskPage,
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
