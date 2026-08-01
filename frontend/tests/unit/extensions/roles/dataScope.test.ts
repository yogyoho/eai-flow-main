import { expect, test, describe } from "vitest";

import { resolveDataScopeSelections } from "@/extensions/role/dataScope";
import { type RegistryModule } from "@/extensions/types";

const modules: RegistryModule[] = [
  {
    key: "contract_price",
    display_name: "合同价格",
    permissions: [],
    data_scopes: [
      { id: "cpa_all", display_name: "全部合同数据" },
      { id: "cpa_dept", display_name: "本部门合同数据" },
    ],
  },
  {
    key: "knowledge",
    display_name: "知识库",
    permissions: [],
    data_scopes: [
      { id: "knowledge_owner", display_name: "本人创建" },
      { id: "knowledge_dept", display_name: "本部门" },
    ],
  },
];

describe("resolveDataScopeSelections (deny-by-default)", () => {
  test("empty role data_scopes → empty result (no fabricated selection)", () => {
    expect(resolveDataScopeSelections(modules, [])).toEqual({});
  });

  test("role scoped for only some modules → only those modules get entries (contract_price omitted when no cpa scope)", () => {
    const result = resolveDataScopeSelections(modules, ["knowledge_dept"]);
    expect(result).toEqual({ knowledge: "knowledge_dept" });
    expect(result.contract_price).toBeUndefined();
  });

  test("role scope matching a module → that module maps to the matched scope id", () => {
    const result = resolveDataScopeSelections(modules, ["cpa_all", "knowledge_owner"]);
    expect(result).toEqual({ contract_price: "cpa_all", knowledge: "knowledge_owner" });
  });

  test("role scope id matching nothing → omitted (unknown ids never map)", () => {
    const result = resolveDataScopeSelections(modules, ["bogus_scope", "cpa_dept"]);
    expect(result).toEqual({ contract_price: "cpa_dept" });
  });

  test("two role scopes for one module → first match wins", () => {
    const result = resolveDataScopeSelections(modules, ["cpa_dept", "cpa_all"]);
    expect(result).toEqual({ contract_price: "cpa_dept" });
  });

  test("modules with no data_scopes are skipped", () => {
    const noScopeModules: RegistryModule[] = [
      { key: "system", display_name: "系统", permissions: [], data_scopes: [] },
      { key: "settings", display_name: "设置", permissions: [], data_scopes: [] },
    ];
    expect(resolveDataScopeSelections(noScopeModules, ["anything"])).toEqual({});
  });

  test("undefined roleDataScopes → empty result", () => {
    expect(resolveDataScopeSelections(modules, undefined)).toEqual({});
  });
});
