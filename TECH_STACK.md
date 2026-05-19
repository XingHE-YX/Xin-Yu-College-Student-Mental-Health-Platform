# 心语技术栈文档

## 1. 文档范围

本文档用于锁定 MVP 的技术基线。由于当前仓库中没有现成代码、锁文件或依赖清单，以下版本号均属于项目规范性决策，而不是对现有代码的被动继承。

遵循两个规则：

1. 仓库可控依赖必须精确锁版本；
2. 无法在仓库内强制锁定的平台级工具，采用“最低支持基线”描述。

## 2. 架构选型结论

- 学生端：微信原生小程序
- 管理端：Streamlit 网页后台
- 后端 API：FastAPI
- 数据库：MySQL
- ORM 与迁移：SQLAlchemy + Alembic
- AI 分析：
- 认证方式：
  - 学生端：微信登录 + 手机号授权
  - 管理端：用户名密码 + JWT

## 3. 明确不采用的技术路线

以下技术在本次 MVP 中明确不使用：

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- Supabase
- Flask
- Django
- Redis
- 以 Docker 为首要前提的开发方式
- 自训练深度学习模型

## 4. 运行时基线

| 层级 | 选型 | 版本 / 基线 | 说明 |
| :--- | :--- | :--- | :--- |
| 学生端运行时 | 微信小程序原生运行环境 | 最低基础库 `3.6.6` | 项目兼容下限 |
| 小程序语言 | JavaScript | ES2021 | MVP 不使用 TypeScript |
| 小程序模板 | WXML | 原生 | 不使用 Taro / uni-app |
| 小程序样式 | WXSS | 原生 | 设计令牌见 `FRONTEND_GUIDELINES.md` |
| 后端运行时 | Python | `3.12.10` | 选择稳定维护中的版本 |
| 数据库 | MySQL Community Server | `8.4.8 LTS` | 长期支持线 |
| 后台运行时 | Streamlit | `1.56.0` | 单管理员后台 |

## 5. 后端依赖锁定

| 包名 | 版本 | 用途 |
| :--- | :--- | :--- |
| `fastapi` | `0.135.3` | REST API 框架 |
| `uvicorn` | `0.43.0` | ASGI 服务启动器 |
| `sqlalchemy` | `2.0.49` | ORM 与查询层 |
| `alembic` | `1.18.4` | 数据库迁移 |
| `pydantic` | `2.12.5` | 请求与响应校验 |
| `pydantic-settings` | `2.13.1` | 环境变量配置管理 |
| `PyMySQL` | `1.1.2` | MySQL 驱动 |
| `httpx` | `0.28.1` | 外部 API 客户端 |
| `streamlit` | `1.56.0` | 管理后台 |
| `pwdlib` | `0.3.0` | 密码哈希抽象 |
| `argon2-cffi` | `25.1.0` | 管理员密码哈希实现 |

## 6. 开发工具锁定

| 工具 | 版本 | 用途 |
| :--- | :--- | :--- |
| `pytest` | `9.0.2` | 后端测试 |
| `ruff` | `0.15.9` | Lint 与导入整理 |
| `black` | `26.3.1` | Python 代码格式化 |

## 7. 外部 API

### 7.1 DeepSeek

| 项目 | 值 |
| :--- | :--- |
| 服务提供方 | DeepSeek API |
| Base URL | `https://api.deepseek.com` |
| 接口路径 | `POST /chat/completions` |
| 模型 ID | `deepseek-v4-flash` |
| 模型模式 | 非思维链模式，`thinking.type = disabled` |
| 返回模式 | 必须输出 JSON |
| 容错策略 | 外部调用失败时读取本地 `mock_response.json` |

必须满足的行为要求：

- 后端必须明确要求模型返回 JSON；
- 后端必须拒绝无法解析的响应，并在演示模式下切换到本地模拟结果；
- 后端必须持久化原始 AI 响应和解析后的结构化结果。

### 7.2 微信小程序

| 项目 | 值 |
| :--- | :--- |
| 客户端登录 API | `wx.login` |
| 手机号授权方式 | 微信一键获取手机号组件 |
| 后端交互方式 | 基于 code 的微信会话交换 |
| 安全要求 | 小程序客户端不能保存 App Secret |

## 8. 认证技术栈

### 8.1 学生端认证

- 微信会话交换；
- 手机号作为账户标识；
- 后端签发学生端会话令牌；
- 演示账号登录仅在非生产环境开放。

### 8.2 管理端认证

- 用户名 + 密码；
- `pwdlib` 配合 `argon2-cffi`；
- 使用 JWT 供 Streamlit 后台调用 API；
- MVP 实际只实现单管理员登录，但数据库预留多角色字段。

## 9. 数据与存储决策

| 主题 | 决策 |
| :--- | :--- |
| 字符集 | `utf8mb4` |
| 排序规则 | `utf8mb4_0900_ai_ci` |
| 主键风格 | `BIGINT UNSIGNED AUTO_INCREMENT` |
| 时间字段 | 统一使用 UTC 的 `DATETIME(3)` |
| 树洞删除策略 | 软删除 |
| JSON 字段使用范围 | 评分快照、AI 输出、选项映射 |
| 文件存储 | 实施阶段用本地 JSON 作为题库附录来源 |

## 10. 部署基线

MVP 支持两种部署模式：

### 10.1 答辩演示模式

- 学生端运行于微信开发者工具或测试小程序
- FastAPI 本地运行
- Streamlit 本地运行
- MySQL 本地运行
- 优先调用 DeepSeek，失败时使用本地模拟数据

### 10.2 低成本云演示模式

- 学生端连接公网 HTTPS API
- FastAPI 与 Streamlit 部署在低成本学生云服务器
- MySQL 8.4 LTS 与应用同机部署，降低复杂度

## 11. 目录规范

仓库后续必须收敛到如下结构：

```text
/
├── PRD.md
├── APP_FLOW.md
├── TECH_STACK.md
├── FRONTEND_GUIDELINES.md
├── BACKEND_STRUCTURE.md
├── IMPLEMENTATION_PLAN.md
├── backend/
├── admin/
├── miniprogram/
└── appendices/
    └── question_bank/
```

其中 `appendices/question_bank/` 用于存放后续可直接录库的题库文件，包括 SDS、SAS 和项目自定义问卷。

## 12. 版本更新策略

- 不允许静默升级 Patch 版本；
- 任意依赖的 Minor 或 Major 升级都需要显式更新规范文档；
- 微信基础库兼容下限只能上调，不能随意下调。

## 13. 版本核验来源

本技术栈文档锁版本时参考了以下来源：

- Python 官网中 3.12 分支发布信息；
- MySQL 官方 8.4 LTS 发布信息；
- PyPI 上 FastAPI、Uvicorn、SQLAlchemy、Alembic、Pydantic、pydantic-settings、PyMySQL、httpx、Streamlit、pwdlib、argon2-cffi、pytest、Ruff、Black 的发布页；
- DeepSeek 官方 API 文档中关于 Base URL、模型 ID 与 JSON 输出的说明。
