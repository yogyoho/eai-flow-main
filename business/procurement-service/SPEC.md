# 招标采购微服务集成方案

## 1. 背景与目标

EAIFlow 系统需要集成一个独立的招标采购业务系统，该系统有自己的前后端服务。采用微服务架构实现与主系统的解耦集成。

## 2. 集成架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Nginx (端口 4026)                      │
│  /procurement/*  →  procurement-frontend:3000                │
│  /procurement/api/* → procurement-backend:3001              │
│  /api/*          → gateway:4001                             │
│  /               → frontend:4000                            │
└─────────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌──────────────────┐  ┌──────────────────────────────────┐
│ Procurement      │  │         EAIFlow Main System       │
│ Microservice     │  │                                  │
│ ┌─────────────┐  │  │  ┌───────────┐  ┌───────────┐  │
│ │  Frontend   │  │  │  │  Frontend  │  │  Gateway  │  │
│ │ (Next.js)   │  │  │  │ (Next.js)  │  │ (FastAPI) │  │
│ │  :3000      │  │  │  │  :4000     │  │  :4001    │  │
│ └─────────────┘  │  │  └───────────┘  └───────────┘  │
│ ┌─────────────┐  │  │                                  │
│ │  Backend    │  │  │  ┌───────────┐  ┌───────────┐    │
│ │ (FastAPI)   │  │  │  │ LangGraph │  │ LangGraph │    │
│ │  :3001      │  │  │  │   :4024   │  │  Server   │    │
│ └─────────────┘  │  │  └───────────┘  └───────────┘    │
└──────────────────┘  └──────────────────────────────────┘
```

## 3. 核心设计决策

### 3.1 JWT 共享认证
- 共享密钥通过环境变量 `JWT_SECRET_KEY` 配置
- 招标微服务独立验证 JWT Token，与 gateway 使用相同签名算法
- Token 格式: `Bearer <token>`，由 EAIFlow gateway 签发
- 前端从 `/api/extensions/auth/login` 登录获取 token，存储在 localStorage

### 3.2 前端集成
- 招标微服务前端（Next.js）独立构建、独立部署
- 主系统侧边栏 "招标采购" 链接指向 `/procurement`（由 Nginx 路由至独立前端）
- 两端前端共享同一套用户登录态（localStorage 中的 JWT）
- 访问入口：`http://localhost:4026/procurement`

### 3.3 API 网关
- Nginx 反向代理统一入口（端口 4026）
- `/procurement/*` → 招标前端
- `/procurement/api/*` → 招标后端 API
- 主系统 API 保持不变

### 3.4 数据库
- 招标微服务使用自己的 PostgreSQL 数据库
- 数据库连接通过 `DATABASE_URL` 环境变量配置
- 独立迁移、独立备份

## 4. 目录结构

```
procurement-service/
├── backend/                    # 招标后端 (FastAPI)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI 入口
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # 数据库连接
│   │   ├── auth.py             # JWT 认证（共享密钥）
│   │   ├── routers/            # API 路由
│   │   │   ├── __init__.py
│   │   │   ├── experts.py
│   │   │   ├── bidders.py
│   │   │   ├── plans.py
│   │   │   ├── projects.py
│   │   │   ├── bids.py
│   │   │   ├── evaluations.py
│   │   │   ├── winning_bids.py
│   │   │   ├── contracts.py
│   │   │   ├── complaints.py
│   │   │   ├── witness_records.py
│   │   │   └── venue_spaces.py
│   │   ├── schemas/            # Pydantic 模型
│   │   │   ├── __init__.py
│   │   │   └── models.py
│   │   └── services/           # 业务逻辑
│   │       ├── __init__.py
│   │       ├── expert_service.py
│   │       ├── bidder_service.py
│   │       ├── plan_service.py
│   │       ├── project_service.py
│   │       ├── bid_service.py
│   │       ├── evaluation_service.py
│   │       ├── winning_bid_service.py
│   │       ├── contract_service.py
│   │       └── complaint_service.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/                   # 招标前端 (Next.js)
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   └── procurement/   # 招标采购页面
│   │   ├── components/
│   │   ├── lib/
│   │   └── styles/
│   ├── package.json
│   ├── Dockerfile
│   └── next.config.js
├── .env.procurement.example
└── docker-compose.yaml         # 独立部署配置（可选）
```

## 5. API 设计

所有 API 遵循 RESTful 规范，基础路径: `/api/v1`

### 5.1 认证
- `POST /api/v1/auth/login` - 登录（由 gateway 统一提供）
- 所有业务 API 需携带 `Authorization: Bearer <token>` 请求头

### 5.2 业务 API
| 资源 | 端点 | 方法 | 说明 |
|------|------|------|------|
| 专家 | `/experts` | GET/POST | 查询/创建专家 |
| 专家 | `/experts/{id}` | GET/PUT/DELETE | 专家 CRUD |
| 专家抽取 | `/expert-draws` | POST/GET | 抽取/查询记录 |
| 投标人 | `/bidders` | GET/POST | 查询/创建投标人 |
| 投标人 | `/bidders/{id}` | GET/PUT/DELETE | 投标人 CRUD |
| 招标计划 | `/plans` | GET/POST | 查询/创建计划 |
| 招标计划 | `/plans/{id}` | GET/PUT/DELETE | 计划 CRUD |
| 招标项目 | `/projects` | GET/POST | 查询/创建项目 |
| 招标项目 | `/projects/{id}` | GET/PUT/DELETE | 项目 CRUD |
| 招标项目 | `/projects/{id}/publish` | POST | 发布公告 |
| 投标 | `/bids` | GET/POST | 查询/提交投标 |
| 投标 | `/bids/{id}` | GET/PUT | 投标详情/更新 |
| 投标 | `/bids/{id}/compliance-check` | POST | 合规性检查 |
| 评标 | `/evaluations` | GET/POST | 查询/创建评标 |
| 评标 | `/evaluations/{id}/verify` | POST | 核验 |
| 评标 | `/evaluations/{id}/complete` | POST | 完成评标 |
| 中标 | `/winning-bids` | POST | 创建中标记录 |
| 中标 | `/winning-bids/{id}/confirm` | POST | 确认中标 |
| 中标 | `/winning-bids/{id}/contract` | POST | 生成合同 |
| 合同 | `/contracts` | GET/POST | 查询/创建合同 |
| 合同 | `/contracts/{id}` | GET/PUT | 合同详情/更新 |
| 合同 | `/contracts/{id}/risk-check` | POST | 风险检测 |
| 投诉 | `/complaints` | GET/POST | 查询/提交投诉 |
| 投诉 | `/complaints/{id}` | GET/PUT | 投诉详情/更新 |
| 投诉 | `/complaints/{id}/reply` | POST | 答复投诉 |
| 投诉 | `/complaints/{id}/decide` | POST | 处理决定 |
| 见证记录 | `/witness-records` | GET/POST | 查询/创建见证 |
| 场所工位 | `/venue-spaces` | GET/POST | 查询/创建工位 |
| 场所工位 | `/venue-spaces/{id}` | PUT | 更新工位 |
| 仪表盘 | `/dashboard/stats` | GET | 统计数据 |

## 6. 环境变量

### 后端
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/procurement
JWT_SECRET_KEY=your-shared-jwt-secret-from-eaiflow
API_PREFIX=/api/v1
HOST=0.0.0.0
PORT=3001
LOG_LEVEL=INFO
```

### 前端
```
NEXT_PUBLIC_API_BASE_URL=/procurement/api
NEXT_PUBLIC_APP_BASE_URL=/procurement
```

## 7. 部署流程

### 7.1 开发环境
```bash
# 启动后端
cd procurement-service/backend
uv sync
uv run uvicorn app.main:app --reload --port 3001

# 启动前端
cd procurement-service/frontend
pnpm install
pnpm dev
```

### 7.2 Docker 部署
```bash
# 构建并启动
cd procurement-service
docker-compose up --build

# 或在主项目 docker-compose-dev.yaml 中使用
# 由主项目统一编排
```

## 8. 安全考虑

- JWT 密钥需与 EAIFlow 主系统保持一致
- 敏感配置通过环境变量注入，不硬编码
- CORS 仅允许已知域名
- 所有 API 端点需身份验证
- SQLAlchemy ORM 防注入

## 9. 与 EAIFlow 主系统的集成点

1. **认证**: 共享 JWT Token（通过相同密钥验证）
2. **导航**: EAIFlow 侧边栏 "招标采购" 链接指向 `/procurement`
3. **反向代理**: Nginx 统一路由
4. **可选数据共享**: 未来可通过 API 从主系统获取用户/部门数据
