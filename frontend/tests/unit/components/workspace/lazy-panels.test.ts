import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "@rstest/core";

const FRONTEND_ROOT = path.resolve(__dirname, "../../../..");
const read = (relativePath: string) =>
  readFileSync(path.join(FRONTEND_ROOT, relativePath), "utf8");

// EAI-CUSTOM: 2026-08-19 已对齐上游分包边界——settings-dialog-host 恢复
// dynamic()+if(!open) 形态、workspace-nav-menu 改挂 host、dialog 内 7 个
// section page 全部 dynamic()（上游 9 个，EAI 无 appearance/about/
// integrations 项）、chat-box 右侧面板 4 个 dynamic() 早已就位。
// 断言已按 EAI section 数适配（7 而非 9）。
describe("interaction-only bundle boundaries", () => {
  it("does not import the settings dialog until its store is open", () => {
    const host = read(
      "src/components/workspace/settings/settings-dialog-host.tsx",
    );
    expect(host).toContain("dynamic(");
    expect(host).toContain("if (!open)");
    expect(host).not.toContain(
      'import { SettingsDialog } from "./settings-dialog"',
    );
  });

  it("loads each settings page from its active section", () => {
    const dialog = read(
      "src/components/workspace/settings/settings-dialog.tsx",
    );
    // EAI-CUSTOM: 上游为 10；EAI settings dialog 渲染 8 个 dynamic section
    // (account/channels/memory/notification/skill/tool/subagent/wechat)。
    expect(dialog.match(/dynamic\(/g)).toHaveLength(8);
    expect(dialog).not.toMatch(
      /import \{ \w+SettingsPage \} from "@\/components\/workspace\/settings\//,
    );
  });

  it("keeps right-panel implementations behind dynamic imports", () => {
    const chatBox = read("src/components/workspace/chats/chat-box.tsx");
    expect(chatBox).toContain('import dynamic from "next/dynamic"');
    expect(chatBox).not.toMatch(
      /import \{ (?:ArtifactFileDetail|ArtifactFileList|BrowserViewPanel|SidecarPanel)/,
    );
    expect(chatBox.match(/dynamic\(/g)?.length).toBeGreaterThanOrEqual(4);
  });
});
