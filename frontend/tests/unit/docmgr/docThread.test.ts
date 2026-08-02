import { describe, expect, test, vi } from "vitest";

import { resolveSubThreadId } from "@/extensions/docmgr/utils/docThread";

describe("resolveSubThreadId", () => {
  test("存储线程有效 (exists=true) → 复用，不新建", async () => {
    const create = vi.fn();
    const { id, reused } = await resolveSubThreadId({
      storedId: "valid-123",
      exists: async () => true,
      create,
    });
    expect(id).toBe("valid-123");
    expect(reused).toBe(true);
    expect(create).not.toHaveBeenCalled();
  });

  test("存储线程失效 (exists=false) → 重建新线程", async () => {
    const { id, reused } = await resolveSubThreadId({
      storedId: "stale-123",
      exists: async () => false,
      create: async () => "fresh-456",
    });
    expect(id).toBe("fresh-456");
    expect(reused).toBe(false);
  });

  test("无存储记录 → 直接新建", async () => {
    const { id, reused } = await resolveSubThreadId({
      storedId: null,
      exists: async () => false,
      create: async () => "brand-new-789",
    });
    expect(id).toBe("brand-new-789");
    expect(reused).toBe(false);
  });

  test('exists 抛错向上传播（调用方 threadExists 负责把网络错误保守当"存在"）', async () => {
    await expect(
      resolveSubThreadId({
        storedId: "weird",
        exists: async () => {
          throw new Error("network down");
        },
        create: async () => "rebuilt-111",
      }),
    ).rejects.toThrow("network down");
  });
});
