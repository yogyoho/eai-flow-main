import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "@rstest/core";

const FRONTEND_ROOT = path.resolve(__dirname, "../../../..");
const read = (relativePath: string) =>
  readFileSync(path.join(FRONTEND_ROOT, relativePath), "utf8");

// EAI-CUSTOM: 2026-08-19 对齐上游分包边界——settings-dialog-host 保持
// dynamic()+if(!open) 形态、workspace-nav-menu 挂 host、dialog 内 section
// page 全部 dynamic()；chat-box 右侧面板 4 个 dynamic() 早已就位。
// 2026-09-19 上游 #5468（Capability Center）后：tool 随上游迁出 settings。
// 2026-09-26 上游 #5596（Settings 管理共享 models）后：上游 dialog 为 8 个
// dynamic section；EAI 融合态同样为 8 个——删 appearance/about（c9b3af55a），
// 加 EAI skill/wechat 扩展 tab 与上游 models tab
// (account/channels/memory/notification/models/skill/subagent/wechat)。
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
    // EAI-CUSTOM: 上游 #5468 后 skill/tool/integrations 迁往 Capability
    // Center；#5596 又加 models tab，上游为 8。EAI settings dialog 保留
    // skill + wechat 扩展 tab，删 appearance/about（c9b3af55a），加上游
    // models tab，tool 随上游迁出，故同为 8 个 dynamic section
    // (account/channels/memory/notification/models/skill/subagent/wechat)。
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
