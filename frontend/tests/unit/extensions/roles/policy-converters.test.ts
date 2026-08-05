// EAI-CUSTOM: 策略条件/授权 shape 转换器单测（UI 数组 ⇄ 引擎 dict）
import { afterEach, describe, expect, it, vi } from "vitest";

import { toEngineConditions, toGrantArray, toUIConditions } from "@/extensions/role/policyConverters";

describe("toEngineConditions (UI 数组 → 引擎 dict)", () => {
  it("空数组 → 空 dict（引擎视为无条件=全量）", () => {
    expect(toEngineConditions([])).toEqual({});
  });

  it("映射展示符 → 引擎 op（= → eq, >= → gte, != → neq）", () => {
    expect(
      toEngineConditions([
        { attribute: "role_level", operator: ">=", value: "5" },
        { attribute: "dept_id", operator: "=", value: "d1" },
        { attribute: "user_id", operator: "!=", value: "u1" },
      ]),
    ).toEqual({
      and: [
        { attr: "role_level", op: "gte", value: "5" },
        { attr: "dept_id", op: "eq", value: "d1" },
        { attr: "user_id", op: "neq", value: "u1" },
      ],
    });
  });

  it("in/not_in 值按逗号拆分并 trim 成列表", () => {
    expect(toEngineConditions([{ attribute: "tags", operator: "in", value: "a, b ,c" }])).toEqual({
      and: [{ attr: "tags", op: "in", value: ["a", "b", "c"] }],
    });
    expect(toEngineConditions([{ attribute: "tags", operator: "not_in", value: "x, y" }])).toEqual({
      and: [{ attr: "tags", op: "not_in", value: ["x", "y"] }],
    });
  });

  it("contains/not_contains 原样透传", () => {
    expect(toEngineConditions([{ attribute: "tags", operator: "contains", value: "vip" }])).toEqual({
      and: [{ attr: "tags", op: "contains", value: "vip" }],
    });
  });
});

describe("toUIConditions (引擎 dict → UI 数组)", () => {
  it("映射引擎 op → 展示符（eq → =）", () => {
    expect(toUIConditions({ and: [{ attr: "role_level", op: "gte", value: "5" }] })).toEqual([
      { attribute: "role_level", operator: ">=", value: "5" },
    ]);
  });

  it("数组 value join 成逗号字符串", () => {
    expect(toUIConditions({ and: [{ attr: "tags", op: "in", value: ["a", "b"] }] })).toEqual([
      { attribute: "tags", operator: "in", value: "a, b" },
    ]);
  });

  it("已是数组（旧数据）原样透传", () => {
    const arr = [{ attribute: "a", operator: "=", value: "1" }];
    expect(toUIConditions(arr)).toBe(arr);
  });

  it("or 树 → __or__ 只读标记，可往返还原", () => {
    const orTree = { or: [{ attr: "role_code", op: "eq", value: "dept_head" }, { attr: "user_id", op: "eq", value: "u1" }] };
    const ui = toUIConditions(orTree);
    expect(ui.length).toBe(1);
    expect(ui[0]!.attribute).toBe("__or__");
    expect(toEngineConditions(ui)).toEqual(orTree);
  });

  it("or 树不再退空条件（不误显全局）", () => {
    const ui = toUIConditions({ or: [{ attr: "a", op: "eq", value: "1" }] });
    expect(ui.length).toBeGreaterThan(0);
  });

  it("单条件 {attr, op, value}（API/脚本创建，非 and 包裹）→ 单行 UI 条件", () => {
    expect(toUIConditions({ attr: "role_code", op: "eq", value: "dept_head" })).toEqual([
      { attribute: "role_code", operator: "=", value: "dept_head" },
    ]);
  });

  it("单条件 in 值数组 join 成逗号字符串", () => {
    expect(toUIConditions({ attr: "dept_ids", op: "in", value: ["d1", "d2"] })).toEqual([
      { attribute: "dept_ids", operator: "in", value: "d1, d2" },
    ]);
  });

  it("非 dict / 垃圾输入 → []", () => {
    expect(toUIConditions(null)).toEqual([]);
    expect(toUIConditions("x")).toEqual([]);
    expect(toUIConditions({})).toEqual([]);
  });
});

describe("toGrantArray (引擎授权 dict → UI 数组)", () => {
  it("dict {permissions:[...]} → [{permission}]", () => {
    expect(toGrantArray({ permissions: ["kb:create", "kb:read"] })).toEqual([
      { permission: "kb:create" },
      { permission: "kb:read" },
    ]);
  });

  it("已是数组原样透传", () => {
    const arr = [{ permission: "kb:create" }];
    expect(toGrantArray(arr)).toBe(arr);
  });

  it("垃圾/空 → []", () => {
    expect(toGrantArray(null)).toEqual([]);
    expect(toGrantArray({})).toEqual([]);
    expect(toGrantArray({ permissions: "kb:create" })).toEqual([]);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});
