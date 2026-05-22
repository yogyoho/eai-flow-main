import { expect, test, describe } from "vitest";

import { PLUGIN_TYPE_LABELS, PLUGIN_STATUS_LABELS } from "@/extensions/plugin/types";

describe("Plugin type labels", () => {
  test("PLUGIN_TYPE_LABELS has all plugin types with Chinese labels", () => {
    expect(PLUGIN_TYPE_LABELS).toEqual({
      data_connector: "数据连接器",
      tool: "工具",
      output: "输出插件",
      custom: "自定义",
    });
  });

  test("PLUGIN_STATUS_LABELS has all statuses", () => {
    expect(PLUGIN_STATUS_LABELS).toEqual({
      registered: "已注册",
      installed: "已安装",
      enabled: "已启用",
      disabled: "已禁用",
    });
  });

  test("every PluginType has a label", () => {
    const types: string[] = ["data_connector", "tool", "output", "custom"];
    for (const t of types) {
      expect(PLUGIN_TYPE_LABELS[t as keyof typeof PLUGIN_TYPE_LABELS]).toBeDefined();
    }
  });

  test("every PluginStatus has a label", () => {
    const statuses: string[] = ["registered", "installed", "enabled", "disabled"];
    for (const s of statuses) {
      expect(PLUGIN_STATUS_LABELS[s as keyof typeof PLUGIN_STATUS_LABELS]).toBeDefined();
    }
  });
});