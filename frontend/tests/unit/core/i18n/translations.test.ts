import { describe, expect, it } from "@rstest/core";

import { loadTranslations } from "@/core/i18n/translations";

describe("core copy loading", () => {
  it("loads only the requested overseas and domestic copy", async () => {
    const [english, chinese] = await Promise.all([
      loadTranslations("en-US"),
      loadTranslations("zh-CN"),
    ]);
    expect(english.inputBox.disclaimer).toBe(
      "Deerflow is AI and can make mistakes",
    );
    expect(chinese.inputBox.disclaimer).toBe(
      "内容由AI生成，重要信息请务必核查",
    );
    // EAI-CUSTOM: upstream asserts a `buzz` channel EAI does not ship; the
    // closest EAI channel is wechat (iLink integration).
    expect(english.channels.descriptions.wechat).toBe(
      "WeChat iLink messages through your DeerFlow bot.",
    );
    expect(chinese.channels.descriptions.wechat).toBe(
      "通过 DeerFlow Bot 接收微信 iLink 消息。",
    );
  });
});
