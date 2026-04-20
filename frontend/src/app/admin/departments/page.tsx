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
import { Textarea } from "@/components/ui/textarea";
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
  if (!parentId) return "-";
  const flat = flattenDepts(tree);
  const p = flat.find((x) => x.dept.id === parentId);
  return p?.dept.name ?? "-";
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
          isSelected ? "bg-primary/10 text-primary font-medium" : "text-foreground hover:bg-muted"
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

  useEffect(() => { loadData(); }, []);

  const flatList = useMemo(() => flattenDepts(departments), [departments]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await deptApi.create(createFormData);
      setIsCreateModalOpen(false);
      setCreateFormData({ name: "", description: "", parent_id: undefined, leader_id: undefined, sort_order: 0 });
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Create failed");
    }
  };

  const handleUpdate = async () => {
    if (!selectedDept) return;
    try {
      await deptApi.update(selectedDept.id, editFormData);
      setIsEditModalOpen(false);
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Update failed");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this department?")) return;
    try {
      await deptApi.delete(id);
      if (selectedDept?.id === id) setSelectedDept(null);
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
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

  const parentName = selectedDept ? findParentName(departments, selectedDept.parent_id) : "-";

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
        <div className="text-muted-foreground">Loading...</div>
      </main>
    );
  }

  return (
    <main className="h-full flex overflow-hidden max-w-[1600px] w-full mx-auto bg-background">
      {/* Left Pane: Department Tree */}
      <div className="w-80 border-r border-border bg-muted/50 flex flex-col shrink-0">
        <div className="p-4 border-b border-border bg-background">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-foreground">Organization</h2>
            <Button
              variant="secondary"
              size="icon"
              className="text-primary"
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
              title="New Sub-department"
            >
              <Plus className="w-4 h-4" />
            </Button>
          </div>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search departments..."
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-muted border-transparent focus:bg-background focus:border-primary focus:ring-2 focus:ring-ring/50 rounded-lg text-sm transition-all outline-none"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {departments.length === 0 ? (
            <div className="text-sm text-muted-foreground py-4 text-center">No departments</div>
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
                        : "text-foreground hover:bg-muted"
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
                <div className="text-sm text-muted-foreground py-4 text-center">No matching departments</div>
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
            <div className="px-8 py-6 border-b border-border shrink-0">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                    <Building2 className="w-4 h-4" />
                    <span>Department Details</span>
                  </div>
                  <h1 className="text-2xl font-bold text-foreground">{selectedDept.name}</h1>
                  <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">
                    {selectedDept.description || "No description"}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openEditModal(selectedDept)}
                    className="text-foreground border-border hover:text-foreground hover:bg-muted"
                  >
                    <Pencil className="w-4 h-4 mr-1.5" />
                    Edit
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDelete(selectedDept.id)}
                    className="text-destructive border-border hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="w-4 h-4 mr-1.5" />
                    Delete
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-6 mt-8">
                <div className="bg-zinc-50 rounded-xl p-4 border border-border">
                  <div className="text-sm text-muted-foreground mb-1 flex items-center gap-2">
                    <Building2 className="w-4 h-4" /> Parent Department
                  </div>
                  <div className="font-medium text-foreground">{parentName}</div>
                </div>
                <div className="bg-zinc-50 rounded-xl p-4 border border-border">
                  <div className="text-sm text-muted-foreground mb-1 flex items-center gap-2">
                    <UserCircle className="w-4 h-4" /> Department Head
                  </div>
                  <div className="font-medium text-foreground">
                    {selectedDept.leader_name ||
                      (selectedDept.leader_id
                        ? users.find((u) => u.id === selectedDept.leader_id)?.username
                        : "Not set")}
                  </div>
                </div>
                <div className="bg-zinc-50 rounded-xl p-4 border border-border">
                  <div className="text-sm text-muted-foreground mb-1 flex items-center gap-2">
                    <Users className="w-4 h-4" /> Members
                  </div>
                  <div className="font-medium text-foreground">{memberUsers.length} people</div>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-8 bg-muted/30">
              <div className="bg-background rounded-2xl border border-border shadow-sm p-8 text-center">
                <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4 text-muted-foreground">
                  <Users className="w-8 h-8" />
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">Department Members</h3>
                <p className="text-muted-foreground max-w-md mx-auto mb-6">
                  This department has <span className="font-semibold text-foreground">{memberUsers.length}</span> members. Click below to view the member list or go to User Management to adjust members.
                </p>
                <div className="flex items-center justify-center gap-3">
                  <Button
                    onClick={() => setIsMembersModalOpen(true)}
                    className="gap-2"
                  >
                    <Users className="w-4 h-4" />
                    View Members
                  </Button>
                  <a
                    href="/admin/users"
                    className="px-4 py-2 text-sm font-medium text-foreground bg-background border border-input rounded-lg hover:bg-muted transition-colors shadow-sm"
                  >
                    Go to User Management
                  </a>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Building2 className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>Select a department to view details</p>
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
                <h3 className="text-lg font-semibold text-foreground">Create Department</h3>
                <button
                  onClick={() => setIsCreateModalOpen(false)}
                  className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <form onSubmit={handleCreate} className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Parent Department</label>
                  <AdminSelect
                    value={createFormData.parent_id || ""}
                    onChange={(val) => setCreateFormData({ ...createFormData, parent_id: val || undefined })}
                    options={[
                      { value: "", label: "None (Top-level)" },
                      ...flatList.map(({ dept, level }) => ({
                        value: dept.id,
                        label: "—".repeat(level) + dept.name,
                      })),
                    ]}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">
                    Name <span className="text-destructive">*</span>
                  </label>
                  <Input
                    placeholder="Department name"
                    value={createFormData.name}
                    onChange={(e) => setCreateFormData({ ...createFormData, name: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Description</label>
                  <Textarea
                    rows={3}
                    placeholder="Department description (optional)"
                    value={createFormData.description ?? ""}
                    onChange={(e) => setCreateFormData({ ...createFormData, description: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Department Head</label>
                  <AdminSelect
                    value={createFormData.leader_id || ""}
                    onChange={(val) => setCreateFormData({ ...createFormData, leader_id: val || undefined })}
                    options={[
                      { value: "", label: "Not set" },
                      ...users.map((u) => ({ value: u.id, label: u.username })),
                    ]}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Sort Order</label>
                  <Input
                    type="number"
                    value={createFormData.sort_order}
                    onChange={(e) => setCreateFormData({ ...createFormData, sort_order: parseInt(e.target.value) || 0 })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Code</label>
                    <Input
                      placeholder="e.g. DEPT001"
                      value={createFormData.code ?? ""}
                      onChange={(e) => setCreateFormData({ ...createFormData, code: e.target.value || undefined })}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Status</label>
                    <AdminSelect
                      value={createFormData.status || "active"}
                      onChange={(val) => setCreateFormData({ ...createFormData, status: val })}
                      options={[
                        { value: "active", label: "Active" },
                        { value: "inactive", label: "Inactive" },
                      ]}
                    />
                  </div>
                </div>
                <DialogFooter className="gap-2 pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setIsCreateModalOpen(false)}
                    className="border-input text-foreground hover:bg-muted"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                  >
                    Create
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
                  <h3 className="text-lg font-semibold text-foreground">Department Members</h3>
                  <p className="text-sm text-muted-foreground mt-0.5">{selectedDept?.name} · {memberUsers.length} members</p>
                </div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer mr-2">
                    <input
                      type="checkbox"
                      checked={includeSubDepts}
                      onChange={(e) => setIncludeSubDepts(e.target.checked)}
                      className="w-4 h-4 rounded border-input focus:ring-2 focus:ring-ring/50 focus:ring-offset-0"
                    />
                    Include sub-depts
                  </label>
                  <button
                    onClick={() => setIsMembersModalOpen(false)}
                    className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                {memberUsers.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                    <Users className="w-12 h-12 mb-3 text-muted-foreground/50" />
                    <p className="text-sm">No members</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {memberUsers.map((u) => (
                      <div
                        key={u.id}
                        className="flex items-center gap-3 p-3 rounded-xl border border-border hover:bg-muted transition-colors"
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
                          u.status === "active" ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
                        )}>
                          {u.status === "active" ? "Active" : "Inactive"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-between shrink-0">
                <a
                  href="/admin/users"
                  className="text-sm text-primary hover:text-primary font-medium transition-colors"
                >
                  Go to User Management
                </a>
                <Button
                  variant="outline"
                  onClick={() => setIsMembersModalOpen(false)}
                >
                  Close
                </Button>
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
                <h3 className="text-lg font-semibold text-foreground">Edit Department</h3>
                <button
                  onClick={() => setIsEditModalOpen(false)}
                  className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Name</label>
                  <Input
                    value={editFormData.name}
                    onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
                    placeholder="Department name"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Description</label>
                  <Textarea
                    rows={3}
                    placeholder="Department description (optional)"
                    value={editFormData.description ?? ""}
                    onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Department Head</label>
                  <AdminSelect
                    value={editFormData.leader_id || ""}
                    onChange={(val) => setEditFormData({ ...editFormData, leader_id: val || undefined })}
                    options={[
                      { value: "", label: "Not set" },
                      ...users.map((u) => ({ value: u.id, label: u.username })),
                    ]}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Sort Order</label>
                  <Input
                    type="number"
                    value={editFormData.sort_order}
                    onChange={(e) => setEditFormData({ ...editFormData, sort_order: parseInt(e.target.value) || 0 })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Code</label>
                    <Input
                      value={editFormData.code ?? ""}
                      onChange={(e) => setEditFormData({ ...editFormData, code: e.target.value || undefined })}
                      placeholder="e.g. DEPT001"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Status</label>
                    <AdminSelect
                      value={editFormData.status || "active"}
                      onChange={(val) => setEditFormData({ ...editFormData, status: val })}
                      options={[
                        { value: "active", label: "Active" },
                        { value: "inactive", label: "Inactive" },
                      ]}
                    />
                  </div>
                </div>
              </div>
              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-end gap-3">
                <Button
                  variant="outline"
                  onClick={() => setIsEditModalOpen(false)}
                  className="border-input text-foreground hover:bg-muted"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleUpdate}
                >
                  Save
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </main>
  );
}
