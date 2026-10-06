import { useEffect, useState } from "react";

/**
 * 本地权限门 (S2 Task 1, EAI-CUSTOM).
 *
 * 替代主系统 @/core/permissions 的 PermissionProvider + usePermission：
 * GET /api/permissions/me（同源 cookie，经 dev proxy 打到主系统 nginx :2026）
 * → 返回 { canPage, isLoading, loginUrl }，canPage 语义对齐主系统
 * （pages 数组 + "*" 通配 + 加载中 fail-open）。
 *
 * 401/请求失败 → 视为无权限但**不跳登录**：调用方（OntologyPage）渲染
 * "无访问权限 + 前往主系统登录"空态，登录按钮 href 指向主系统 /login。
 */

const PERMISSIONS_ME_URL = "/api/permissions/me";
const PAGE_ID = "ontology:page:map";

/** 主系统入口：dev 独立跑在 :3010，主系统在 nginx :2026；可用 VITE_MAIN_APP_URL 覆盖。 */
const MAIN_APP_URL: string =
  (import.meta.env.VITE_MAIN_APP_URL as string | undefined) ??
  "http://localhost:2026";

export const MAIN_LOGIN_URL = `${MAIN_APP_URL}/login`;

interface PermissionsMeResponse {
  permissions?: string[];
  nav?: string[];
  pages?: string[];
  is_admin?: boolean;
  /** EAI-CUSTOM (2026-10-06): 身份展示字段（侧栏账户区，替代此前硬编码）。 */
  email?: string | null;
  full_name?: string | null;
  dept_name?: string | null;
}

export interface MeIdentity {
  email: string;
  fullName: string;
  deptName: string;
  /** 头像字：full_name → email → username 依次取首字符。 */
  avatarChar: string;
}

export interface PermissionGate {
  /** 页面可见性判定（签名对齐主系统 usePermission.canPage；加载中 fail-open）。 */
  canPage: (pageId: string) => boolean;
  /** 通用权限点判定（B1: ontology:review/model/governance/export）；加载中 fail-open；is_admin 短路。 */
  can: (permission: string) => boolean;
  isLoading: boolean;
  /** 预检的页面 id（本体页固定 ontology:page:map）。 */
  pageId: string;
  /** 当前用户展示身份（未知字段回退空串，调用方自行兜底）。 */
  me: MeIdentity;
}

// 模块级单次拉取：整个 SPA 只打一次 /me，避免多调用方重复请求
let mePromise: Promise<PermissionsMeResponse> | null = null;

function fetchPermissionsMe(): Promise<PermissionsMeResponse> {
  if (!mePromise) {
    mePromise = fetch(PERMISSIONS_ME_URL, {
      credentials: "include",
    }).then(async (res) => {
      if (!res.ok) {
        // 401/403/5xx 一律降级为空权限（对齐主系统 PermissionProvider 的 fail-closed 语义）
        return {};
      }
      return (await res.json()) as PermissionsMeResponse;
    });
    // 失败不缓存——网络抖动恢复后下次挂载可重试
    mePromise.catch(() => {
      mePromise = null;
    });
  }
  return mePromise;
}

export function usePermission(): PermissionGate {
  const [pages, setPages] = useState<string[] | null>(null);
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [me, setMe] = useState<MeIdentity>({
    email: "",
    fullName: "",
    deptName: "",
    avatarChar: "",
  });

  useEffect(() => {
    let cancelled = false;
    fetchPermissionsMe()
      .then((data) => {
        if (cancelled) return;
        setPages(data.pages ?? []);
        setPermissions(data.permissions ?? []);
        setIsAdmin(Boolean(data.is_admin));
        const email = data.email ?? "";
        const fullName = data.full_name ?? "";
        const deptName = data.dept_name ?? "";
        const avatarChar = [...(fullName || email)][0] ?? "";
        setMe({ email, fullName, deptName, avatarChar });
      })
      .catch(() => {
        if (!cancelled) {
          setPages([]);
          setPermissions([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isLoading = pages === null;
  const canPage = (pageId: string): boolean => {
    if (isLoading) return true; // Fail-open: 与主系统一致，加载中先渲染
    if (pages!.includes("*") || isAdmin) return true;
    return pages!.includes(pageId);
  };
  const can = (permission: string): boolean => {
    if (isLoading) return true; // fail-open 与 canPage 同约定
    if (isAdmin || permissions!.includes("*")) return true;
    return permissions!.includes(permission);
  };

  return { canPage, can, isLoading, pageId: PAGE_ID, me };
}

/** OntoStudio 权限点目录（B1, 2026-10-05）——与后端 auth.py PERM_* 一一对应。 */
export const PERM = {
  /** 消解审核：确认/驳回/合并/撤销/批量/CQ 验收运行 */
  REVIEW: "ontology:review",
  /** 建模与抽取：建模器保存/删除、新建/中止抽取任务、推理全量重算 */
  MODEL: "ontology:model",
  /** 治理：全量装载、规则启停、孤儿/零边 mention 清除、快照生成/恢复/删除 */
  GOVERNANCE: "ontology:governance",
  /** 交付物流出：图导出下载、快照内容下载 */
  EXPORT: "ontology:export",
} as const;
