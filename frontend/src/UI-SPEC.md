# EAI-Flow UI 设计规范

> 基于 shadcn/ui + deer-flow 规范体系，参考 shadcn-admin-main 设计模式

---

## 一、设计原则

1. **一致性**：所有页面使用相同的组件库和设计模式
2. **可复用性**：使用 shadcn/ui 组件，通过 Tailwind CSS 变量实现主题定制
3. **可访问性**：遵循 ARIA 规范，支持键盘导航和屏幕阅读器
4. **响应式**：支持桌面端和移动端自适应
5. **国际化**：所有文本使用 i18n key，支持中英文切换

---

## 二、设计令牌 (Design Tokens)

### 2.1 颜色系统

| 令牌 | 用途 | 亮色模式 | 暗色模式 |
|------|------|----------|----------|
| `--background` | 页面背景 | `oklch(1 0 0)` 白 | `oklch(0.145 0 0)` 深灰 |
| `--foreground` | 主文本 | `oklch(0.145 0 0)` | `oklch(0.985 0 0)` |
| `--primary` | 主色调 | `oklch(0.51 0.22 264)` 靛蓝 | `oklch(0.58 0.22 264)` |
| `--primary-foreground` | 主色文本 | `oklch(1 0 0)` 白 | `oklch(0.985 0 0)` |
| `--secondary` | 次要背景 | `oklch(0.96 0 0)` | `oklch(0.3 0 0)` |
| `--muted` | 弱化背景 | `oklch(0.97 0 0)` | `oklch(0.269 0 0)` |
| `--muted-foreground` | 次要文本 | `oklch(0.556 0 0)` | `oklch(0.6 0 0)` |
| `--accent` | 强调背景 | `oklch(0.96 0 0)` | `oklch(0.32 0 0)` |
| `--destructive` | 危险/错误 | `oklch(0.577 0.245 27.325)` 红 | 同左 |
| `--border` | 边框 | `oklch(0.922 0 0)` | `oklch(1 0 0 / 10%)` |
| `--input` | 输入框边框 | `oklch(0.88 0 0)` | `oklch(1 0 0 / 15%)` |
| `--success` | 成功状态 | `oklch(0.627 0.194 154.44)` 绿 | 同左 |
| `--warning` | 警告状态 | `oklch(0.769 0.188 70.08)` 黄 | 同左 |

### 2.2 圆角系统

| 令牌 | 尺寸 | 用途 |
|------|------|------|
| `--radius` | 0.625rem (10px) | 默认圆角 |
| `--radius-sm` | calc(var(--radius) - 4px) = 6px | 小按钮/输入框 |
| `--radius-md` | calc(var(--radius) - 2px) = 8px | 中等元素 |
| `--radius-lg` | var(--radius) = 10px | 大卡片/弹窗 |
| `--radius-xl` | calc(var(--radius) + 4px) = 14px | 更大卡片 |

### 2.3 间距规范

| 名称 | 尺寸 | 用途 |
|------|------|------|
| `space-y-1` | 4px | 紧凑间距 |
| `space-y-2` | 8px | 小间距 |
| `space-y-4` | 16px | 默认间距 |
| `space-y-6` | 24px | 大间距 |
| `space-y-8` | 32px | 区域间距 |
| `p-4` / `px-4` / `py-6` | 16px/16px/24px | 组件内边距 |
| `px-8 py-6` | 32px/24px | 页面级边距 |

### 2.4 阴影系统

```css
/* 卡片阴影 */
shadow-sm      /* 小阴影，用于内嵌卡片 */
shadow-xs      /* 极小阴影 */
shadow-lg      /* 大阴影，用于弹窗 */

/* eai-flow 特定阴影 */
shadow-[0_8px_30px_rgb(0,0,0,0.08)] /* 登录页卡片阴影 */
```

### 2.5 字体系统

```css
--font-sans: ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji",
    "Segoe UI Symbol", "Noto Color Emoji";
```

字号层级：
- `text-xs`: 0.75rem (12px) - 辅助文本
- `text-sm`: 0.875rem (14px) - 正文/按钮
- `text-base`: 1rem (16px) - 主文本
- `text-lg`: 1.125rem (18px) - 大标题
- `text-2xl`: 1.5rem (24px) - 页面标题
- `text-3xl`: 1.875rem (30px) - 大标题

---

## 三、组件规范

### 3.1 按钮 (Button)

**CVA 变体模式**：

```typescript
buttonVariants({
  variant: {
    default:    'bg-primary text-primary-foreground shadow-xs hover:bg-primary/90',
    destructive: 'bg-destructive text-white shadow-xs hover:bg-destructive/90',
    outline:    'border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground',
    secondary:  'bg-secondary text-secondary-foreground shadow-xs hover:bg-secondary/80',
    ghost:      'hover:bg-accent hover:text-accent-foreground',
    link:       'text-primary underline-offset-4 hover:underline',
  },
  size: {
    default: 'h-9 px-4 py-2 has-[>svg]:px-3',
    sm:      'h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5',
    lg:      'h-10 rounded-md px-6 has-[>svg]:px-4',
    icon:    'size-9',
  },
})
```

**使用规范**：
- 主要操作使用 `variant="default"`（主色调按钮）
- 危险操作（删除）使用 `variant="destructive"`
- 次要操作使用 `variant="outline"`
- 图标按钮使用 `size="icon"`
- 始终包含 `gap-2` 和图标/文字间距
- 使用 `data-slot="button"` 属性

**正确示例**：
```tsx
import { Button } from "@/components/ui/button"
import { Plus, Edit, Trash2 } from "lucide-react"

// 添加按钮
<Button>
  <Plus className="h-4 w-4" />
  添加用户
</Button>

// 图标按钮
<Button size="icon" variant="ghost">
  <Edit className="h-4 w-4" />
</Button>

// 危险操作
<Button variant="destructive">
  <Trash2 className="h-4 w-4" />
  删除
</Button>
```

**错误示例**：
```tsx
// ❌ 错误：使用普通 <button> 而非 shadcn Button
<button className="px-4 py-2 bg-primary text-white rounded-lg">
  提交
</button>

// ❌ 错误：缺少图标间距
<Button><Plus />添加用户</Button>

// ✅ 正确：使用 Button 组件，图标有正确间距
<Button><Plus className="h-4 w-4" />添加用户</Button>
```

### 3.2 卡片 (Card)

**组件结构**：

```tsx
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  CardAction,
} from "@/components/ui/card"

// 标准卡片结构
<Card>
  <CardHeader>
    <CardTitle>卡片标题</CardTitle>
    <CardDescription>卡片描述</CardDescription>
    <CardAction>操作按钮</CardAction>
  </CardHeader>
  <CardContent>内容区域</CardContent>
  <CardFooter>底部操作</CardFooter>
</Card>
```

**样式规范**：
- 卡片：`rounded-xl border bg-card py-6 text-card-foreground shadow-sm`
- CardHeader：`px-6`，包含标题和描述时使用 `@container/card-header` 布局
- CardContent：`px-6`
- CardFooter：`px-6`，有上边框时自动添加 `pt-6`

**应用场景**：
- 数据展示卡片：用户信息卡片、统计卡片
- 表单卡片：编辑/创建表单容器
- 列表卡片：聊天会话卡片、文件卡片

### 3.3 表格 (Table)

**组件结构**：

```tsx
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table"

<Table>
  <TableHeader>
    <TableRow>
      <TableHead>列标题</TableHead>
      <TableHead className="text-right">右对齐列</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    <TableRow className="hover:bg-muted/50">
      <TableCell>单元格内容</TableCell>
      <TableCell className="text-right">右对齐</TableCell>
    </TableRow>
  </TableBody>
</Table>
```

**样式规范**：
- TableRow：`border-b transition-colors hover:bg-muted/50`
- TableHead：`h-10 px-2 text-start align-middle font-medium text-muted-foreground uppercase tracking-wider`
- TableCell：`p-2 align-middle`
- 表头背景：`bg-muted/50` 或 `bg-muted`

**交互规范**：
- 行悬停：鼠标悬停时整行高亮 `hover:bg-muted/50`
- 行选中：选中行高亮 `data-[state=selected]:bg-muted`
- 操作按钮：默认隐藏（opacity-0），悬停行时显示（group-hover:opacity-100）

### 3.4 输入框 (Input)

**组件结构**：

```tsx
import { Input } from "@/components/ui/input"

<Input
  type="text"
  value={value}
  onChange={(e) => setValue(e.target.value)}
  placeholder="请输入..."
  className="w-full"
/>
```

**样式规范**：
- 高度：`h-9`（默认）、`h-8`（小）、`h-10`（大）
- 内边距：`px-3 py-1`
- 焦点样式：`focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50`
- 错误样式：`aria-invalid:border-destructive aria-invalid:ring-destructive/20`

**带图标的输入框**：

```tsx
<div className="relative">
  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
  <Input className="pl-9" placeholder="用户名" />
</div>
```

### 3.5 弹窗/模态框

**使用 Dialog 组件**：

```tsx
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
```

**动画规范**：
- 进入动画：`animate-in fade-in-0 zoom-in-95`
- 退出动画：`animate-out fade-out-0 zoom-out-95`
- 背景遮罩：`bg-black/40 backdrop-blur-sm`
- 内容动画：`scale-95 -> scale-100`，`y-4 -> y-0`

### 3.6 下拉菜单 (Dropdown)

**组件结构**：

```tsx
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

<DropdownMenu>
  <DropdownMenuTrigger>触发器</DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuItem>选项1</DropdownMenuItem>
    <DropdownMenuSeparator />
    <DropdownMenuItem className="text-destructive">危险操作</DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

**样式规范**：
- 触发器使用 `DropdownMenuTrigger asChild`
- 内容区域：`w-56 rounded-lg border bg-popover p-1 shadow-md`
- 项目：`flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none hover:bg-accent`
- 危险项目：`text-destructive focus:bg-destructive/10 focus:text-destructive`
- 图标与文字间距：`mr-2 h-4 w-4`

### 3.7 徽章/标签 (Badge)

**变体**：

```tsx
import { Badge } from "@/components/ui/badge"

<Badge variant="default">默认</Badge>
<Badge variant="secondary">次要</Badge>
<Badge variant="outline">描边</Badge>
<Badge variant="destructive">危险</Badge>
```

**状态徽章示例**：

```tsx
// 成功状态
<Badge className="bg-success/10 text-success">
  <span className="w-1.5 h-1.5 rounded-full bg-success mr-1.5" />
  正常
</Badge>

// 禁用状态
<Badge variant="secondary">
  已停用
</Badge>
```

### 3.8 分页 (Pagination)

**组件结构**：

```tsx
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

<div className="flex items-center justify-between px-2">
  {/* 左侧：每页条数 */}
  <div className="flex items-center gap-2">
    <Select value={`${pageSize}`} onValueChange={(v) => setPageSize(Number(v))}>
      <SelectTrigger className="h-8 w-[70px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {[10, 20, 30, 50].map(size => (
          <SelectItem key={size} value={`${size}`}>{size}</SelectItem>
        ))}
      </SelectContent>
    </Select>
    <span className="text-sm text-muted-foreground">条/页</span>
  </div>

  {/* 右侧：分页按钮 */}
  <div className="flex items-center gap-2">
    <Button size="icon" variant="outline" disabled={!canPrevious}>
      <ChevronLeftIcon className="h-4 w-4" />
    </Button>
    {pageNumbers.map((page, idx) => (
      page === '...' ? (
        <span key={idx} className="px-2 text-muted-foreground">...</span>
      ) : (
        <Button
          key={page}
          size="sm"
          variant={currentPage === page ? 'default' : 'outline'}
        >
          {page}
        </Button>
      )
    ))}
    <Button size="icon" variant="outline" disabled={!canNext}>
      <ChevronRightIcon className="h-4 w-4" />
    </Button>
  </div>
</div>
```

---

## 四、页面布局规范

### 4.1 页面结构

```
页面容器
├── 页面头部 (Header)
│   ├── 标题区域 (左侧)
│   │   ├── 页面标题 (text-2xl font-bold)
│   │   └── 页面描述 (text-sm text-muted-foreground)
│   └── 操作区域 (右侧)
│       └── 主要操作按钮 (添加、创建等)
├── 工具栏 (Toolbar) [可选]
│   ├── 搜索框 (max-w-sm)
│   ├── 筛选器
│   └── 其他操作
├── 内容区域
│   ├── 表格/卡片列表
│   ├── 空状态
│   └── 加载状态
└── 分页 [可选]
```

### 4.2 页面边距规范

| 区域 | 边距 |
|------|------|
| 页面头部 | `px-8 py-6` |
| 内容区域 | `p-8` |
| 卡片内边距 | `px-6` |
| 表格单元格 | `px-6 py-4` |

### 4.3 侧边栏规范

**ExtensionsSidebar**（左侧图标导航栏）：
- 宽度：`w-14 shrink-0`
- 高度：全屏 `h-screen`
- 图标按钮：`w-10 h-10 rounded-lg`
- 激活状态：`text-primary bg-primary/10`
- 悬停状态：`text-muted-foreground hover:text-primary hover:bg-accent`

**WorkspaceSidebar**（工作区侧边栏）：
- 使用 shadcn/ui Sidebar 组件
- 折叠模式：`collapsible="icon"`
- 变体：`variant="sidebar"`

---

## 五、状态规范

### 5.1 加载状态

```tsx
// 骨架屏
import { Skeleton } from "@/components/ui/skeleton"

<Skeleton className="h-4 w-[200px]" />
<Skeleton className="h-10 w-full" />
<Skeleton className="h-20 w-full rounded-lg" />

// 全页加载
<div className="flex-1 flex items-center justify-center">
  <div className="text-muted-foreground">加载中...</div>
</div>
```

### 5.2 空状态

```tsx
<div className="flex flex-col items-center justify-center py-12 text-center">
  <EmptyIcon className="w-12 h-12 text-muted-foreground mb-3" />
  <p className="text-muted-foreground">没有找到匹配的数据</p>
</div>
```

### 5.3 错误状态

```tsx
// 使用 Alert 显示错误
<div className="p-3 text-sm text-destructive bg-destructive/10 rounded-lg">
  {errorMessage}
</div>
```

### 5.4 成功状态

```tsx
// 使用 Toast (Sonner) 或 Alert
toast.success("操作成功")
```

---

## 六、动画规范

### 6.1 页面过渡动画

```tsx
import { motion, AnimatePresence } from "framer-motion"

// 模态框
<motion.div
  initial={{ opacity: 0, scale: 0.95, y: 10 }}
  animate={{ opacity: 1, scale: 1, y: 0 }}
  exit={{ opacity: 0, scale: 0.95, y: 10 }}
>
  内容
</motion.div>

// 列表项
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  exit={{ opacity: 0, y: -20 }}
>
  列表项
</motion.div>
```

### 6.2 按钮交互

```tsx
// hover:bg-primary/90 (默认)
// hover:bg-destructive/90 (危险)
// hover:bg-accent (ghost)
```

### 6.3 渐变动画

```css
.animate-fade-in {
  animation: fade-in 1.1s;
}

.animate-fade-in-up {
  animation: fade-in-up 0.15s ease-in-out forwards;
}

.animate-shimmer {
  animation: shimmer 2s infinite linear;
  background: linear-gradient(90deg, var(--muted) 25%, var(--muted-foreground) 50%, var(--muted) 75%);
  background-size: 200% 100%;
}
```

---

## 七、可访问性规范

### 7.1 焦点管理

- 使用 `focus-visible:ring-[3px]` 替代 `outline`
- 确保模态框打开时焦点在内部
- 使用 `aria-label` 为图标按钮提供描述

### 7.2 屏幕阅读器

- 使用 `sr-only` 为视觉元素提供替代文本
- 使用 `aria-invalid` 标识表单错误
- 使用 `aria-describedby` 关联错误消息

### 7.3 键盘导航

- Tab 键：按顺序切换焦点
- Enter/Space：激活按钮
- Escape：关闭模态框/下拉菜单
- 方向键：在下拉菜单中选择

---

## 八、国际化规范

### 8.1 i18n key 命名约定

```typescript
// 页面标题：page.{pageName}.title
// 页面描述：page.{pageName}.description
// 按钮：common.{action}
// 表单标签：form.{field}.label
// 验证消息：form.{field}.error.{errorType}
// 提示消息：message.{type}.{action}
```

### 8.2 示例

```typescript
// zh-CN.ts
export default {
  page: {
    users: {
      title: "用户管理",
      description: "管理企业内所有用户的账号、部门归属及角色权限",
    },
  },
  common: {
    add: "添加",
    edit: "编辑",
    delete: "删除",
    save: "保存",
    cancel: "取消",
    confirm: "确认",
    search: "搜索",
    filter: "筛选",
    logout: "退出登录",
  },
  form: {
    username: {
      label: "用户名",
      placeholder: "请输入用户名",
      required: "用户名不能为空",
    },
  },
  message: {
    success: {
      create: "创建成功",
      update: "更新成功",
      delete: "删除成功",
    },
    error: {
      create: "创建失败",
      update: "更新失败",
      delete: "删除失败",
    },
  },
}
```

---

## 九、参考文件

| 类别 | 参考文件 |
|------|----------|
| Button | `src/components/ui/button.tsx` |
| Card | `src/components/ui/card.tsx` |
| Table | `src/components/ui/table.tsx` |
| Input | `src/components/ui/input.tsx` |
| Badge | `src/components/ui/badge.tsx` |
| Dialog | `src/components/ui/dialog.tsx` |
| Dropdown | `src/components/ui/dropdown-menu.tsx` |
| 全局样式 | `src/styles/globals.css` |
| 布局组件 | `src/components/workspace/workspace-sidebar.tsx` |
| Admin 页面 | `src/app/admin/users/page.tsx` |
| shadcn-admin | `D:\aiproj\qData\shadcn-admin-main\` |

---

## 十、待完善检查清单

- [x] 设计令牌定义（globals.css）
- [x] Button 组件（shadcn/ui）
- [x] Card 组件（shadcn/ui）
- [x] Table 组件（shadcn/ui）
- [x] Input 组件（shadcn/ui）
- [ ] Badge 组件检查
- [x] Dialog 组件（shadcn/ui）
- [ ] 分页组件统一
- [ ] 统一 Admin 页面使用 shadcn 组件
- [ ] 空状态组件统一
- [ ] 骨架屏组件使用
