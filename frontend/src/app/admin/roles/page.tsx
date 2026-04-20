"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Search, Plus, Shield, Lock, Pencil, Trash2, Users, X,
  ChevronRight, ChevronDown, Brain, Database, Puzzle, Wrench,
  Settings, Key,
} from "lucide-react";
import { useEffect, useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageLoadingOverlay } from "@/components/ui/page-loading-overlay";
import { Textarea } from "@/components/ui/textarea";
import { roleApi, userApi } from "@/extensions/api";
import type { Role, CreateRoleRequest, UpdateRoleRequest, User } from "@/extensions/types";
import { cn } from "@/lib/utils";

const PERMISSION_CATEGORIES = [
  {
    name: "Model Access", icon: Brain,
    permissions: [
      { key: "model:read", label: "View Models" },
      { key: "model:create", label: "Create Model Config" },
      { key: "model:update", label: "Update Model Config" },
      { key: "model:delete", label: "Delete Model Config" },
    ],
  },
  {
    name: "Knowledge & Data", icon: Database,
    permissions: [
      { key: "kb:read", label: "View Knowledge Base" },
      { key: "kb:create", label: "Create Knowledge Base" },
      { key: "kb:update", label: "Update Knowledge Base" },
      { key: "kb:delete", label: "Delete Knowledge Base" },
      { key: "doc:read", label: "View Documents" },
      { key: "doc:upload", label: "Upload Documents" },
      { key: "doc:delete", label: "Delete Documents" },
    ],
  },
  {
    name: "Plugins & Tools", icon: Puzzle,
    permissions: [
      { key: "skill:read", label: "View Skills" },
      { key: "skill:install", label: "Install Skills" },
      { key: "skill:uninstall", label: "Uninstall Skills" },
    ],
  },
  {
    name: "System & Admin", icon: Wrench,
    permissions: [
      { key: "user:read", label: "View Users" },
      { key: "user:create", label: "Create Users" },
      { key: "user:update", label: "Update Users" },
      { key: "user:delete", label: "Delete Users" },
      { key: "role:read", label: "View Roles" },
      { key: "role:create", label: "Create Roles" },
      { key: "role:update", label: "Update Roles" },
      { key: "role:delete", label: "Delete Roles" },
      { key: "dept:read", label: "View Departments" },
      { key: "dept:create", label: "Create Departments" },
      { key: "dept:update", label: "Update Departments" },
      { key: "dept:delete", label: "Delete Departments" },
      { key: "system:*", label: "All System Permissions" },
    ],
  },
];

const ALL_PERMS = PERMISSION_CATEGORIES.flatMap((c) => c.permissions.map((p) => p.key));

function PermissionPanel({
  selected, onChange, readonly = false, compact = false,
}: {
  selected: string[];
  onChange: (perms: string[]) => void;
  readonly?: boolean;
  compact?: boolean;
}) {
  const [expandedCats, setExpandedCats] = useState<Set<string>>(
    new Set(PERMISSION_CATEGORIES.map((c) => c.name))
  );

  const toggleCat = (name: string) =>
    setExpandedCats((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });

  const togglePerm = (key: string) => {
    if (readonly) return;
    onChange(selected.includes(key) ? selected.filter((p) => p !== key) : [...selected, key]);
  };

  const toggleCategory = (keys: string[]) => {
    if (readonly) return;
    const allSelected = keys.every((k) => selected.includes(k));
    if (allSelected) onChange(selected.filter((p) => !keys.includes(p)));
    else onChange([...new Set([...selected, ...keys])]);
  };

  return (
    <div className="space-y-3">
      {!readonly && (
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onChange(ALL_PERMS)}
          >
            Select All
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onChange([])}
          >
            Clear All
          </Button>
        </div>
      )}
      {PERMISSION_CATEGORIES.map((category) => {
        const Icon = category.icon;
        const isExpanded = expandedCats.has(category.name);
        const catKeys = category.permissions.map((p) => p.key);
        const selectedCount = selected.filter((p) => catKeys.includes(p)).length;
        const allCatSelected = catKeys.every((k) => selected.includes(k));

        return (
          <div key={category.name} className="bg-background rounded-xl border border-border overflow-hidden">
            <div className="flex items-center w-full">
              <button type="button" onClick={() => toggleCat(category.name)}
                className="flex-1 flex items-center gap-3 p-4 hover:bg-muted transition-colors text-left">
                <div className="w-8 h-8 bg-background rounded-lg shadow-sm border border-border flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4 text-muted-foreground" />
                </div>
                <div>
                  <div className="font-medium text-foreground text-sm">{category.name}</div>
                  <div className="text-xs text-muted-foreground">{selectedCount}/{category.permissions.length} selected</div>
                </div>
                <div className="ml-auto mr-2">
                  {isExpanded ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
                </div>
              </button>
              {!readonly && (
                <button type="button" onClick={() => toggleCategory(catKeys)}
                  className={cn("px-3 py-1.5 mr-3 text-xs font-medium rounded-md transition-colors shrink-0",
                    allCatSelected ? "bg-primary/10 text-primary hover:bg-primary/20" : "bg-muted text-muted-foreground hover:bg-muted/80"
                  )}>
                  {allCatSelected ? "Deselect" : "Select All"}
                </button>
              )}
            </div>
            <AnimatePresence>
              {isExpanded && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
                  <div className="px-4 pb-4 grid gap-1" style={{ gridTemplateColumns: compact ? "repeat(auto-fill, minmax(140px, 1fr))" : "repeat(auto-fill, minmax(180px, 1fr))" }}>
                    {category.permissions.map((perm) => (
                      <label key={perm.key}
                        className={cn("flex items-center gap-2 text-sm text-foreground p-2 rounded-lg transition-colors min-w-0",
                          readonly ? "cursor-default" : "cursor-pointer hover:bg-muted"
                        )}>
                        <input type="checkbox"
                          checked={selected.includes(perm.key)}
                          onChange={() => togglePerm(perm.key)}
                          disabled={readonly}
                          className="w-4 h-4 shrink-0 rounded border-input focus:ring-2 focus:ring-ring/50 focus:ring-offset-0 disabled:opacity-50"
                        />
                        <span className={cn("truncate", readonly ? "text-muted-foreground" : "")}>{perm.label}</span>
                      </label>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

export default function AdminRolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"permissions" | "users">("permissions");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [roleUsers, setRoleUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);

  const [createForm, setCreateForm] = useState<CreateRoleRequest>({
    name: "", code: "", permissions: [], description: "", level: 10, parent_role_id: undefined,
  });
  const [editForm, setEditForm] = useState<{ name: string; description: string; permissions: string[]; level?: number; parent_role_id?: string }>({
    name: "", description: "", permissions: [],
  });

  const loadData = async () => {
    setIsLoading(true);
    try {
      const res = await roleApi.list();
      setRoles(res.roles);
      setSelectedRole((prev) =>
        prev
          ? (res.roles.find((r) => r.id === prev.id) ?? prev)
          : (res.roles[0] ?? null)
      );
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const filteredRoles = searchQuery
    ? roles.filter((r) =>
        r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.code || "").toLowerCase().includes(searchQuery.toLowerCase())
      )
    : roles;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await roleApi.create(createForm);
      setIsCreateModalOpen(false);
      setCreateForm({ name: "", code: "", permissions: [], description: "" });
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Create failed");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this role?")) return;
    try {
      await roleApi.delete(id);
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const openEditModal = (role: Role) => {
    setEditForm({
      name: role.name,
      description: role.description || "",
      permissions: role.permissions ?? [],
      level: role.level,
      parent_role_id: role.parent_role_id,
    });
    setIsEditModalOpen(true);
  };

  const handleEdit = async () => {
    if (!selectedRole) return;
    try {
      await roleApi.update(selectedRole.id, editForm);
      setIsEditModalOpen(false);
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Update failed");
    }
  };

  const loadRoleUsers = async (role: Role) => {
    setUsersLoading(true);
    try {
      const res = await userApi.list({ limit: 500, role_id: role.id });
      setRoleUsers(res.users);
    } catch {
      setRoleUsers([]);
    } finally {
      setUsersLoading(false);
    }
  };

  const handleSelectRole = (role: Role) => {
    setSelectedRole(role);
    setActiveTab("permissions");
    setRoleUsers([]);
  };

  const handleTabChange = (tab: "permissions" | "users") => {
    setActiveTab(tab);
    if (tab === "users" && selectedRole && roleUsers.length === 0 && !usersLoading) {
      loadRoleUsers(selectedRole);
    }
  };

  if (isLoading) {
    return <PageLoadingOverlay text="Loading" />;
  }

  return (
    <main className="h-full flex overflow-hidden max-w-[1600px] w-full mx-auto bg-background">
      {/* Left Sidebar */}
      <div className="w-80 border-r border-border bg-muted/50 flex flex-col shrink-0">
        <div className="p-4 border-b border-border bg-background">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-foreground">Role List</h2>
            <Button
              variant="secondary"
              size="icon"
              onClick={() => setIsCreateModalOpen(true)}
              title="New Role"
            >
              <Plus className="w-4 h-4 text-primary" />
            </Button>
          </div>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search roles..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 bg-muted border-transparent focus:border-ring focus:ring-ring/50"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {filteredRoles.length === 0 ? (
            <div className="text-sm text-muted-foreground py-4 text-center">No roles</div>
          ) : (
            filteredRoles.map((role) => {
              const isSelected = selectedRole?.id === role.id;
              return (
                <button key={role.id} onClick={() => handleSelectRole(role)}
                  className={cn(
                    "w-full text-left p-3 rounded-xl transition-all duration-200 border",
                    isSelected
                      ? "bg-background border-primary/50 shadow-sm ring-1 ring-primary/10"
                      : "border-transparent hover:bg-muted"
                  )}>
                  <div className="flex items-center justify-between mb-1">
                    <span className={cn("font-medium text-sm truncate", isSelected ? "text-primary" : "text-foreground")}>
                      {role.name}
                    </span>
                    {role.is_system && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-200 text-muted-foreground font-medium shrink-0 ml-1">System</span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground line-clamp-1 mb-2 min-h-[1rem]">
                    {role.description || <span className="text-muted-foreground/50">No description</span>}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Users className="w-3 h-3" /> —
                    </span>
                    <span className="flex items-center gap-1">
                      <Key className="w-3 h-3" /> {role.permissions?.length ?? 0} perms
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Right Side */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedRole ? (
          <>
            <div className="px-8 pt-6 shrink-0">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                    <Settings className="w-4 h-4" />
                    <span>Role Details</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <h1 className="text-2xl font-bold text-foreground tracking-tight">{selectedRole.name}</h1>
                    <span className="text-xs px-2 py-1 rounded-md bg-muted text-muted-foreground font-medium border border-border font-mono">
                      {selectedRole.code}
                    </span>
                    {selectedRole.is_system && (
                      <span className="flex items-center gap-1 text-xs font-medium text-warning bg-warning/10 px-2 py-1 rounded-full border border-warning/50">
                        <Lock className="w-3 h-3" /> System role, read-only
                      </span>
                    )}
                  </div>
                  {selectedRole.description && (
                    <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">{selectedRole.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {!selectedRole.is_system && (
                    <>
                      <Button
                        variant="outline"
                        onClick={() => openEditModal(selectedRole)}
                        className="gap-1.5"
                      >
                        <Pencil className="w-4 h-4" /> Edit
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => handleDelete(selectedRole.id)}
                        className="gap-1.5 text-destructive border-destructive/50 hover:bg-destructive/10"
                      >
                        <Trash2 className="w-4 h-4" /> Delete
                      </Button>
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-6 mt-4 border-b border-border px-8 -mx-8">
                <button onClick={() => handleTabChange("permissions")}
                  className={cn("pb-3 text-sm font-medium transition-colors relative",
                    activeTab === "permissions" ? "text-primary" : "text-muted-foreground hover:text-foreground")}>
                  Permissions
                  {activeTab === "permissions" && (
                    <motion.div layoutId="roleActiveTab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
                  )}
                </button>
                <button onClick={() => handleTabChange("users")}
                  className={cn("pb-3 text-sm font-medium transition-colors relative",
                    activeTab === "users" ? "text-primary" : "text-muted-foreground hover:text-foreground")}>
                  Users{activeTab === "users" ? ` (${usersLoading ? "..." : roleUsers.length})` : ""}
                  {activeTab === "users" && (
                    <motion.div layoutId="roleActiveTab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
                  )}
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-8 bg-muted/30">
              <AnimatePresence mode="wait">
                {activeTab === "permissions" ? (
                  <motion.div key="permissions" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} className="w-full">
                    {selectedRole.is_system && (
                      <p className="text-xs text-muted-foreground mb-4">System role permissions are read-only</p>
                    )}
                    <PermissionPanel
                      selected={selectedRole.permissions ?? []}
                      readonly={selectedRole.is_system}
                      onChange={async (perms) => {
                        try {
                          await roleApi.update(selectedRole.id, { permissions: perms });
                          loadData();
                        } catch (err: unknown) {
                          alert(err instanceof Error ? err.message : "Update permission failed");
                        }
                      }}
                    />
                  </motion.div>
                ) : (
                  <motion.div key="users" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
                    {usersLoading ? (
                      <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">Loading...</div>
                    ) : roleUsers.length === 0 ? (
                      <div className="bg-background rounded-2xl border border-border shadow-sm p-8 text-center max-w-lg mx-auto">
                        <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4 text-muted-foreground">
                          <Users className="w-8 h-8" />
                        </div>
                        <h3 className="text-base font-medium text-foreground mb-2">No users assigned</h3>
                        <p className="text-muted-foreground text-sm mb-6">No users currently have the &quot;{selectedRole.name}&quot; role.</p>
                        <a href="/admin/users"
                          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm shadow-sm">
                          Go to User Management
                        </a>
                      </div>
                    ) : (
                      <div className="max-w-3xl">
                        <div className="grid grid-cols-2 gap-3 mb-6">
                          {roleUsers.map((user) => (
                            <div key={user.id}
                              className="flex items-center gap-3 p-3 rounded-xl bg-background border border-border hover:shadow-sm transition-all">
                              <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm shrink-0">
                                {(user.full_name || user.username).charAt(0).toUpperCase()}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="font-medium text-foreground text-sm truncate">{user.full_name || user.username}</div>
                                <div className="text-xs text-muted-foreground truncate">{user.email}</div>
                              </div>
                              <span className={cn("text-xs px-1.5 py-0.5 rounded-full font-medium shrink-0",
                                user.status === "active" ? "bg-success/10 text-success" : "bg-muted text-muted-foreground")}>
                                {user.status === "active" ? "Active" : "Inactive"}
                              </span>
                            </div>
                          ))}
                        </div>
                        <div className="text-center">
                          <a href="/admin/users"
                            className="text-sm text-primary hover:text-primary/80 font-medium transition-colors">
                            Go to User Management
                          </a>
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Select a role to view details</p>
            </div>
          </div>
        )}
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {isCreateModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 bg-foreground/40 backdrop-blur-sm"
              onClick={() => setIsCreateModalOpen(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-background rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
              <div className="px-6 py-4 border-b border-border flex items-center justify-between shrink-0">
                <h3 className="text-lg font-semibold text-foreground">Create Role</h3>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setIsCreateModalOpen(false)}
                >
                  <X className="w-5 h-5 text-muted-foreground" />
                </Button>
              </div>
              <form onSubmit={handleCreate} className="p-6 space-y-5 overflow-y-auto flex-1">
                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      Role Name <span className="text-destructive">*</span>
                    </label>
                    <Input placeholder="e.g. Admin" value={createForm.name}
                      onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })} required />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      Role Code <span className="text-destructive">*</span>
                    </label>
                    <Input placeholder="e.g. admin" value={createForm.code}
                      onChange={(e) => setCreateForm({ ...createForm, code: e.target.value })} required />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Description</label>
                  <Textarea
                    rows={2}
                    placeholder="Role description (optional)"
                    value={createForm.description || ""}
                    onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                    className="resize-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">Permissions</label>
                  <PermissionPanel selected={createForm.permissions ?? []}
                    compact
                    onChange={(perms) => setCreateForm({ ...createForm, permissions: perms })} />
                </div>
              </form>
              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-end gap-3 shrink-0">
                <Button
                  variant="outline"
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  onClick={handleCreate}
                >
                  Create Role
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
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 bg-foreground/40 backdrop-blur-sm"
              onClick={() => setIsEditModalOpen(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-background rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
              <div className="px-6 py-4 border-b border-border flex items-center justify-between shrink-0">
                <h3 className="text-lg font-semibold text-foreground">Edit Role — {selectedRole?.name}</h3>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setIsEditModalOpen(false)}
                >
                  <X className="w-5 h-5 text-muted-foreground" />
                </Button>
              </div>
              <div className="p-6 space-y-5 overflow-y-auto flex-1">
                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Role Name</label>
                    <Input value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Role Code</label>
                    <Input value={selectedRole?.code || ""} disabled
                      className="bg-muted text-muted-foreground cursor-not-allowed" />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Description</label>
                  <Textarea
                    rows={2}
                    placeholder="Role description (optional)"
                    value={editForm.description || ""}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                    className="resize-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Level</label>
                    <Input
                      type="number"
                      value={editForm.level ?? 10}
                      onChange={(e) => setEditForm({ ...editForm, level: parseInt(e.target.value) || 10 })}
                      min="1"
                      max="100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Parent Role</label>
                    <AdminSelect
                      value={editForm.parent_role_id || ""}
                      onValueChange={(value) => setEditForm({ ...editForm, parent_role_id: value || undefined })}
                      options={roles
                        .filter((r) => r.id !== selectedRole?.id)
                        .map((r) => ({ value: r.id, label: `${r.name} (Lv.${r.level})` }))}
                      placeholder="None"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">Permissions</label>
                  <PermissionPanel selected={editForm.permissions}
                    compact
                    onChange={(perms) => setEditForm({ ...editForm, permissions: perms })} />
                </div>
              </div>
              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-end gap-3 shrink-0">
                <Button
                  variant="outline"
                  onClick={() => setIsEditModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button onClick={handleEdit}>
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
