# 知识库细粒度数据访问控制（Knowledge Base Data Access Control）设计

- 日期：2026-08-06
- 状态：已评审（用户认可 §1-§4）
- 关联：role-management-yaml-driven、policy-grant-page-visibility

## 背景与现状

知识库（`knowledge_bases` 表）当前访问模型：

- 每 KB：`owner_id` + `access_type`(public/dept/private) + `allowed_depts`；**无每-KB 授权列表**
- 角色 `data_scopes`（`config/permissions.yaml` knowledge 模块）决定"能看哪类"：
  - `knowledge_owner`：自己的
  - `knowledge_public`：公开的
  - `knowledge_dept`：自己的 ∪ 部门重叠（access_type=dept AND allowed_depts 命中）
  - 普通用户仅 owner+public；dept_head/project_manager/writer/reviewer 含 dept
- 强制：`with_data_scope("knowledge")` → DataScopeEngine → FilterRule → SQL WHERE（合取：角色 scope AND KB 属性匹配）
- 超管 bypass（allow_all）
- 子文档（documents）继承所属 KB 可见性
- `knowledge_factory`（模板/抽取/法规/任务）**无 data_scope**，有 system:access 全可见（范围外）

### 冲突分析（为什么角色控制不够）

角色 `data_scope` 是**类级分类器**（"哪类 KB 谁能碰"），无法表达**实例级例外**。业务确认存在三类真实场景：

1. **部门内子集限制**：一个部门里只让子组看某 KB
2. **跨部门/角色共享**：私有 KB 共享给特定人（不因改 access_type 而开放整个集合）
3. **按项目/任务临时授权**：给特定人短期开某 KB

硬用角色表达实例例外 → 每个例外造一个角色/scope → **角色爆炸**。因此需在 RBAC 之上加**对象级授权**（与角色控制**互补**，非冲突）。

## 设计决策

- **方案**：独立授权表 `knowledge_base_grants`（否决数组列、否决复用 docmgr DocumentShare——后者只支持单 user 目标）
- **组合**：授权是**显式例外（OR）**——`可见 ⟺ (角色 scope 匹配) OR (授权命中我)`，跨部门/角色共享才成立
- **权限语义**：read / write（write 不含授权管理）

## 数据模型

```sql
CREATE TABLE knowledge_base_grants (
  id            UUID PRIMARY KEY,
  kb_id         UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  grantee_type  VARCHAR(20) NOT NULL,          -- 'user' | 'dept' | 'role'
  grantee_id    VARCHAR(64) NOT NULL,          -- user/dept=UUID串; role=角色code(registry真源)
  permission    VARCHAR(20) NOT NULL DEFAULT 'read',  -- 'read' | 'write'
  expires_at    TIMESTAMP NULL,                -- 临时授权过期
  created_by    UUID REFERENCES users(id),     -- 审计
  created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (kb_id, grantee_type, grantee_id)
);
```

SQLAlchemy 模型加入 `backend/app/extensions/models/__init__.py`；幂等迁移加入 `backend/app/extensions/database.py`。

## 可见性组合（核心规则）

```
可见 ⟺ (现有 data_scope 过滤) OR EXISTS (
  SELECT 1 FROM knowledge_base_grants g
  WHERE g.kb_id = knowledge_bases.id
    AND (g.grantee_type='user'  AND g.grantee_id = :user_id
      OR g.grantee_type='dept'  AND g.grantee_id IN (identity.dept_ids)
      OR g.grantee_type='role'  AND g.grantee_id = identity.role_code)
    AND (g.expires_at IS NULL OR g.expires_at > now()))
```

**强制落点**：KB 查询层（`with_data_scope("knowledge")` → FilterRule → SQL WHERE）统一追加 `OR EXISTS(grant)`。实现方式（计划阶段定）：
- 扩展 FilterRule 渲染支持 grant-EXISTS 谓词；或
- 在知识库 scoped 查询构建处统一拼 OR

要求：**所有 KB 端点（list / by-id / search / docs 列表）一致生效，不可遗漏**。子文档继承 KB 可见性，无需单独改。

## 权限语义

| 级别 | 能力 |
|---|---|
| read | 查看 KB + 文档 + 检索 |
| write | read + 内容管理：上传/删除文档、编辑/删除 KB 元信息 |

- 编辑/删除 KB：`owner | write-grantee | 超管`（现状 owner|超管 扩展）
- 上传/删除文档：`(owner | write-grantee | 超管) 且 持有 kb:upload 权限`——`kb:upload` 为角色能力门（保留现状权限点），owner/write-grantee/超管 为对象写门；两者 AND。堵住现状"上传未 owner 门"缺口
- 授权管理（增删 grant）：仅 `owner | 超管`；write grantee 不含
- owner 恒 write；超管 bypass

## API

（owner|超管）`/knowledge-bases/{kb_id}/grants`

- `GET` 列授权
- `POST` `{grantee_type, grantee_id, permission='read', expires_at?}`——grantee 校验：user/dept 存在、role code 在 registry
- `PATCH /{grant_id}` `{permission?, expires_at?}`（可选）
- `DELETE /{grant_id}` 撤销

## UI（KB 管理页）

- 保留现有访问控制区（access_type / allowed_depts）
- 新增「授权」区：列表（类型徽章 + 名称 + 权限 + 过期）+ 添加/删除
- 添加授权选择器：搜索 用户/部门/角色
- 已过期授权显示灰色"已过期"

## 边界 / 一致性

- owner 恒可见（不经 scope/grant）
- 超管 bypass（既有 allow_all）
- 过期 grant → 查询时不命中
- grantee 停用/删除 → identity 不匹配 → 无访问（惰性，不主动清理）
- KB 删除 → grants ON DELETE CASCADE
- 临时授权不做物理清理（查询时判断 expires_at）

## 测试

- 模型/迁移（表结构 + 级联）
- 可见性组合：scope 内可见；跨部门 grant 可见；过期 grant 不可见；私有+授权子集（scope 不命中仅 grant 命中）
- 写权限：write-grantee 可编辑/上传；read-grantee 不可编辑
- API：CRUD；非 owner 访问 grants 403
- UI E2E：授权增删 + 目标用户可见性

## 范围外（后续项）

- `knowledge_factory`（模板/抽取/法规/任务）无 data_scope 缺口
- docmgr 不动
- 过期授权自动清理任务
