# 工作流槽位体系设计

**日期**: 2026-06-06（第2版，推翻第1版）
**状态**: 设计中
**关联**: BUG-3 (bug-029)

---

## 1. 核心洞察

**"项目角色"不是角色——它们是工作流节点上的执行人标签。**

模板设计者在编排工作流时，为每个节点指定"这个阶段需要谁来执行"。这个指定就是槽位（slot）。槽位类型决定权限加成，槽位标签决定显示名称。项目成员没有独立的"角色"——他们只是被分配到了某个槽位上。

---

## 2. 四类槽位

| 槽位类型 | 默认标签 | 权限 | 说明 |
|---------|---------|------|------|
| `lead` | 组长 | project:create, member:add/remove, template:select, ai:generate, chapter:write_any, chapter:confirm, report:submit | 创建项目、选模板、拉组员、AI生成、编辑、提交成果 |
| `writer` | 组员 | ai:generate, chapter:write_own, chapter:confirm | AI生成、编辑自己的章节、确认完成 |
| `dept_reviewer` | 部门审核人 | chapter:review | 审核报告，提出修改建议 |
| `company_reviewer` | 公司审核人 | chapter:review, report:final_approve | 审核报告，最终批准 |

**两级审核的区别**：公司审核人可以最终批准（report:final_approve），部门审核人只能审核建议。审核层级由工作流节点顺序保证。

---

## 3. 数据模型（无需新建表）

### 3.1 不新建 project_roles 表

槽位类型和权限仍然在代码中定义（`_DUTY_BONUS` 字典），因为：
- 只有4种槽位类型，不需要数据库管理
- 权限集相对固定，不需要运行时修改
- 模板设计者只需要选择槽位类型 + 自定义标签

### 3.2 模板 graph_json 中的槽位定义

```json
{
  "nodes": [
    {
      "id": "phase-2",
      "type": "phase",
      "data": {
        "label": "消防设计方案编写",
        "slots": [
          {
            "slot_type": "writer",
            "label": "撰写人",
            "count": 2
          }
        ]
      }
    },
    {
      "id": "review-1",
      "type": "review",
      "data": {
        "label": "内部技术审核",
        "slots": [
          {
            "slot_type": "dept_reviewer",
            "label": "部门审核人",
            "count": 2
          }
        ]
      }
    }
  ]
}
```

### 3.3 project_members.phase_duties 不变

```json
{
  "phase-2": {"slot_type": "writer", "label": "撰写人"},
  "review-1": {"slot_type": "dept_reviewer", "label": "部门审核人"}
}
```

---

## 4. 权限计算

### 4.1 project_permissions.py

```python
# 槽位权限加成（替代原 _DUTY_BONUS）
SLOT_PERMISSIONS = {
    "lead": {
        "project:create", "member:add", "member:remove",
        "template:select", "ai:generate",
        "chapter:write_any", "chapter:confirm",
        "report:submit",
    },
    "writer": {
        "ai:generate", "chapter:write_own", "chapter:confirm",
    },
    "dept_reviewer": {
        "chapter:review",
    },
    "company_reviewer": {
        "chapter:review", "report:final_approve",
    },
}
```

### 4.2 权限合并

用户在某项目中的有效权限 = 其所有 phase_duties 槽位的权限并集。

```python
def get_effective_permissions(member):
    perms = set()
    for phase_node, duty in (member.phase_duties or {}).items():
        slot_type = duty.get("slot_type", "")
        perms |= SLOT_PERMISSIONS.get(slot_type, set())
    return perms
```

---

## 5. Dashboard 标签推导

`_classify_project_role()` 简化为：

```python
def _classify_project_role(member, project):
    """根据成员在项目中的槽位分配推导 Dashboard 分组标签"""
    duties = member.phase_duties or {}
    
    # 按优先级查找：lead > reviewer > writer
    slot_types = {d.get("slot_type") for d in duties.values()}
    
    if "lead" in slot_types:
        return "lead", "我负责的项目"
    if "company_reviewer" in slot_types or "dept_reviewer" in slot_types:
        return "reviewer", "作为审核人"
    if "writer" in slot_types:
        return "writer", "作为撰写人"
    
    # 未分配到任何槽位 → 仅查看
    return "viewer", "仅查看"
```

**BUG-3 自动修复**：只要 wanger 被分配到了 writer 槽位，Dashboard 就显示"作为撰写人"。

---

## 6. 前端变更

### 6.1 PhaseConfigPanel（模板编辑器）

```
BEFORE: PRESET_ROLES 硬编码下拉
  { roleKey: "lead", label: "阶段负责人" }
  { roleKey: "writer", label: "撰写人" }
  { roleKey: "reviewer", label: "审核人" }
  { roleKey: "data_reviewer", label: "数据审核" }
  { roleKey: "approver", label: "审批人" }

AFTER: 槽位类型下拉 + 自定义标签
  槽位类型: [组长 ▼] [部门审核人 ▼] [组员 ▼] [公司审核人 ▼]
  显示标签: [____________] (默认使用槽位类型的默认标签，可自定义)
  需要人数: [1]
```

### 6.2 AddMemberDialog

角色下拉 → 槽位分配下拉。不再显示"负责人/管理者/撰写人/审核人/审批人/成员"，而是显示当前工作流阶段需要的槽位。

### 6.3 Dashboard

ROLE_LABELS / GROUP_LABELS 从 `_classify_project_role()` 返回值动态生成，不再需要硬编码映射表。

---

## 7. 消除的硬编码

| 文件 | 删除内容 |
|------|---------|
| `types.ts:5` | `type MemberRole = "owner" \| "manager" \| ...` |
| `types.ts:107` | `MEMBER_ROLE_LABELS` |
| `schemas.py:22` | `VALID_MEMBER_ROLES` |
| `permissions.py:16` | `PERMISSION_MATRIX`（改为 SLOT_PERMISSIONS） |
| `permissions.py:19` | `ROLE_ORDER` |
| `ProjectMiniCard.tsx:6` | `ROLE_LABELS` |
| `MyProjects.tsx:8` | `GROUP_LABELS` |
| `PhaseConfigPanel.tsx:9` | `PRESET_ROLES` |

---

## 8. 不需要做的

- ❌ 不需要新建 `project_roles` 表
- ❌ 不需要 `/admin/project-roles` 管理页面
- ❌ 不需要角色继承、权限模板化
- ❌ 不需要 project_members 新增 project_role_id 列
- ❌ project_members.role 列保留（向后兼容），但不再用于权限计算

---

## 9. 迁移策略

1. `SLOT_PERMISSIONS` 替代 `_DUTY_BONUS`（4种槽位类型）
2. `_classify_project_role()` 改为基于 slot_type 推导
3. PhaseConfigPanel 槽位下拉改为4种类型 + 自定义标签
4. 现有模板的 phase_duties 数据无需迁移（已包含 duty 信息）
5. 删除 MEMBER_ROLE_LABELS / ROLE_LABELS / GROUP_LABELS 硬编码
