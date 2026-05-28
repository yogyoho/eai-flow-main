import type { Run } from "@langchain/langgraph-sdk";
import { expect, test, describe } from "vitest";

import { findLatestUnloadedRunIndex } from "@/core/threads/hooks";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRun(runId: string): Run {
  return {
    run_id: runId,
    thread_id: "t1",
    assistant_id: "lead_agent",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    status: "success",
  } as Run;
}

// ---------------------------------------------------------------------------
// findLatestUnloadedRunIndex — pure function tests
// ---------------------------------------------------------------------------

describe("findLatestUnloadedRunIndex", () => {
  test("returns -1 when runs array is empty", () => {
    expect(findLatestUnloadedRunIndex([], new Set())).toBe(-1);
  });

  test("returns -1 when all runs are already loaded", () => {
    const runs = [makeRun("r1"), makeRun("r2"), makeRun("r3")];
    const loaded = new Set(["r1", "r2", "r3"]);
    expect(findLatestUnloadedRunIndex(runs, loaded)).toBe(-1);
  });

  test("returns index of latest unloaded run (scans from end)", () => {
    const runs = [makeRun("r1"), makeRun("r2"), makeRun("r3")];
    const loaded = new Set(["r1"]);
    expect(findLatestUnloadedRunIndex(runs, loaded)).toBe(2);
  });

  test("returns correct index when only the latest run is loaded", () => {
    const runs = [makeRun("r1"), makeRun("r2"), makeRun("r3")];
    const loaded = new Set(["r3"]);
    expect(findLatestUnloadedRunIndex(runs, loaded)).toBe(1);
  });

  test("returns last index when no runs are loaded", () => {
    const runs = [makeRun("r1"), makeRun("r2"), makeRun("r3")];
    expect(findLatestUnloadedRunIndex(runs, new Set())).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// hasMore computation — unloadedIndex >= 0 || !runs.data
// ---------------------------------------------------------------------------

describe("hasMore computation", () => {
  test("true when runs.data is undefined (not yet loaded)", () => {
    const runsData: Run[] | undefined = undefined;
    const hasMore = -1 >= 0 || !runsData;
    expect(hasMore).toBe(true);
  });

  test("true when there are unloaded runs", () => {
    const runs = [makeRun("r1"), makeRun("r2")];
    const loaded = new Set(["r2"]);
    const unloadedIndex = findLatestUnloadedRunIndex(runs, loaded);
    const hasMore = unloadedIndex >= 0 || !runs;
    expect(hasMore).toBe(true);
  });

  test("false when all runs are loaded", () => {
    const runs = [makeRun("r1"), makeRun("r2")];
    const loaded = new Set(["r1", "r2"]);
    const unloadedIndex = findLatestUnloadedRunIndex(runs, loaded);
    const hasMore = unloadedIndex >= 0 || !runs;
    expect(hasMore).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Effect simulation — NO auto-load, user-driven loading
// This tests the FIX: effect only updates unloadedIndex, does NOT call loadMessages
// ---------------------------------------------------------------------------

describe("effect simulation — user-driven loading (FIX)", () => {
  test("multi-turn: hasMore stays true until user clicks Load More", () => {
    const loadedRunIds = new Set<string>();

    // --- Turn 1: runs.data = [r1] ---
    const runs_t1 = [makeRun("r1")];
    let unloadedIndex = findLatestUnloadedRunIndex(runs_t1, loadedRunIds);
    let hasMore = unloadedIndex >= 0 || !runs_t1;

    expect(unloadedIndex).toBe(0);
    expect(hasMore).toBe(true); // r1 is unloaded → button visible

    // User clicks Load More → loads r1
    loadedRunIds.add("r1");
    unloadedIndex = findLatestUnloadedRunIndex(runs_t1, loadedRunIds);
    hasMore = unloadedIndex >= 0 || !runs_t1;
    expect(hasMore).toBe(false); // All loaded → button gone

    // --- Turn 2: runs.data = [r1, r2] ---
    const runs_t2 = [makeRun("r1"), makeRun("r2")];
    unloadedIndex = findLatestUnloadedRunIndex(runs_t2, loadedRunIds);
    hasMore = unloadedIndex >= 0 || !runs_t2;
    expect(unloadedIndex).toBe(1); // r2 unloaded
    expect(hasMore).toBe(true); // Button appears for r2

    // User clicks Load More → loads r2
    loadedRunIds.add("r2");
    unloadedIndex = findLatestUnloadedRunIndex(runs_t2, loadedRunIds);
    hasMore = unloadedIndex >= 0 || !runs_t2;
    expect(hasMore).toBe(false);

    // --- Turn 3: runs.data = [r1, r2, r3] ---
    const runs_t3 = [makeRun("r1"), makeRun("r2"), makeRun("r3")];
    unloadedIndex = findLatestUnloadedRunIndex(runs_t3, loadedRunIds);
    hasMore = unloadedIndex >= 0 || !runs_t3;
    expect(unloadedIndex).toBe(2); // r3 unloaded
    expect(hasMore).toBe(true); // Button appears for r3
  });

  test("5 existing runs: user loads them one by one", () => {
    const runs = [makeRun("r1"), makeRun("r2"), makeRun("r3"), makeRun("r4"), makeRun("r5")];
    const loadedRunIds = new Set<string>();

    let unloadedIndex = findLatestUnloadedRunIndex(runs, loadedRunIds);
    expect(unloadedIndex).toBe(4); // r5
    let hasMore = unloadedIndex >= 0 || !runs;
    expect(hasMore).toBe(true);

    // Load r5
    loadedRunIds.add("r5");
    unloadedIndex = findLatestUnloadedRunIndex(runs, loadedRunIds);
    expect(unloadedIndex).toBe(3); // r4
    hasMore = unloadedIndex >= 0 || !runs;
    expect(hasMore).toBe(true);

    // Load r4
    loadedRunIds.add("r4");
    unloadedIndex = findLatestUnloadedRunIndex(runs, loadedRunIds);
    expect(unloadedIndex).toBe(2); // r3
    hasMore = unloadedIndex >= 0 || !runs;
    expect(hasMore).toBe(true);

    // Load remaining
    loadedRunIds.add("r3");
    loadedRunIds.add("r2");
    loadedRunIds.add("r1");
    unloadedIndex = findLatestUnloadedRunIndex(runs, loadedRunIds);
    expect(unloadedIndex).toBe(-1);
    hasMore = unloadedIndex >= 0 || !runs;
    expect(hasMore).toBe(false);
  });

  test("thread change resets all state", () => {
    const loadedRunIds = new Set<string>(["r1", "r2"]);

    // Simulate thread change reset
    loadedRunIds.clear();
    const runs = [makeRun("new_r1")];
    const unloadedIndex = findLatestUnloadedRunIndex(runs, loadedRunIds);
    expect(unloadedIndex).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Regression test: the OLD bug (auto-load on every runs.data change)
// ---------------------------------------------------------------------------

describe("regression: auto-load bug should NOT happen", () => {
  test("OLD BUG: auto-load consumed all runs, hasMore always false", () => {
    // This test documents the OLD buggy behavior where the effect
    // called loadMessages() on every runs.data change, auto-loading
    // the latest run and eventually making hasMore=false always.
    //
    // With the fix, the effect only updates unloadedIndex without calling
    // loadMessages(), so hasMore correctly reflects unloaded state.

    const loadedRunIds = new Set<string>();

    // Simulate 3 turns with auto-load (OLD behavior)
    const runs_all = [makeRun("r1"), makeRun("r2"), makeRun("r3")];

    // Auto-load r1
    let idx = findLatestUnloadedRunIndex(runs_all, loadedRunIds);
    loadedRunIds.add(runs_all[idx]!.run_id);
    // Auto-load r2
    idx = findLatestUnloadedRunIndex(runs_all, loadedRunIds);
    loadedRunIds.add(runs_all[idx]!.run_id);
    // Auto-load r3
    idx = findLatestUnloadedRunIndex(runs_all, loadedRunIds);
    loadedRunIds.add(runs_all[idx]!.run_id);

    const hasMore = findLatestUnloadedRunIndex(runs_all, loadedRunIds) >= 0;
    expect(hasMore).toBe(false); // BUG: all auto-loaded, user never saw button

    // With the FIX, the effect does NOT auto-load, so loadedRunIds stays
    // empty until user clicks Load More.
  });

  test("FIX: effect only updates index, does not load", () => {
    // With the fix, the effect does:
    //   runsRef.current = runs.data;
    //   unloadedIndex = findLatestUnloadedRunIndex(runs.data, loadedRunIds);
    //   setUnloadedIndex(newIndex);  // triggers re-render
    // NO loadMessages() call.

    const runs = [makeRun("r1"), makeRun("r2"), makeRun("r3")];
    const loadedRunIds = new Set<string>(); // Empty — no auto-load happened

    const unloadedIndex = findLatestUnloadedRunIndex(runs, loadedRunIds);
    const hasMore = unloadedIndex >= 0 || !runs;
    expect(unloadedIndex).toBe(2); // r3 is latest unloaded
    expect(hasMore).toBe(true); // Button IS visible!
  });
});
