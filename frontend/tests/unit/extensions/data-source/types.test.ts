import { expect, test, describe } from "vitest";

import {
  DATA_SOURCE_TYPE_LABELS,
  CONNECTION_STATUS_LABELS,
  AUTH_TYPE_LABELS,
  SYNC_MODE_LABELS,
} from "@/extensions/data-source/types";

describe("Data source type labels", () => {
  test("DATA_SOURCE_TYPE_LABELS has all types", () => {
    expect(DATA_SOURCE_TYPE_LABELS).toEqual({
      database: "数据库",
      api: "API接口",
      file: "文件",
      gis: "GIS数据",
    });
  });

  test("CONNECTION_STATUS_LABELS has all statuses", () => {
    expect(CONNECTION_STATUS_LABELS).toEqual({
      connected: "已连接",
      error: "连接错误",
      disconnected: "未连接",
      testing: "测试中",
    });
  });

  test("every DataSourceType has a label", () => {
    const types: string[] = ["database", "api", "file", "gis"];
    for (const t of types) {
      expect(DATA_SOURCE_TYPE_LABELS[t as keyof typeof DATA_SOURCE_TYPE_LABELS]).toBeDefined();
    }
  });

  test("AUTH_TYPE_LABELS has all auth types", () => {
    expect(AUTH_TYPE_LABELS).toEqual({
      none: "无认证",
      basic: "基本认证",
      oauth: "OAuth",
      api_key: "API密钥",
      certificate: "证书",
    });
  });

  test("SYNC_MODE_LABELS has all sync modes", () => {
    expect(SYNC_MODE_LABELS).toEqual({
      manual: "手动",
      scheduled: "定时",
      event: "事件驱动",
    });
  });
});