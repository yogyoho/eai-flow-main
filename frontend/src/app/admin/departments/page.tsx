"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Plus,
  RefreshCw,
  Pencil,
  Trash2,
  ChevronRight,
  ChevronDown,
  Building2,
  Users,
  UserCircle,
  X,
} from "lucide-react";
import { useEffect, useState, useMemo } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { deptApi, userApi } from "@/extensions/api";
import type { Department, CreateDepartmentRequest, UpdateDepartmentRequest, User } from "@/extensions/types";
import { cn } from "@/lib/utils";

function flattenDepts(depts: Department[], level = 0): { dept: Department; level: number }[] {
  return depts.reduce((acc, dept) => {
    acc.push({ dept, level });
    if (dept.children?.length) {
      acc.push(...flattenDepts(dept.children, level + 1));
    }
    return acc;
  }, [] as { dept: Department; level: number }[]);
}

function findParentName(tree: Department[], parentId: string | undefined): string {
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

interface TreeNodeProps {
  dept: Department;
  level: number;
  selectedId: string | null;
  expandedIds: Set<string>;
  searchKeyword: string;
  onToggle: (id: string) => void;
  onSelect: (dept: Department) => void;
}

function DeptTreeNode({ dept, level, selectedId, expandedIds, searchKeyword, onToggle, onSelect }: TreeNodeProps) {
  const hasChildren = dept.children && dept.children.length > 0;
  const isExpanded = expandedIds.has(dept.id);
  const isSelected = selectedId === dept.id;
  const matchSearch = !searchKeyword || dept.name.toLowerCase().includes(searchKeyword.toLowerCase());
  const visibleChildren = dept.children?.filter((c) => !searchKeyword || c.name.toLowerCase().includes(searchKeyword.toLowerCase())) ?? [];

  const showNode = matchSearch || (hasChildren && visibleChildren.length > 0);
  if (!showNode) return null;

  return (
    <div className="select-none">
      <div
        className={cn(
          "flex items-center gap-1 py-2 px-3 rounded-lg cursor-pointer transition-colors text-sm",
          isSelected ? "bg-primary/10 text-primary font-medium" : "text-foreground hover:bg-accent"
        )}
        style={{ paddingLeft: `${level * 1.5 + 0.75}rem` }}
        onClick={() => onSelect(dept)}
      >
        <div
          className={cn("w-5 h-5 flex items-center justify-center mr-1", hasChildren ? "cursor-pointer text-muted-foreground hover:text-foreground" : "opacity-0")}
          onClick={(e) => {
            e.stopPropagation();
            if (hasChildren) onToggle(dept.id);
          }}
        >
          {hasChildren ? (isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />) : null}
        </div>
        <Building2 className={cn("w-4 h-4 mr-2", isSelected ? "text-primary" : "text-muted-foreground")} />
        <span className="truncate flex-1">{dept.name}</span>
      </div>
      {hasChildren && isExpanded &&
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
  const [createFormData, setCreateFormData] = useState<CreateDepartmentRequest>({
    name: "",
    description: "",
    parent_id: undefined,
    leader_id: undefined,
    sort_order: 0,
    code: undefined,
    status: "active",
  });
  const [editFormData, setEditFormData] = useState<UpdateDepartmentRequest>({
    name: "",
    description: "",
    sort_order: 0,
    leader_id: undefined,
    code: undefined,
    status: undefined,
  });

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [deptsRes, usersRes] = await Promise.all([
        deptApi.list(),
        userApi.list({ limit: 1000 }),
      ]);
      setDepartments(deptsRes.departments);
      setUsers(usersRes.users);
      if (deptsRes.departments.length > 0 && expandedIds.size === 0) {
        setExpandedIds(new Set(deptsRes.departments.map((d) => d.id)));
      }
      if (deptsRes.departments.length > 0) {
        const flat = flattenDepts(deptsRes.departments);
        setSelectedDept((prev) =>
          prev
            ? (flat.find((x) => x.dept.id === prev.id)?.dept ?? prev)
            : (deptsRes.departments[0] ?? null)
        );
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const flatList = useMemo(() => flattenDepts(departments), [departments]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await deptApi.create(createFormData);
      setIsCreateModalOpen(false);
      setCreateFormData({ name: "", description: "", parent_id: undefined, leader_id: undefined, sort_order: 0 });
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "创建失败");
    }
  };

  const handleUpdate = async () => {
    if (!selectedDept) return;
    try {
      await deptApi.update(selectedDept.id, editFormData);
      setIsEditModalOpen(false);
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "更新失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定要删除该部门吗？")) return;
    try {
      await deptApi.delete(id);
      if (selectedDept?.id === id) setSelectedDept(null);
      loadData();
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

  const parentName = selectedDept ? findParentName(departments, selectedDept.parent_id) : "—";

  const formatDate = (s: string) => {
    try {
      const d = new Date(s);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    } catch {
      return s;
    }
  };

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
      <main className="flex-1 flex items-center justify-center bg-background">
        <div className="text-muted-foreground">加载中...</div>
      </main>
    );
  }

  return (
    <main className="h-full flex overflow-hidden max-w-[1600px] w-full mx-auto bg-background">
      {/* Left Pane: Department Tree */}
      <div className="w-80 border-r border-border bg-muted/30 flex flex-col shrink-0">
        <div className="p-4 border-b border-border bg-card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-foreground">组织架构</h2>
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
              className="p-1.5 bg-primary/10 text-primary rounded-md hover:bg-primary/20 transition-colors"
              title="新建子部门"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="搜索部门..."
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-secondary border-transparent focus:bg-background focus:border-primary focus:ring-2 focus:ring-primary/20 rounded-lg text-sm transition-all outline-none"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {departments.length === 0 ? (
            <div className="text-sm text-muted-foreground py-4 text-center">暂无部门</div>
          ) : searchKeyword ? (
            <div className="space-y-1">
              {flattenDepts(departments)
                .filter(({ dept }) =>
                  dept.name.toLowerCase().includes(searchKeyword.toLowerCase())
                )
                .map(({ dept }) => (
                  <button
                    key={dept.id}
                    onClick={() => setSelectedDept(dept)}
                    className={cn(
                      "w-full text-left flex items-center py-2 px-3 rounded-lg transition-colors text-sm",
                      selectedDept?.id === dept.id
                        ? "bg-primary/10 text-primary font-medium"
                        : "text-foreground hover:bg-accent"
                    )}
                  >
                    <Building2
                      className={cn(
                        "w-4 h-4 mr-2 shrink-0",
                        selectedDept?.id === dept.id ? "text-primary" : "text-muted-foreground"
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="truncate">{dept.name}</div>
                      {dept.parent_id && (
                        <div className="text-xs text-muted-foreground truncate">
                          {findParentName(departments, dept.parent_id)}
                        </div>
                      )}
                    </div>
                  </button>
                ))}
              {flattenDepts(departments).filter(({ dept }) =>
                dept.name.toLowerCase().includes(searchKeyword.toLowerCase())
              ).length === 0 && (
                <div className="text-sm text-muted-foreground py-4 text-center">未找到匹配部门</div>
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
      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedDept ? (
          <>
            {/* Header */}
            <div className="px-8 py-6 border-b border-border shrink-0">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                    <Building2 className="w-4 h-4" />
                    <span>部门详情</span>
                  </div>
                  <h1 className="text-2xl font-bold text-foreground">{selectedDept.name}</h1>
                  <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">
                    {selectedDept.description || "暂无描述信息"}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openEditModal(selectedDept)}
                  >
                    <Pencil className="w-4 h-4 mr-1.5" />
                    编辑
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDelete(selectedDept.id)}
                    className="text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="w-4 h-4 mr-1.5" />
                    删除
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-6 mt-8">
                <div className="bg-muted/50 rounded-xl p-4 border border-border">
                  <div className="text-sm text-muted-foreground mb-1 flex items-center gap-2">
                    <Building2 className="w-4 h-4" /> 上级部门
                  </div>
                  <div className="font-medium text-foreground">{parentName}</div>
                </div>
                <div className="bg-muted/50 rounded-xl p-4 border border-border">
                  <div className="text-sm text-muted-foreground mb-1 flex items-center gap-2">
                    <UserCircle className="w-4 h-4" /> 部门负责人
                  </div>
                  <div className="font-medium text-foreground">
                    {selectedDept.leader_name ||
                      (selectedDept.leader_id
                        ? users.find((u) => u.id === selectedDept.leader_id)?.username
                        : "未设置")}
                  </div>
                </div>
                <div className="bg-muted/50 rounded-xl p-4 border border-border">
                  <div className="text-sm text-muted-foreground mb-1 flex items-center gap-2">
                    <Users className="w-4 h-4" /> 成员数量
                  </div>
                  <div className="font-medium text-foreground">{memberUsers.length} 人</div>
                </div>
              </div>
            </div>

            {/* Members */}
            <div className="flex-1 overflow-y-auto p-8 bg-muted/20">
              <div className="bg-card rounded-2xl border border-border shadow-sm p-8 text-center">
                <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4 text-muted-foreground">
                  <Users className="w-8 h-8" />
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">部门成员管理</h3>
                <p className="text-muted-foreground max-w-md mx-auto mb-6">
                  当前部门共有 <span className="font-semibold text-foreground">{memberUsers.length}</span> 名成员。点击下方按钮查看成员列表，或前往用户管理页面调整成员归属。
                </p>
                <div className="flex items-center justify-center gap-3">
                  <button
                    onClick={() => setIsMembersModalOpen(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm shadow-sm"
                  >
                    <Users className="w-4 h-4" />
                    查看成员
                  </button>
                  <a
                    href="/admin/users"
                    className="px-4 py-2 text-sm font-medium text-foreground bg-background border border-input rounded-lg hover:bg-muted transition-colors shadow-sm"
                  >
                    前往用户管理
                  </a>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Building2 className="w-12 h-12 mx-auto mb-3 opacity-50" />
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
              className="relative bg-background rounded-2xl shadow-xl w-full max-w-lg overflow-hidden"
            >
              <div className="px-6 py-4 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">新建部门</h3>
                <button
                  onClick={() => setIsCreateModalOpen(false)}
                  className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <form onSubmit={handleCreate} className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">上级部门</label>
                  <AdminSelect
                    value={createFormData.parent_id || ""}
                    onChange={(val) => setCreateFormData({ ...createFormData, parent_id: val || undefined })}
                    options={[
                      { value: "", label: "无 (顶级部门)" },
                      ...flatList.map(({ dept, level }) => ({
                        value: dept.id,
                        label: "—".repeat(level) + dept.name,
                      })),
                    ]}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">
                    部门名称 <span className="text-destructive">*</span>
                  </label>
                  <Input
                    placeholder="部门名称"
                    value={createFormData.name}
                    onChange={(e) => setCreateFormData({ ...createFormData, name: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">部门描述</label>
                  <textarea
                    rows={3}
                    placeholder="请输入部门描述（选填）"
                    value={createFormData.description ?? ""}
                    onChange={(e) => setCreateFormData({ ...createFormData, description: e.target.value })}
                    className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary text-sm resize-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">部门负责人</label>
                  <AdminSelect
                    value={createFormData.leader_id || ""}
                    onChange={(val) => setCreateFormData({ ...createFormData, leader_id: val || undefined })}
                    options={[
                      { value: "", label: "未设置" },
                      ...users.map((u) => ({ value: u.id, label: u.username })),
                    ]}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">排序</label>
                  <Input
                    type="number"
                    value={createFormData.sort_order}
                    onChange={(e) => setCreateFormData({ ...createFormData, sort_order: parseInt(e.target.value) || 0 })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">部门编码</label>
                    <Input
                      placeholder="如：DEPT001"
                      value={createFormData.code ?? ""}
                      onChange={(e) => setCreateFormData({ ...createFormData, code: e.target.value || undefined })}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">状态</label>
                    <AdminSelect
                      value={createFormData.status || "active"}
                      onChange={(val) => setCreateFormData({ ...createFormData, status: val })}
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
                  <Button
                    type="submit"
                  >
                    创建
                  </Button>
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
              className="relative bg-background rounded-2xl shadow-xl w-full max-w-xl max-h-[80vh] overflow-hidden flex flex-col"
            >
              <div className="px-6 py-4 border-b border-border flex items-center justify-between shrink-0">
                <div>
                  <h3 className="text-lg font-semibold text-foreground">部门成员</h3>
                  <p className="text-sm text-muted-foreground mt-0.5">{selectedDept?.name} · 共 {memberUsers.length} 人</p>
                </div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer mr-2">
                    <input
                      type="checkbox"
                      checked={includeSubDepts}
                      onChange={(e) => setIncludeSubDepts(e.target.checked)}
                      className="w-4 h-4 rounded border-input focus:ring-2 focus:ring-primary/30 focus:ring-offset-0"
                    />
                    含子部门
                  </label>
                  <button
                    onClick={() => setIsMembersModalOpen(false)}
                    className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                {memberUsers.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                    <Users className="w-12 h-12 mb-3 opacity-40" />
                    <p className="text-sm">暂无成员</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {memberUsers.map((u) => (
                      <div
                        key={u.id}
                        className="flex items-center gap-3 p-3 rounded-xl border border-border hover:bg-accent transition-colors"
                      >
                        <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm shrink-0">
                          {(u.full_name || u.username).charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-foreground text-sm truncate">
                            {u.full_name || u.username}
                          </div>
                          <div className="text-xs text-muted-foreground truncate">{u.email}</div>
                        </div>
                        <span className={cn(
                          "text-xs px-1.5 py-0.5 rounded-full font-medium shrink-0",
                          u.status === "active" ? "bg-success/10 text-success" : "bg-secondary text-muted-foreground"
                        )}>
                          {u.status === "active" ? "正常" : "停用"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-between shrink-0">
                <a
                  href="/admin/users"
                  className="text-sm text-primary hover:text-primary/80 font-medium transition-colors"
                >
                  前往用户管理 →
                </a>
                <button
                  onClick={() => setIsMembersModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-foreground bg-background border border-input rounded-lg hover:bg-accent transition-colors"
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
              className="relative bg-background rounded-2xl shadow-xl w-full max-w-lg overflow-hidden"
            >
              <div className="px-6 py-4 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">编辑部门</h3>
                <button
                  onClick={() => setIsEditModalOpen(false)}
                  className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">部门名称</label>
                  <Input
                    value={editFormData.name}
                    onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
                    placeholder="部门名称"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">部门描述</label>
                  <textarea
                    rows={3}
                    placeholder="请输入部门描述（选填）"
                    value={editFormData.description ?? ""}
                    onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
                    className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary text-sm resize-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">部门负责人</label>
                  <AdminSelect
                    value={editFormData.leader_id || ""}
                    onChange={(val) => setEditFormData({ ...editFormData, leader_id: val || undefined })}
                    options={[
                      { value: "", label: "未设置" },
                      ...users.map((u) => ({ value: u.id, label: u.username })),
                    ]}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">排序</label>
                  <Input
                    type="number"
                    value={editFormData.sort_order}
                    onChange={(e) => setEditFormData({ ...editFormData, sort_order: parseInt(e.target.value) || 0 })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">部门编码</label>
                    <Input
                      value={editFormData.code ?? ""}
                      onChange={(e) => setEditFormData({ ...editFormData, code: e.target.value || undefined })}
                      placeholder="如：DEPT001"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">状态</label>
                    <AdminSelect
                      value={editFormData.status || "active"}
                      onChange={(val) => setEditFormData({ ...editFormData, status: val })}
                      options={[
                        { value: "active", label: "正常" },
                        { value: "inactive", label: "停用" },
                      ]}
                    />
                  </div>
                </div>
              </div>
              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-end gap-3">
                <Button
                  variant="outline"
                  onClick={() => setIsEditModalOpen(false)}
                >
                  取消
                </Button>
                <Button
                  onClick={handleUpdate}
                >
                  保存
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </main>
  );
}
