"use client";

import { format } from "date-fns";
import { zhCN } from "date-fns/locale";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Plus,
  Edit,
  Trash2,
  Filter,
  UserCheck,
  UserX,
  X,
  UserCircle,
  Mail,
  Building2,
  Shield,
  Lock,
  Phone,
  Hash,
  Calendar as CalendarIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { userApi, roleApi, deptApi } from "@/extensions/api";
import type {
  User,
  Role,
  Department,
  CreateUserRequest,
  UpdateUserRequest,
} from "@/extensions/types";
import { cn } from "@/lib/utils";

function flattenDepts(depts: Department[]): Department[] {
  return depts.reduce((acc: Department[], dept) => {
    acc.push(dept);
    if (dept.children?.length) acc.push(...flattenDepts(dept.children));
    return acc;
  }, []);
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterDept, setFilterDept] = useState<string>("all");
  const [filterRole, setFilterRole] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<"all" | "active" | "inactive">("all");

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [passwordUser, setPasswordUser] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [hireDatePopoverOpen, setHireDatePopoverOpen] = useState(false);

  const [formData, setFormData] = useState({
    username: "",
    password: "",
    full_name: "",
    email: "",
    phone: "",
    emp_no: "",
    hire_date: "",
    dept_ids: [] as string[],
    role_id: "",
    status: "active" as "active" | "inactive",
  });

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [usersRes, rolesRes, deptsRes] = await Promise.all([
        userApi.list({
          limit: 500,
          dept_id: filterDept && filterDept !== "all" ? filterDept : undefined,
          role_id: filterRole && filterRole !== "all" ? filterRole : undefined,
          status: filterStatus && filterStatus !== "all" ? filterStatus : undefined,
        }),
        roleApi.list(),
        deptApi.list(),
      ]);
      setUsers(usersRes.users);
      setRoles(rolesRes.roles);
      setDepartments(deptsRes.departments);
    } catch (err) {
      console.error("Failed to load data:", err);
    } finally {
      setIsLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void loadData(); }, [filterDept, filterRole, filterStatus]);

  const filteredUsers = users.filter((user) => {
    const matchesSearch =
      (user.full_name ?? user.username).toLowerCase().includes(searchQuery.toLowerCase()) ||
      user.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (user.email ?? "").toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSearch;
  });

  const flatDepts = flattenDepts(departments);

  const getDepartmentName = (id?: string) => {
    if (!id) return "-";
    const dept = flatDepts.find((d) => d.id === id);
    return dept?.name ?? "-";
  };

  const getRoleName = (id?: string) => {
    if (!id) return "-";
    const role = roles.find((r) => r.id === id);
    return role?.name ?? "-";
  };

  const handleOpenModal = (user?: User) => {
    if (user) {
      setEditingUser(user);
      setFormData({
        username: user.username,
        password: "",
        full_name: user.full_name ?? "",
        email: user.email ?? "",
        phone: user.phone ?? "",
        emp_no: user.emp_no ?? "",
        hire_date: user.hire_date ?? "",
        dept_ids: user.dept_ids ?? (user.dept_id ? [user.dept_id] : []),
        role_id: user.role_id ?? "",
        status: user.status as "active" | "inactive",
      });
    } else {
      setEditingUser(null);
      setFormData({
        username: "",
        password: "",
        full_name: "",
        email: "",
        phone: "",
        emp_no: "",
        hire_date: "",
        dept_ids: [],
        role_id: roles[0]?.id ?? "",
        status: "active",
      });
    }
    setIsModalOpen(true);
  };

  const handleSaveUser = async () => {
    if (!formData.username.trim() || !formData.full_name.trim() || !formData.email.trim()) return;
    if (!editingUser && !formData.password.trim()) return;

    try {
      if (editingUser) {
        const updateData: UpdateUserRequest = {
          email: formData.email,
          full_name: formData.full_name,
          dept_id: formData.dept_ids[0],
          role_id: formData.role_id || undefined,
          status: formData.status,
          phone: formData.phone || undefined,
          emp_no: formData.emp_no || undefined,
          hire_date: formData.hire_date || undefined,
          dept_ids: formData.dept_ids.length > 0 ? formData.dept_ids : undefined,
        };
        if (formData.password) {
          await userApi.resetPassword(editingUser.id, formData.password);
        }
        await userApi.update(editingUser.id, updateData);
      } else {
        const createData: CreateUserRequest = {
          username: formData.username,
          password: formData.password,
          email: formData.email,
          full_name: formData.full_name,
          dept_id: formData.dept_ids[0],
          role_id: formData.role_id || undefined,
          phone: formData.phone || undefined,
          emp_no: formData.emp_no || undefined,
          hire_date: formData.hire_date || undefined,
          dept_ids: formData.dept_ids.length > 0 ? formData.dept_ids : undefined,
        };
        await userApi.create(createData);
      }
      setIsModalOpen(false);
      void loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "操作失败");
    }
  };

  const handleDeleteUser = async (id: string) => {
    if (!confirm("确定要删除该用户吗？此操作不可恢复。")) return;
    try {
      await userApi.delete(id);
      void loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "删除失败");
    }
  };

  const toggleUserStatus = async (user: User) => {
    const newStatus = user.status === "active" ? "inactive" : "active";
    try {
      await userApi.update(user.id, { status: newStatus });
      void loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "更新状态失败");
    }
  };

  const openPasswordDialog = (user: User) => {
    setPasswordUser(user);
    setNewPassword("");
    setShowPasswordDialog(true);
  };

  const handleResetPassword = async () => {
    if (!passwordUser || !newPassword) return;
    try {
      await userApi.resetPassword(passwordUser.id, newPassword);
      alert("密码重置成功");
      setShowPasswordDialog(false);
      setPasswordUser(null);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "重置密码失败");
    }
  };

  if (isLoading) {
    return (
      <main className="h-full flex flex-col overflow-hidden max-w-[1600px] w-full mx-auto bg-background">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-muted-foreground">加载中...</div>
        </div>
      </main>
    );
  }

  return (
    <main className="h-full flex flex-col overflow-hidden max-w-[1600px] w-full mx-auto bg-background">
      {/* Header & Controls */}
      <div className="px-8 py-6 border-b border-border shrink-0">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-foreground">用户管理</h1>
            <p className="text-muted-foreground mt-1 text-sm">管理企业内所有用户的账号、部门归属及角色权限。</p>
          </div>
          <button
            onClick={() => handleOpenModal()}
            className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm shadow-sm flex items-center gap-2"
          >
            <Plus className="w-4 h-4" /> 添加用户
          </button>
        </div>

        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="搜索姓名或邮箱..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-muted border border-input rounded-lg focus:bg-background focus:border-primary focus:ring-2 focus:ring-primary/20 text-sm transition-all outline-none"
            />
          </div>

          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <AdminSelect
              value={filterDept}
              onChange={setFilterDept}
              options={[
                { value: "all", label: "所有部门" },
                ...flatDepts.map((d) => ({ value: d.id, label: d.name })),
              ]}
              className="w-36"
            />

            <AdminSelect
              value={filterRole}
              onChange={setFilterRole}
              options={[
                { value: "all", label: "所有角色" },
                ...roles.map((r) => ({ value: r.id, label: r.name })),
              ]}
              className="w-36"
            />

            <AdminSelect
              value={filterStatus}
              onChange={(val) => setFilterStatus(val as "all" | "active" | "inactive")}
              options={[
                { value: "all", label: "所有状态" },
                { value: "active", label: "正常" },
                { value: "inactive", label: "停用" },
              ]}
              className="w-32"
            />
          </div>
        </div>
      </div>

      {/* User Table */}
      <div className="flex-1 overflow-auto p-8 bg-muted/30">
        <div className="bg-background border border-border rounded-xl shadow-sm overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider">用户信息</th>
                <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider">部门</th>
                <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider">角色</th>
                <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider">状态</th>
                <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider">最后登录</th>
                <th className="py-3 px-6 text-xs font-semibold text-muted-foreground uppercase tracking-wider text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredUsers.length > 0 ? (
                filteredUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-muted/50 transition-colors group">
                    <td className="py-4 px-6">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold shrink-0">
                          {(user.full_name ?? user.username).charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div className="font-medium text-foreground">
                            {user.full_name ?? user.username}
                            <span className="text-muted-foreground font-normal ml-1.5 text-xs">@{user.username}</span>
                          </div>
                          <div className="text-sm text-muted-foreground">{user.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-4 px-6">
                      {user.dept_ids && user.dept_ids.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-muted text-foreground text-sm">
                            <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
                            {getDepartmentName(user.primary_dept_id ?? user.dept_ids[0])}
                          </div>
                          {user.dept_ids.length > 1 && (
                            <span className="inline-flex items-center px-2 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
                              +{user.dept_ids.length - 1}
                            </span>
                          )}
                        </div>
                      ) : (
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-muted text-foreground text-sm">
                          <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
                          {getDepartmentName(user.dept_id)}
                        </div>
                      )}
                    </td>
                    <td className="py-4 px-6">
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-primary/10 text-primary text-sm">
                        <Shield className="w-3.5 h-3.5 text-primary" />
                        {getRoleName(user.role_id)}
                      </div>
                    </td>
                    <td className="py-4 px-6">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
                          user.status === "active" ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
                        )}
                      >
                        <span className={cn("w-1.5 h-1.5 rounded-full", user.status === "active" ? "bg-success" : "bg-muted-foreground")} />
                        {user.status === "active" ? "正常" : "已停用"}
                      </span>
                    </td>
                    <td className="py-4 px-6 text-sm text-muted-foreground">
                      {user.last_login_at
                        ? new Date(user.last_login_at).toLocaleString("zh-CN")
                        : "-"}
                    </td>
                    <td className="py-4 px-6 text-right">
                      <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => toggleUserStatus(user)}
                          className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
                          title={user.status === "active" ? "停用账号" : "启用账号"}
                        >
                          {user.status === "active" ? <UserX className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
                        </button>
                        <button
                          onClick={() => handleOpenModal(user)}
                          className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-md transition-colors"
                          title="编辑用户"
                        >
                          <Edit className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => openPasswordDialog(user)}
                          className="p-1.5 text-muted-foreground hover:text-warning hover:bg-warning/10 rounded-md transition-colors"
                          title="重置密码"
                        >
                          <Lock className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteUser(user.id)}
                          className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                          title="删除用户"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-muted-foreground">
                    <div className="flex flex-col items-center justify-center">
                      <UserCircle className="w-12 h-12 text-muted-foreground mb-3" />
                      <p>没有找到匹配的用户</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create/Edit Modal */}
      <AnimatePresence>
        {isModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsModalOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-background rounded-2xl shadow-xl w-full max-w-lg overflow-hidden"
            >
              <div className="px-6 py-4 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">
                  {editingUser ? "编辑用户" : "添加用户"}
                </h3>
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-6 space-y-5">
                <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      登录账号 <span className="text-destructive">*</span>
                    </label>
                    <div className="relative">
                      <UserCircle className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="text"
                        value={formData.username}
                        onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                        disabled={!!editingUser}
                        className="w-full pl-9 pr-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary disabled:bg-muted disabled:text-muted-foreground"
                        placeholder="例如：zhangsan"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      登录密码 {!editingUser && <span className="text-destructive">*</span>}
                    </label>
                    <div className="relative">
                      <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="password"
                        value={formData.password}
                        onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                        className="w-full pl-9 pr-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
                        placeholder={editingUser ? "留空表示不修改" : "设置初始密码"}
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      姓名 <span className="text-destructive">*</span>
                    </label>
                    <div className="relative">
                      <UserCircle className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="text"
                        value={formData.full_name}
                        onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                        className="w-full pl-9 pr-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
                        placeholder="例如：张三"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      邮箱 <span className="text-destructive">*</span>
                    </label>
                    <div className="relative">
                      <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="email"
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        className="w-full pl-9 pr-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
                        placeholder="zhangsan@example.com"
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">手机号码</label>
                    <div className="relative">
                      <Phone className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="tel"
                        value={formData.phone}
                        onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                        className="w-full pl-9 pr-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
                        placeholder="138xxxx"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">工号</label>
                    <div className="relative">
                      <Hash className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="text"
                        value={formData.emp_no}
                        onChange={(e) => setFormData({ ...formData, emp_no: e.target.value })}
                        className="w-full pl-9 pr-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
                        placeholder="EMP001"
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">入职日期</label>
                    <Popover open={hireDatePopoverOpen} onOpenChange={setHireDatePopoverOpen}>
                      <PopoverTrigger asChild>
                        <button
                          type="button"
                          className="relative w-full flex items-center justify-start pl-9 pr-3 py-2 bg-background border border-input rounded-lg hover:border-input hover:bg-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
                        >
                          <CalendarIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                          <span className={formData.hire_date ? "text-foreground" : "text-muted-foreground"}>
                            {formData.hire_date ? format(new Date(formData.hire_date), "yyyy年MM月dd日", { locale: zhCN }) : "选择日期"}
                          </span>
                        </button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0 bg-background border border-border shadow-lg rounded-lg" align="start">
                        <Calendar
                          mode="single"
                          selected={formData.hire_date ? new Date(formData.hire_date) : undefined}
                          onSelect={(date) => {
                            if (date) {
                              setFormData({ ...formData, hire_date: format(date, "yyyy-MM-dd") });
                              setHireDatePopoverOpen(false);
                            }
                          }}
                          initialFocus
                          locale={zhCN}
                        />
                      </PopoverContent>
                    </Popover>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">所属部门（可多选）</label>
                    <div className="flex flex-wrap gap-2 mb-2">
                      {formData.dept_ids.map((deptId) => (
                        <span
                          key={deptId}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-sm"
                        >
                          {getDepartmentName(deptId)}
                          <button
                            type="button"
                            onClick={() => setFormData({
                              ...formData,
                              dept_ids: formData.dept_ids.filter((id) => id !== deptId),
                            })}
                            className="ml-1 hover:text-primary/80"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                    <AdminSelect
                      value=""
                      onChange={(val) => {
                        if (val && !formData.dept_ids.includes(val)) {
                          setFormData({ ...formData, dept_ids: [...formData.dept_ids, val] });
                        }
                      }}
                      options={flatDepts
                        .filter((d) => !formData.dept_ids.includes(d.id))
                        .map((d) => ({ value: d.id, label: d.name }))}
                      placeholder="添加部门..."
                      className="w-full"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">分配角色</label>
                    <AdminSelect
                      value={formData.role_id}
                      onChange={(val) => setFormData({ ...formData, role_id: val })}
                      options={roles.map((r) => ({ value: r.id, label: r.name }))}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-foreground mb-2">账号状态</label>
                    <div className="flex h-10 w-full items-center gap-4 rounded-lg border border-input bg-background px-3">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="status"
                          value="active"
                          checked={formData.status === "active"}
                          onChange={() => setFormData({ ...formData, status: "active" })}
                          className="text-primary focus:ring-primary"
                        />
                        <span className="text-sm text-foreground">正常</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="status"
                          value="inactive"
                          checked={formData.status === "inactive"}
                          onChange={() => setFormData({ ...formData, status: "inactive" })}
                          className="text-primary focus:ring-primary"
                        />
                        <span className="text-sm text-foreground">停用</span>
                      </label>
                    </div>
                  </div>
                </div>
              </div>

              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-end gap-3">
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-foreground bg-background border border-input rounded-lg hover:bg-muted transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleSaveUser}
                  disabled={!formData.username.trim() || !formData.full_name.trim() || !formData.email.trim() || (!editingUser && !formData.password.trim())}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 transition-colors shadow-sm disabled:opacity-50"
                >
                  {editingUser ? "保存更改" : "确认添加"}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Reset Password Dialog */}
      <AnimatePresence>
        {showPasswordDialog && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setShowPasswordDialog(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-background rounded-2xl shadow-xl w-full max-w-sm overflow-hidden"
            >
              <div className="px-6 py-4 border-b border-border flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">
                  重置密码 - {passwordUser?.username}
                </h3>
                <button
                  onClick={() => setShowPasswordDialog(false)}
                  className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6">
                <label className="block text-sm font-medium text-foreground mb-1">新密码</label>
                <input
                  type="password"
                  placeholder="请输入新密码"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
                />
              </div>
              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-end gap-3">
                <button
                  onClick={() => setShowPasswordDialog(false)}
                  className="px-4 py-2 text-sm font-medium text-foreground bg-background border border-input rounded-lg hover:bg-muted transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleResetPassword}
                  disabled={!newPassword}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 transition-colors shadow-sm disabled:opacity-50"
                >
                  确定重置
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </main>
  );
}
