# 应用中心分类体系设计

> 日期：2026-06-22 | 状态：已确认

## 目标

为应用中心设计可支撑 50+ 内部应用稳健增长的分类体系。

## 设计决策

- **主分类维度**：业务域（business domain），按企业业务单元自然增长
- **辅助维度**：功能阶段标签（stage tag），卡片级徽章展示，不作为独立筛选项
- **当前范围**：仅内部应用，第三方集成暂不纳入

---

## 一、分类模型

单一层级：每个应用归属一个 `businessDomain`。

### 两种分类类型

| 类型 | 生命周期 | 示例 |
|------|----------|------|
| **业务域** | 动态增长，随业务单元扩展 | 采购管理、报告编撰、合规审查 |
| **通用分类** | 固定 2 个，硬编码白名单 | 通用工具、系统管理 |

通用分类收纳跨业务域的应用（工作台、文档空间、智能写作），避免污染业务域分类。

---

## 二、当前应用迁移

| 应用 | 旧 category | → | 新 businessDomain |
|------|-------------|---|-------------------|
| 工作台 | project | | universal |
| 智能写作 | writing | | universal |
| 报告项目 | project | | report-compilation |
| 文档空间 | document | | universal |
| 知识工厂 | knowledge | | knowledge |
| 知识库 | knowledge | | knowledge |
| 报告输出 | report | | report-compilation |
| 采购管理 | project | | procurement |
| 系统管理 | admin | | admin |

迁移后分布：通用工具(3)、报告编撰(2)、知识管理(2)、采购管理(1)、系统管理(1)。

---

## 三、功能阶段标签

每个应用可携带一个可选的功能阶段标签，以徽章形式展示在卡片上。

| 标签 | 含义 | 示例应用 |
|------|------|----------|
| `overview` 概览 | 全局视图/入口 | 工作台 |
| `collect` 采集 | 数据/资料录入 | 数据采集 |
| `process` 加工 | AI 处理/分析 | 合同分析、智能写作 |
| `collaborate` 协作 | 多人协同流转 | 报告项目、文档空间 |
| `output` 输出 | 成果生成/导出 | 报告输出 |
| `retrieve` 检索 | 查询/问答 | 知识库 |
| `manage` 管理 | 配置/管控 | 系统管理 |

规则：
- 每个应用最多 1 个标签
- 标签可选——不确定就不标
- 不作为分类筛选维度，仅视觉辅助

---

## 四、数据模型

```typescript
export type BusinessDomainKey = string;

export type StageTag =
  | "overview"
  | "collect"
  | "process"
  | "collaborate"
  | "output"
  | "retrieve"
  | "manage";

export interface AppDefinition {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;

  // 主分类：业务域
  businessDomain: BusinessDomainKey;

  // 辅助标签：功能阶段（可选）
  stageTag?: StageTag;

  path: string;
  licenseModule: string | null;
  adminOnly?: boolean;
  sortOrder: number;
  sortKey: string;
  isBuiltin: boolean;
}
```

## 五、通用分类常量

```typescript
export const UNIVERSAL_DOMAINS = new Set<BusinessDomainKey>([
  "universal",   // 通用工具
  "admin",       // 系统管理
]);
```

## 六、分类配置

通用分类手动声明 label 和 accent；业务域的 accent 从调色板自动轮转分配。

```typescript
export const DOMAIN_CONFIG: Record<string, { label: string; accent: AccentColor }> = {
  universal: { label: "通用工具", accent: "blue" },
  admin:     { label: "系统管理", accent: "slate" },
};

// 调色板（按需扩展）
export const ACCENT_PALETTE: AccentColor[] = [
  "blue", "violet", "cyan", "amber", "emerald",
  "rose", "indigo", "teal", "orange", "sky",
];
```

## 七、分类 Pill 生成逻辑

```
1. 从 visibleApps 提取所有 businessDomain，去重
2. 通用分类排在前面（universal → admin），按 UNIVERSAL_DOMAINS 声明顺序
3. 业务域按首次出现顺序排列，自动从调色板取 accent
4. 每个 pill 显示 count（该域下可见应用数）
5. "全部" pill 始终在最前
```

---

## 八、UI 布局

不变。现有布局已足够：

```
标题 + 统计
工具栏（搜索 → 分类 pills → 排序）
收藏区（条件显示）
主网格
```

变更点：
- 分类 pills 标签从旧的 CATEGORIES 改为业务域名
- 应用卡片增加 stageTag 小徽章
- AccentColor 调色板从 6 色扩展到 10 色

---

## 九、不在范围内

- 第三方/外部应用集成（后续独立设计）
- 多级分类/嵌套分类
- 功能阶段标签作为筛选维度
- 业务域的管理后台 CRUD（直接在 apps.ts 中声明）
