import { describe, expect, test } from "@rstest/core";

import {
  RAGFLOW_DATASETS,
  ragflowPhase,
} from "@/extensions/contract-price/components/ragflowPhase";
import type { RagflowStatusResponse } from "@/extensions/contract-price/types";

// EAI-CUSTOM: ragflowPhase 纯函数态推导矩阵。pending 是组件级关注点
// (SettingsView 在查询进行中直接短路),不在本矩阵内。

const ds = (name: string, status: "connected" | "missing") => ({
  name,
  status,
  dataset_id: `id-${name}`,
});

const connected = (name: string) => ds(name, "connected");
const missing = (name: string) => ds(name, "missing");

describe("ragflowPhase", () => {
  test("pins the two fixed dataset names (backend ragflow_setup constants)", () => {
    expect([...RAGFLOW_DATASETS]).toEqual(["合同知识库", "合同货物分项表格"]);
  });

  test("derives phase from the status payload (matrix)", () => {
    const [contractName, goodsName] = RAGFLOW_DATASETS;
    const cases: {
      name: string;
      data?: RagflowStatusResponse;
      isError?: boolean;
      initializing?: boolean;
      want: string;
    }[] = [
      {
        name: "both datasets connected → ok",
        data: {
          available: true,
          datasets: [connected(contractName), connected(goodsName)],
        },
        want: "ok",
      },
      {
        // C1: RAGFlow 进程挂掉的真实形状——degraded 载荷不带 error 键也必须 err
        name: "available=false without error key → err (RAGFlow down)",
        data: { available: false, datasets: [] },
        want: "err",
      },
      {
        name: "available=false with error → err",
        data: { available: false, datasets: [], error: "RAGFlow 服务不可达" },
        want: "err",
      },
      {
        // 防御形状: error 键单独出现(available 缺失)同样按不可达处理
        name: "error key only → err",
        data: { error: "x" } as unknown as RagflowStatusResponse,
        want: "err",
      },
      {
        name: "never fetched (no data, no error) → idle",
        data: undefined,
        want: "idle",
      },
      {
        name: "status request itself failed → err",
        data: undefined,
        isError: true,
        want: "err",
      },
      {
        // M3: 一库连接一库缺失 → partial(「重新对齐」修复路径),不得谎报 ok
        name: "one connected one missing → partial",
        data: {
          available: true,
          datasets: [connected(contractName), missing(goodsName)],
        },
        want: "partial",
      },
      {
        name: "available but both datasets missing → idle",
        data: {
          available: true,
          datasets: [missing(contractName), missing(goodsName)],
        },
        want: "idle",
      },
      {
        name: "available with error key, none connected → err",
        data: {
          available: true,
          datasets: [missing(contractName), missing(goodsName)],
          error: "boom",
        },
        want: "err",
      },
      {
        name: "initializing mutation short-circuits even over ok data",
        data: {
          available: true,
          datasets: [connected(contractName), connected(goodsName)],
        },
        initializing: true,
        want: "initializing",
      },
    ];

    for (const c of cases) {
      const got = ragflowPhase(
        { data: c.data, isError: c.isError ?? false },
        c.initializing ?? false,
      );
      if (got !== c.want) {
        throw new Error(`case "${c.name}": want ${c.want}, got ${got}`);
      }
    }
  });
});
