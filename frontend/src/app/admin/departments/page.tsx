"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Plus,
  Pencil,
  Trash2,
  ChevronRight,
  ChevronDown,
  Building2,
  Users,
  UserCircle,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { deptApi, userApi } from "@/extensions/api";
import type {
  Department,
  CreateDepartmentRequest,
  UpdateDepartmentRequest,
  User,
} from "@/extensions/types";
import { cn } from "@/lib/utils";

function flattenDepts(
  depts: Department[],
  level = 0,
): { dept: Department; level: number }[] {
  return depts.reduce(
    (acc, dept) => {
      acc.push({ dept, level });
      if (dept.children?.length) {
        acc.push(...flattenDepts(dept.children, level + 1));
      }
      return acc;
    },
    [] as { dept: Department; level: number }[],
  );
}

function findParentName(
  tree: Department[],
  parentId: string | undefined,
): string {
  if (!parentId) return "—";
  const flat = flattenDepts(tree);
  const p = flat.find((x) => x.dept.id === parentId);
  return p?.dept.name ?? "—";
}

function collectDeptIds(dept: Department): string[] {
  const ids = [dept.id];
  if (dept.children?.length) {
    dept.children.forEach((c) => ids.push(...collectDeptIds(c)));
  }
  return ids;
}
const ROOT_DEPARTMENT_OPTION = "__root_department__";
const UNSET_LEADER_OPTION = "__unset_leader__";

interface TreeNodeProps {
  dept: Department;
  level: number;
  selectedId: string | null;
  expandedIds: Set<string>;
  searchKeyword: string;
  onToggle: (id: string) => void;
  onSelect: (dept: Department) => void;
}

function DeptTreeNode({
  dept,
  level,
  selectedId,
  expandedIds,
  searchKeyword,
  onToggle,
  onSelect,
}: TreeNodeProps) {
  const hasChildren = dept.children && dept.children.length > 0;
  const isExpanded = expandedIds.has(dept.id);
  const isSelected = selectedId === dept.id;
  const matchSearch =
    !searchKeyword ||
    dept.name.toLowerCase().includes(searchKeyword.toLowerCase());
  const visibleChildren =
    dept.children?.filter(
      (c) =>
        !searchKeyword ||
        c.name.toLowerCase().includes(searchKeyword.toLowerCase()),
    ) ?? [];

  const showNode = matchSearch || (hasChildren && visibleChildren.length > 0);
  if (!showNode) return null;

  return (
    <div className="select-none">
      <div
        className={cn(
          "flex cursor-pointer items-center gap-1 rounded-lg px-3 py-2 text-sm transition-colors",
          isSelected
            ? "bg-primary/10 text-primary font-medium"
            : "text-foreground hover:bg-accent",
        )}
        style={{ paddingLeft: `${level * 1.5 + 0.75}rem` }}
        onClick={() => onSelect(dept)}
      >
        <div
          className={cn(
            "mr-1 flex h-5 w-5 items-center justify-center",
            hasChildren
              ? "text-muted-foreground hover:text-foreground cursor-pointer"
              : "opacity-0",
          )}
          onClick={(e) => {
            e.stopPropagation();
            if (hasChildren) onToggle(dept.id);
          }}
        >
          {hasChildren ? (
            isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )
          ) : null}
        </div>
        <Building2
          className={cn(
            "mr-2 h-4 w-4",
            isSelected ? "text-primary" : "text-muted-foreground",
          )}
        />
        <span className="flex-1 truncate">{dept.name}</span>
        {dept.unit_type && dept.unit_type !== "internal" && (
          <span
            className={cn(
              "rounded-full px-1.5 py-0 text-[10px] font-medium",
              dept.unit_type === "external"
                ? "bg-amber-100 text-amber-700"
                : "bg-blue-100 text-blue-700",
            )}
          >
            {dept.unit_type === "external" ? "外部" : "虚拟"}
          </span>
        )}
        {dept.status === "inactive" && (
          <span className="rounded-full bg-gray-100 px-1.5 py-0 text-[10px] text-gray-500">
            停用
          </span>
        )}
      </div>
      {hasChildren &&
        isExpanded &&
        visibleChildren.map((child) => (
          <DeptTreeNode
            key={child.id}
            dept={child}
            level={level + 1}
            selectedId={selectedId}
            expandedIds={expandedIds}
            searchKeyword={searchKeyword}
            onToggle={onToggle}
            onSelect={onSelect}
          />
        ))}
    </div>
  );
}

export default function AdminDepartmentsPage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedDept, setSelectedDept] = useState<Department | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [searchKeyword, setSearchKeyword] = useState("");
  const [includeSubDepts, setIncludeSubDepts] = useState(false);

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isMembersModalOpen, setIsMembersModalOpen] = useState(false);
  const [createFormData, setCreateFormData] = useState<CreateDepartmentRequest>(
    {
      name: "",
      description: "",
      parent_id: undefined,
      leader_id: undefined,
      sort_order: 0,
      code: undefined,
      status: "active",
    },
  );
  const [editFormData, setEditFormData] = useState<UpdateDepartmentRequest>({
    name: "",
    description: "",
    sort_order: 0,
    leader_id: undefined,
    code: undefined,
    status: undefined,
  });

  // useCallback + functional setState so the mount effect can depend on loadData without re-running on expandedIds changes
  const loadData = useCallback(async (retries = 2, delay = 1500) => {
    setIsLoading(true);
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const [deptsRes, usersRes] = await Promise.all([
          deptApi.list(),
          userApi.list({ limit: 1000 }),
        ]);
        setDepartments(deptsRes.departments);
        setUsers(usersRes.users);
        if (deptsRes.departments.length > 0) {
          setExpandedIds((prev) =>
            prev.size === 0
              ? new Set(deptsRes.departments.map((d) => d.id))
              : prev,
          );
        }
        if (deptsRes.departments.length > 0) {
          const flat = flattenDepts(deptsRes.departments);
          setSelectedDept((prev) =>
            prev
              ? (flat.find((x) => x.dept.id === prev.id)?.dept ?? prev)
              : (deptsRes.departments[0] ?? null),
          );
        }
        setIsLoading(false);
        return;
      } catch (err) {
        if (attempt < retries) {
          await new Promise((r) => setTimeout(r, delay));
        } else {
          console.error(err);
        }
      }
    }
    setIsLoading(false);
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const flatList = useMemo(() => flattenDepts(departments), [departments]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await deptApi.create(createFormData);
      setIsCreateModalOpen(false);
      setCreateFormData({
        name: "",
        description: "",
        parent_id: undefined,
        leader_id: undefined,
        sort_order: 0,
      });
      void loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "创建失败");
    }
  };

  const handleUpdate = async () => {
    if (!selectedDept) return;
    try {
      await deptApi.update(selectedDept.id, editFormData);
      setIsEditModalOpen(false);
      void loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "更新失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定要删除该部门吗？")) return;
    try {
      await deptApi.delete(id);
      if (selectedDept?.id === id) setSelectedDept(null);
      void loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "删除失败");
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const memberUsers = useMemo(() => {
    if (!selectedDept) return [];
    if (includeSubDepts && selectedDept.children?.length) {
      const ids = new Set(collectDeptIds(selectedDept));
      return users.filter((u) => u.dept_id && ids.has(u.dept_id));
    }
    return users.filter((u) => u.dept_id === selectedDept.id);
  }, [selectedDept, users, includeSubDepts]);

  const parentName = selectedDept
    ? findParentName(departments, selectedDept.parent_id)
    : "—";

  const openEditModal = (dept: Department) => {
    setEditFormData({
      name: dept.name,
      description: dept.description ?? "",
      sort_order: dept.sort_order,
      leader_id: dept.leader_id,
      code: dept.code,
      status: dept.status,
    });
    setIsEditModalOpen(true);
  };

  if (isLoading) {
    return (
      <main className="bg-background flex flex-1 items-center justify-center">
        <div className="text-muted-foreground">加载中...</div>
      </main>
    );
  }

  return (
    <main className="bg-background mx-auto flex h-full w-full max-w-[1600px] overflow-hidden">
      {/* Left Pane: Department Tree */}
      <div className="border-border bg-muted/30 flex w-80 shrink-0 flex-col border-r">
        <div className="border-border bg-card border-b p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-foreground font-semibold">组织架构</h2>
            <button
              onClick={() => {
                setCreateFormData({
                  name: "",
                  parent_id: selectedDept?.id,
                  leader_id: undefined,
                  sort_order: 0,
                  code: undefined,
                  status: "active",
                });
                setIsCreateModalOpen(true);
              }}
              className="bg-primary/10 text-primary hover:bg-primary/20 rounded-md p-1.5 transition-colors"
              title="新建子部门"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
          <div className="relative">
            <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
            <input
              type="text"
              placeholder="搜索部门..."
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              className="bg-secondary focus:bg-background focus:border-primary focus:ring-primary/20 w-full rounded-lg border-transparent py-2 pr-4 pl-9 text-sm transition-all outline-none focus:ring-2"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {departments.length === 0 ? (
            <div className="text-muted-foreground py-4 text-center text-sm">
              暂无部门
            </div>
          ) : searchKeyword ? (
            <div className="space-y-1">
              {flattenDepts(departments)
                .filter(({ dept }) =>
                  dept.name.toLowerCase().includes(searchKeyword.toLowerCase()),
                )
                .map(({ dept }) => (
                  <button
                    key={dept.id}
                    onClick={() => setSelectedDept(dept)}
                    className={cn(
                      "flex w-full items-center rounded-lg px-3 py-2 text-left text-sm transition-colors",
                      selectedDept?.id === dept.id
                        ? "bg-primary/10 text-primary font-medium"
                        : "text-foreground hover:bg-accent",
                    )}
                  >
                    <Building2
                      className={cn(
                        "mr-2 h-4 w-4 shrink-0",
                        selectedDept?.id === dept.id
                          ? "text-primary"
                          : "text-muted-foreground",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate">{dept.name}</div>
                      {dept.parent_id && (
                        <div className="text-muted-foreground truncate text-xs">
                          {findParentName(departments, dept.parent_id)}
                        </div>
                      )}
                    </div>
                  </button>
                ))}
              {flattenDepts(departments).filter(({ dept }) =>
                dept.name.toLowerCase().includes(searchKeyword.toLowerCase()),
              ).length === 0 && (
                <div className="text-muted-foreground py-4 text-center text-sm">
                  未找到匹配部门
                </div>
              )}
            </div>
          ) : (
            departments.map((dept) => (
              <DeptTreeNode
                key={dept.id}
                dept={dept}
                level={0}
                selectedId={selectedDept?.id ?? null}
                expandedIds={expandedIds}
                searchKeyword={searchKeyword}
                onToggle={toggleExpand}
                onSelect={setSelectedDept}
              />
            ))
          )}
        </div>
      </div>

      {/* Right Pane: Department Details */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {selectedDept ? (
          <>
            {/* Header */}
            <div className="border-border shrink-0 border-b px-8 py-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-muted-foreground mb-2 flex items-center gap-2 text-sm">
                    <Building2 className="h-4 w-4" />
                    <span>部门详情</span>
                  </div>
                  <h1 className="text-foreground text-2xl font-bold">
                    {selectedDept.name}
                  </h1>
                  <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">
                    {/* EAI-CUSTOM: truthiness check via .length (not `??`) — description can legitimately be "" (create form defaults to ""), placeholder must still show */}
                    {selectedDept.description?.length
                      ? selectedDept.description
                      : "暂无描述信息"}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openEditModal(selectedDept)}
                  >
                    <Pencil className="mr-1.5 h-4 w-4" />
                    编辑
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDelete(selectedDept.id)}
                    className="text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="mr-1.5 h-4 w-4" />
                    删除
                  </Button>
                </div>
              </div>

              <div className="mt-8 grid grid-cols-3 gap-6">
                <div className="bg-muted/50 border-border rounded-xl border p-4">
                  <div className="text-muted-foreground mb-1 flex items-center gap-2 text-sm">
                    <Building2 className="h-4 w-4" /> 上级部门
                  </div>
                  <div className="text-foreground font-medium">
                    {parentName}
                  </div>
                </div>
                <div className="bg-muted/50 border-border rounded-xl border p-4">
                  <div className="text-muted-foreground mb-1 flex items-center gap-2 text-sm">
                    <UserCircle className="h-4 w-4" /> 部门负责人
                  </div>
                  <div className="text-foreground font-medium">
                    {selectedDept.leader_name ??
                      (selectedDept.leader_id
                        ? users.find((u) => u.id === selectedDept.leader_id)
                            ?.username
                        : "未设置")}
                  </div>
                </div>
                <div className="bg-muted/50 border-border rounded-xl border p-4">
                  <div className="text-muted-foreground mb-1 flex items-center gap-2 text-sm">
                    <Users className="h-4 w-4" /> 成员数量
                  </div>
                  <div className="text-foreground font-medium">
                    {memberUsers.length} 人
                  </div>
                </div>
              </div>
            </div>

            {/* Members */}
            <div className="bg-muted/20 flex-1 overflow-y-auto p-8">
              <div className="bg-card border-border rounded-2xl border p-8 text-center shadow-sm">
                <div className="bg-muted text-muted-foreground mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                  <Users className="h-8 w-8" />
                </div>
                <h3 className="text-foreground mb-2 text-lg font-medium">
                  部门成员管理
                </h3>
                <p className="text-muted-foreground mx-auto mb-6 max-w-md">
                  当前部门共有{" "}
                  <span className="text-foreground font-semibold">
                    {memberUsers.length}
                  </span>{" "}
                  名成员。点击下方按钮查看成员列表，或前往用户管理页面调整成员归属。
                </p>
                <div className="flex items-center justify-center gap-3">
                  <button
                    onClick={() => setIsMembersModalOpen(true)}
                    className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors"
                  >
                    <Users className="h-4 w-4" />
                    查看成员
                  </button>
                  <Link
                    href="/admin/users"
                    className="text-foreground bg-background border-input hover:bg-muted rounded-lg border px-4 py-2 text-sm font-medium shadow-sm transition-colors"
                  >
                    前往用户管理
                  </Link>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="text-muted-foreground flex flex-1 items-center justify-center">
            <div className="text-center">
              <Building2 className="mx-auto mb-3 h-12 w-12 opacity-50" />
              <p>请选择一个部门查看详情</p>
            </div>
          </div>
        )}
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {isCreateModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsCreateModalOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="bg-background relative w-full max-w-lg overflow-hidden rounded-2xl shadow-xl"
            >
              <div className="border-border flex items-center justify-between border-b px-6 py-4">
                <h3 className="text-foreground text-lg font-semibold">
                  新建部门
                </h3>
                <button
                  onClick={() => setIsCreateModalOpen(false)}
                  className="text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg p-2 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <form onSubmit={handleCreate} className="space-y-4 p-6">
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    上级部门
                  </label>
                  <AdminSelect
                    value={createFormData.parent_id ?? ROOT_DEPARTMENT_OPTION}
                    onChange={(val) =>
                      setCreateFormData({
                        ...createFormData,
                        parent_id:
                          val === ROOT_DEPARTMENT_OPTION ? undefined : val,
                      })
                    }
                    options={[
                      { value: ROOT_DEPARTMENT_OPTION, label: "无 (顶级部门)" },
                      ...flatList.map(({ dept, level }) => ({
                        value: dept.id,
                        label: "—".repeat(level) + dept.name,
                      })),
                    ]}
                  />
                </div>
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    部门名称 <span className="text-destructive">*</span>
                  </label>
                  <Input
                    placeholder="部门名称"
                    value={createFormData.name}
                    onChange={(e) =>
                      setCreateFormData({
                        ...createFormData,
                        name: e.target.value,
                      })
                    }
                    required
                  />
                </div>
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    部门描述
                  </label>
                  <textarea
                    rows={3}
                    placeholder="请输入部门描述（选填）"
                    value={createFormData.description ?? ""}
                    onChange={(e) =>
                      setCreateFormData({
                        ...createFormData,
                        description: e.target.value,
                      })
                    }
                    className="bg-background border-input focus:ring-primary/50 focus:border-primary w-full resize-none rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    部门负责人
                  </label>
                  <AdminSelect
                    value={createFormData.leader_id ?? UNSET_LEADER_OPTION}
                    onChange={(val) =>
                      setCreateFormData({
                        ...createFormData,
                        leader_id:
                          val === UNSET_LEADER_OPTION ? undefined : val,
                      })
                    }
                    options={[
                      { value: UNSET_LEADER_OPTION, label: "未设置" },
                      ...users.map((u) => ({ value: u.id, label: u.username })),
                    ]}
                  />
                </div>
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    排序
                  </label>
                  <Input
                    type="number"
                    value={createFormData.sort_order}
                    onChange={(e) =>
                      setCreateFormData({
                        ...createFormData,
                        sort_order: parseInt(e.target.value) || 0,
                      })
                    }
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      部门编码
                    </label>
                    <Input
                      placeholder="如：DEPT001"
                      value={createFormData.code ?? ""}
                      onChange={(e) =>
                        setCreateFormData({
                          ...createFormData,
                          code: e.target.value || undefined,
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      状态
                    </label>
                    <AdminSelect
                      value={createFormData.status ?? "active"}
                      onChange={(val) =>
                        setCreateFormData({ ...createFormData, status: val })
                      }
                      options={[
                        { value: "active", label: "正常" },
                        { value: "inactive", label: "停用" },
                      ]}
                    />
                  </div>
                </div>
                <DialogFooter className="gap-2 pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setIsCreateModalOpen(false)}
                  >
                    取消
                  </Button>
                  <Button type="submit">创建</Button>
                </DialogFooter>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Members Modal */}
      <AnimatePresence>
        {isMembersModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsMembersModalOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="bg-background relative flex max-h-[80vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl shadow-xl"
            >
              <div className="border-border flex shrink-0 items-center justify-between border-b px-6 py-4">
                <div>
                  <h3 className="text-foreground text-lg font-semibold">
                    部门成员
                  </h3>
                  <p className="text-muted-foreground mt-0.5 text-sm">
                    {selectedDept?.name} · 共 {memberUsers.length} 人
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-foreground mr-2 flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={includeSubDepts}
                      onChange={(e) => setIncludeSubDepts(e.target.checked)}
                      className="border-input focus:ring-primary/30 h-4 w-4 rounded focus:ring-2 focus:ring-offset-0"
                    />
                    含子部门
                  </label>
                  <button
                    onClick={() => setIsMembersModalOpen(false)}
                    className="text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg p-2 transition-colors"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                {memberUsers.length === 0 ? (
                  <div className="text-muted-foreground flex flex-col items-center justify-center py-12">
                    <Users className="mb-3 h-12 w-12 opacity-40" />
                    <p className="text-sm">暂无成员</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {memberUsers.map((u) => (
                      <div
                        key={u.id}
                        className="border-border hover:bg-accent flex items-center gap-3 rounded-xl border p-3 transition-colors"
                      >
                        <div className="bg-primary/10 text-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold">
                          {(u.full_name ?? u.username).charAt(0).toUpperCase()}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-foreground truncate text-sm font-medium">
                            {u.full_name ?? u.username}
                          </div>
                          <div className="text-muted-foreground truncate text-xs">
                            {u.email}
                          </div>
                        </div>
                        <span
                          className={cn(
                            "shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium",
                            u.status === "active"
                              ? "bg-success/10 text-success"
                              : "bg-secondary text-muted-foreground",
                          )}
                        >
                          {u.status === "active" ? "正常" : "停用"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="bg-muted border-border flex shrink-0 items-center justify-between border-t px-6 py-4">
                <Link
                  href="/admin/users"
                  className="text-primary hover:text-primary/80 text-sm font-medium transition-colors"
                >
                  前往用户管理 →
                </Link>
                <button
                  onClick={() => setIsMembersModalOpen(false)}
                  className="text-foreground bg-background border-input hover:bg-accent rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
                >
                  关闭
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Edit Modal */}
      <AnimatePresence>
        {isEditModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsEditModalOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="bg-background relative w-full max-w-lg overflow-hidden rounded-2xl shadow-xl"
            >
              <div className="border-border flex items-center justify-between border-b px-6 py-4">
                <h3 className="text-foreground text-lg font-semibold">
                  编辑部门
                </h3>
                <button
                  onClick={() => setIsEditModalOpen(false)}
                  className="text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg p-2 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="space-y-4 p-6">
                <div className="grid grid-cols-2 gap-4">
                  <div className="w-full">
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      部门名称
                    </label>
                    <Input
                      className="w-full"
                      value={editFormData.name}
                      onChange={(e) =>
                        setEditFormData({
                          ...editFormData,
                          name: e.target.value,
                        })
                      }
                      placeholder="部门名称"
                    />
                  </div>
                  <div className="w-full">
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      部门负责人
                    </label>
                    <AdminSelect
                      className="w-full"
                      value={editFormData.leader_id ?? UNSET_LEADER_OPTION}
                      onChange={(val) =>
                        setEditFormData({
                          ...editFormData,
                          leader_id:
                            val === UNSET_LEADER_OPTION ? undefined : val,
                        })
                      }
                      options={[
                        { value: UNSET_LEADER_OPTION, label: "未设置" },
                        ...users.map((u) => ({
                          value: u.id,
                          label: u.username,
                        })),
                      ]}
                    />
                  </div>
                  <div className="w-full">
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      排序
                    </label>
                    <Input
                      className="w-full"
                      type="number"
                      value={editFormData.sort_order}
                      onChange={(e) =>
                        setEditFormData({
                          ...editFormData,
                          sort_order: parseInt(e.target.value) || 0,
                        })
                      }
                    />
                  </div>
                  <div className="w-full">
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      部门编码
                    </label>
                    <Input
                      className="w-full"
                      value={editFormData.code ?? ""}
                      onChange={(e) =>
                        setEditFormData({
                          ...editFormData,
                          code: e.target.value || undefined,
                        })
                      }
                      placeholder="如：DEPT001"
                    />
                  </div>
                </div>
                <div className="w-full">
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    状态
                  </label>
                  <AdminSelect
                    className="w-full"
                    value={editFormData.status ?? "active"}
                    onChange={(val) =>
                      setEditFormData({ ...editFormData, status: val })
                    }
                    options={[
                      { value: "active", label: "正常" },
                      { value: "inactive", label: "停用" },
                    ]}
                  />
                </div>
                <div className="w-full">
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    部门描述
                  </label>
                  <textarea
                    rows={3}
                    placeholder="请输入部门描述（选填）"
                    value={editFormData.description ?? ""}
                    onChange={(e) =>
                      setEditFormData({
                        ...editFormData,
                        description: e.target.value,
                      })
                    }
                    className="bg-background border-input focus:ring-primary/50 focus:border-primary w-full resize-none rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                  />
                </div>
              </div>
              <div className="bg-muted border-border flex items-center justify-end gap-3 border-t px-6 py-4">
                <Button
                  variant="outline"
                  onClick={() => setIsEditModalOpen(false)}
                >
                  取消
                </Button>
                <Button onClick={handleUpdate}>保存</Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </main>
  );
}
