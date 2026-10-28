import {
  Activity,
  Briefcase,
  ChevronRight,
  Database,
  ExternalLink,
  Filter,
  LayoutDashboard,
  ListChecks,
  Menu,
  Search,
  ShieldCheck,
  Workflow,
  X,
} from 'lucide-react'
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'

import { api, setToken, type Identity, type WorkbenchSummary } from './api'
import { Spinner } from './components/ui'
import { ROLE_LABELS, errorText, initials } from './lib/format'
import Approvals from './pages/Approvals'
import MasterData from './pages/MasterData'
import Opportunities from './pages/Opportunities'
import Todos from './pages/Todos'
import Workbench from './pages/Workbench'

interface SessionValue {
  identity: Identity
  summary: WorkbenchSummary
  refresh: () => Promise<void>
}

const SessionContext = createContext<SessionValue | null>(null)

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside AppShell')
  return value
}

const NAV_GROUPS = [
  {
    label: 'A · 作战指挥',
    items: [
      { to: '/', label: '我的工作台', icon: LayoutDashboard, end: true },
      { to: '/todos', label: '统一待办', icon: ListChecks },
      { to: '/approvals', label: '审批中心', icon: ShieldCheck },
    ],
  },
  {
    label: 'C1 · 销售执行',
    items: [{ to: '/opportunities', label: '商机漏斗', icon: Filter }],
  },
  {
    label: '基础能力',
    items: [{ to: '/master-data', label: '销售主数据', icon: Database }],
  },
]

const FUTURE_NAV = [
  { code: 'C2', label: '招标雷达' },
  { code: 'B01', label: '集团全景' },
  { code: 'D01', label: '合同台账' },
  { code: 'E01', label: '尾款作战' },
  { code: 'F01', label: '装机台账' },
]

interface PageMeta {
  title: string
  kicker: string
  subtitle: string
  icon: typeof Briefcase
}

const PAGES: Record<string, PageMeta> = {
  '/': {
    title: '我的工作台',
    kicker: 'A01 · 作战指挥中心',
    subtitle: '角色化卡片 · 阻断优先 · 数据来自当前销售快照',
    icon: Briefcase,
  },
  '/opportunities': {
    title: '商机漏斗',
    kicker: 'C1 · 销售执行',
    subtitle: '九段状态机 · 阶段停留上限 · 规则概率与人工覆盖双源',
    icon: Filter,
  },
  '/todos': {
    title: '统一待办',
    kicker: 'A02 · 作战指挥中心',
    subtitle: '规则事件 / 审批 / 仲裁 / 补录四类合一 · SLA 倒计时 · 超时升级',
    icon: ListChecks,
  },
  '/approvals': {
    title: '审批中心',
    kicker: 'R4 / R6 / 撞单 · Temporal 驱动',
    subtitle: '审批只解除闸门，不直接推进商机；支持自批、转办与超时升级',
    icon: ShieldCheck,
  },
  '/master-data': {
    title: '销售主数据',
    kicker: '本地最小记录 · 明确来源',
    subtitle: '客户集团 / 客户 / 矿井 / 工作面 / 产品 / 联系人 / 示范面',
    icon: Database,
  },
}

function LoginGate({ message }: { message: string }) {
  const [token, setTokenValue] = useState('')
  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="brand-mark large">TM</div>
        <span className="eyebrow">TIANMA SALES · QW2</span>
        <h1>需要 EAI 统一身份</h1>
        <p>{message}</p>
        <p className="muted">
          销售服务复用 EAI 用户、角色与部门，不维护第二套账号。请从 EAI 门户进入，或粘贴带有
          <code> sub </code>与<code> exp </code>的 JWT 进行本地联调。
        </p>
        <textarea
          className="token-input"
          value={token}
          onChange={(event) => setTokenValue(event.target.value)}
          placeholder="eyJhbGciOi..."
          rows={4}
        />
        <button
          type="button"
          className="button primary block"
          onClick={() => {
            setToken(token.trim())
            window.location.reload()
          }}
          disabled={!token.trim()}
        >
          进入销售综合管理平台
        </button>
        <a className="text-link" href="/">
          返回 EAI 门户 <ChevronRight size={14} />
        </a>
      </div>
    </div>
  )
}

function AppShell() {
  const [summary, setSummary] = useState<WorkbenchSummary | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await api.get<WorkbenchSummary>('/workbench/summary')
      setSummary(data)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  const value = useMemo<SessionValue | null>(
    () =>
      summary
        ? {
            identity: summary.identity,
            summary,
            refresh: load,
          }
        : null,
    [summary],
  )

  if (loading) {
    return (
      <div className="app-loading">
        <div className="brand-mark large">TM</div>
        <Spinner label="正在连接销售服务" />
      </div>
    )
  }

  if (!summary || !value) {
    const unauthorized = error.includes('登录') || error.includes('401')
    if (unauthorized) return <LoginGate message={error} />
    return (
      <div className="login-shell">
        <div className="login-card">
          <div className="brand-mark large">TM</div>
          <h1>销售服务暂不可用</h1>
          <p>{error || '无法读取工作台摘要。'}</p>
          <button type="button" className="button primary block" onClick={() => void load()}>
            重试
          </button>
        </div>
      </div>
    )
  }

  const path = location.pathname.replace(/\/$/, '') || '/'
  const page = PAGES[path] || PAGES['/']
  const kicker = kickerParts(page.kicker)
  const PageIcon = page.icon
  const identity = summary.identity
  const roleLabel =
    roleDisplay(identity) || ROLE_LABELS[identity.sales_role] || identity.sales_role || '销售用户'
  const pendingApprovals = summary.metrics.pending_approvals

  return (
    <SessionContext.Provider value={value}>
      <div className="app-shell">
        <aside className={`sidebar ${menuOpen ? 'open' : ''}`}>
          <div className="brand">
            <div className="brand-mark">
              <Activity size={19} />
            </div>
            <div className="brand-copy">
              <strong>天马智控 · 营销中心</strong>
              <span>
                销售综合管理平台 <em>V1.0</em>
              </span>
            </div>
            <button
              type="button"
              className="icon-button sidebar-close"
              onClick={() => setMenuOpen(false)}
              aria-label="关闭导航"
            >
              <X size={18} />
            </button>
          </div>

          <div className="side-search">
            <button type="button" onClick={() => navigate('/opportunities')}>
              <Search size={14} />
              <span>搜索商机、客户、待办</span>
              <kbd>⌘K</kbd>
            </button>
          </div>

          <nav className="side-nav" aria-label="主导航">
            {NAV_GROUPS.map((group) => (
              <div className="nav-group" key={group.label}>
                <div className="nav-label">{group.label}</div>
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                  >
                    <item.icon size={15} />
                    <span>{item.label}</span>
                    {item.to === '/approvals' && pendingApprovals ? (
                      <span className="n-badge">{pendingApprovals}</span>
                    ) : null}
                  </NavLink>
                ))}
              </div>
            ))}

            {summary.workflow_platform_enabled !== false && (identity.is_admin || identity.sales_role === 'sales_admin') ? (
              <div className="nav-group">
                <div className="nav-label">平台管理</div>
                <a className="nav-item" href="/workflow" target="_blank" rel="noreferrer">
                  <Workflow size={15} />
                  <span>流程管理</span>
                  <ExternalLink size={11} style={{ marginLeft: 'auto' }} />
                </a>
              </div>
            ) : null}

            <div className="nav-group">
              <div className="nav-label">后续模块</div>
              {FUTURE_NAV.map((item) => (
                <span className="nav-item future" key={item.code} title="待接入">
                  <span className="future-code">{item.code}</span>
                  <span>{item.label}</span>
                  <em>待接入</em>
                </span>
              ))}
            </div>
          </nav>

          <div className="side-foot">
            <span className="avatar">{initials(identity.display_name)}</span>
            <div className="sf-user">
              <b>{identity.display_name}</b>
              <span>{roleLabel} · {identity.region_code}</span>
            </div>
            <a className="icon-button" href="/temporal/" target="_blank" rel="noreferrer" title="Temporal UI">
              <ExternalLink size={15} />
            </a>
          </div>
        </aside>

        {menuOpen ? <button type="button" className="scrim" onClick={() => setMenuOpen(false)} aria-label="关闭导航" /> : null}

        <div className="workspace">
          <header className="topbar">
            <button type="button" className="icon-button menu-button" onClick={() => setMenuOpen(true)} aria-label="打开导航">
              <Menu size={19} />
            </button>
            <div className="crumb">
              <span>销售综合管理平台</span>
              <i>/</i>
              <b>{page.title}</b>
            </div>
            <span className="live-pill">
              <span className="dot dot-ok" />
              数据快照 · {new Date(summary.data_as_of).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
            </span>
            <div className="top-search">
              <button type="button" onClick={() => navigate('/opportunities')}>
                <Search size={14} />
                <span>搜索商机 / 客户 / 待办</span>
                <kbd>⌘K</kbd>
              </button>
            </div>
            <div className="top-actions">
              <a className="icon-button" href="/temporal/" target="_blank" rel="noreferrer" title="Temporal UI">
                <Activity size={16} />
              </a>
              <span className="top-divider" />
              <div className="user-chip">
                <span className="avatar sm">{initials(identity.display_name)}</span>
                <div>
                  <b>{identity.display_name}</b>
                  <span>{roleLabel} · {scopeLabel(identity.data_scope)}</span>
                </div>
              </div>
            </div>
          </header>

          <main className="content">
            <div className="page">
              <section className="page-head">
                <div className="ph-icon">
                  <PageIcon size={19} />
                </div>
                <div className="ph-title">
                  <div className="ph-title-line">
                    <span className="ph-code">{kicker.code}</span>
                    <h2>{page.title}</h2>
                    {kicker.context ? <span className="ph-context">{kicker.context}</span> : null}
                  </div>
                  <div className="ph-sub">
                    {page.subtitle}
                    <span className="tag">{roleLabel}</span>
                    <span className="tag">{scopeLabel(identity.data_scope)}</span>
                  </div>
                </div>
                <div className="ph-actions">{pageActions(path, navigate, () => void load())}</div>
              </section>

              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </SessionContext.Provider>
  )
}

function kickerParts(kicker: string): { code: string; context: string } {
  const [code, ...rest] = kicker.split(' · ')
  return { code, context: rest.join(' · ') }
}

function pageActions(path: string, navigate: (to: string) => void, refresh: () => void): ReactNode {
  if (path === '/opportunities') {
    return (
      <>
        <button type="button" className="button ghost small" onClick={() => navigate('/opportunities?overdue=1')}>
          仅看超期
        </button>
        <button type="button" className="button primary small" onClick={() => navigate('/opportunities?new=1')}>
          新建商机
        </button>
      </>
    )
  }
  if (path === '/todos') {
    return (
      <>
        <button type="button" className="button ghost small" onClick={refresh}>
          刷新
        </button>
        <button type="button" className="button primary small" onClick={() => navigate('/todos?severity=blocker')}>
          阻断队列
        </button>
      </>
    )
  }
  if (path === '/approvals') {
    return (
      <>
        <a className="button ghost small" href="/temporal/" target="_blank" rel="noreferrer">
          Temporal UI <ExternalLink size={13} />
        </a>
        <button type="button" className="button primary small" onClick={() => navigate('/approvals?mine=1')}>
          待我审批
        </button>
      </>
    )
  }
  if (path === '/master-data') {
    return (
      <button type="button" className="button ghost small" onClick={refresh}>
        刷新
      </button>
    )
  }
  return (
    <>
      <button type="button" className="button ghost small" onClick={refresh}>
        刷新
      </button>
      <button type="button" className="button primary small" onClick={() => navigate('/todos')}>
        处理待办
      </button>
    </>
  )
}

function scopeLabel(scope: string): string {
  if (scope === 'all') return '全公司视角'
  if (scope === 'region') return '大区视角'
  return '本人视角'
}

function roleDisplay(identity: Identity): string {
  if (identity.sales_role_label) return identity.sales_role_label
  return ROLE_LABELS[identity.sales_role] || ''
}

export default function App() {
  return (
    <BrowserRouter basename="/sales">
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Workbench />} />
          <Route path="opportunities" element={<Opportunities />} />
          <Route path="todos" element={<Todos />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="master-data" element={<MasterData />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
