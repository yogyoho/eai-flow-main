import { expect, test, describe } from "vitest";
import { toCamelCase, toSnakeCase } from "@/extensions/project/transforms";

describe("toCamelCase", () => {
  test("converts snake_case keys to camelCase", () => {
    const result = toCamelCase({ report_type: "test", created_at: "2024-01-01" });
    expect(result).toEqual({ reportType: "test", createdAt: "2024-01-01" });
  });

  test("handles nested objects", () => {
    const result = toCamelCase({
      outer_key: { inner_key: "value" }
    });
    expect(result).toEqual({ outerKey: { innerKey: "value" } });
  });

  test("handles arrays of objects", () => {
    const result = toCamelCase({
      items: [{ item_name: "a" }, { item_name: "b" }]
    });
    expect(result).toEqual({ items: [{ itemName: "a" }, { itemName: "b" }] });
  });

  test("preserves primitive values", () => {
    const result = toCamelCase({ count: 5, active: true, name: "test" });
    expect(result).toEqual({ count: 5, active: true, name: "test" });
  });

  test("handles empty object", () => {
    expect(toCamelCase({})).toEqual({});
  });

  test("handles deeply nested structures", () => {
    const result = toCamelCase<{
      levelOne: {
        levelTwo: {
          levelThree: { deepValue: number };
        };
        arrayOfItems: { nestedItem: string }[];
      };
    }>({
      level_one: {
        level_two: {
          level_three: { deep_value: 42 }
        },
        array_of_items: [{ nested_item: "test" }]
      }
    });
    expect(result).toEqual({
      levelOne: {
        levelTwo: {
          levelThree: { deepValue: 42 }
        },
        arrayOfItems: [{ nestedItem: "test" }]
      }
    });
  });

  test("handles null values", () => {
    const result = toCamelCase({ null_field: null, normal_field: "value" });
    expect(result).toEqual({ nullField: null, normalField: "value" });
  });

  test("preserves Date objects", () => {
    const date = new Date("2024-01-01");
    const result = toCamelCase<{ createdAt: Date; otherField: string }>({ created_at: date, other_field: "test" });
    expect(result.createdAt).toBe(date);
    expect(result.otherField).toBe("test");
  });

  test("handles arrays with mixed types", () => {
    const result = toCamelCase<{ mixedArray: unknown[] }>({
      mixed_array: [{ item_key: "obj" }, "string", 123, null]
    });
    expect(result.mixedArray).toEqual([{ itemKey: "obj" }, "string", 123, null]);
  });
});

describe("toSnakeCase", () => {
  test("converts camelCase keys to snake_case", () => {
    const result = toSnakeCase({ reportType: "test", createdAt: "2024-01-01" });
    expect(result).toEqual({ report_type: "test", created_at: "2024-01-01" });
  });

  test("skips undefined values", () => {
    const result = toSnakeCase({ name: "test", value: undefined });
    expect(result).toEqual({ name: "test" });
  });

  test("preserves null values", () => {
    const result = toSnakeCase({ templateId: null });
    expect(result).toEqual({ template_id: null });
  });

  test("handles empty object", () => {
    expect(toSnakeCase({})).toEqual({});
  });

  test("handles multiple consecutive uppercase letters", () => {
    const result = toSnakeCase({ userId: "123", projectId: "456" });
    expect(result).toEqual({ user_id: "123", project_id: "456" });
  });

  test("handles numbers in keys", () => {
    const result = toSnakeCase({ field2Name: "value" });
    expect(result).toEqual({ field2_name: "value" });
  });

  test("preserves primitive values", () => {
    const result = toSnakeCase({ count: 5, active: true, name: "test" });
    expect(result).toEqual({ count: 5, active: true, name: "test" });
  });

  test("handles already snake_case keys", () => {
    const result = toSnakeCase({ already_snake: "test" });
    // Already snake_case will still be transformed (no special handling)
    expect(result).toEqual({ already_snake: "test" });
  });
});