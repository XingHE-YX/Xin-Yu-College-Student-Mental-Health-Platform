# 心语项目协作说明（CODEX.md）

## 1. 文档目的

本文档用于约束 AI 编码助手和项目成员在本仓库中的协作方式。它不是产品需求文档，而是“如何在这个项目里正确工作”的统一说明。

任何新会话开始后，AI 在进行分析、设计、编码、改动、重构、补文档之前，都必须先阅读本文件，并按本文件约束执行。

## 2. 会话启动必读规则

每次会话开始时，AI 必须按以下顺序检查并读取：

1. `CODEX.md`
2. `progress.txt`，如果存在
3. `lessons.md`，如果存在
4. 本项目规范文档列表中的相关文件

如果 `progress.txt` 或 `lessons.md` 不存在，AI 不得报错阻塞，只需记录为“文件不存在，继续执行”。

## 3. 必须参考的规范文档

AI 在执行任何设计、编码、重构、建表、接口实现、页面实现时，必须参考以下文档：

- `PRD.md`
- `APP_FLOW.md`
- `TECH_STACK.md`
- `FRONTEND_GUIDELINES.md`
- `BACKEND_STRUCTURE.md`
- `IMPLEMENTATION_PLAN.md`

如果这些文档之间出现冲突，处理优先级如下：

1. `PRD.md`
2. `APP_FLOW.md`
3. `BACKEND_STRUCTURE.md`
4. `TECH_STACK.md`
5. `FRONTEND_GUIDELINES.md`
6. `IMPLEMENTATION_PLAN.md`
7. `CODEX.md`

如果发现冲突且无法自动消解，AI 必须停止关键实现并先指出冲突点。

## 4. 项目技术栈摘要

本项目的固定技术栈如下：

### 4.1 学生端

- 平台：微信小程序
- 语言：JavaScript
- 视图：WXML
- 样式：WXSS
- 运行基线：微信基础库 `3.6.6` 及以上

### 4.2 后端

- 语言：Python `3.12.10`
- Web 框架：`FastAPI 0.135.3`
- ASGI：`uvicorn 0.43.0`
- ORM：`SQLAlchemy 2.0.49`
- 迁移：`Alembic 1.18.4`
- 校验：`Pydantic 2.12.5`
- 配置：`pydantic-settings 2.13.1`
- 数据库驱动：`PyMySQL 1.1.2`
- HTTP 客户端：`httpx 0.28.1`

### 4.3 管理后台

- 框架：`Streamlit 1.56.0`

### 4.4 数据库

- 数据库：`MySQL 8.4.8 LTS`
- 字符集：`utf8mb4`
- 排序规则：`utf8mb4_0900_ai_ci`

### 4.5 AI 能力

- 服务：DeepSeek API
- Base URL：`https://api.deepseek.com`
- 模型：`deepseek-chat`
- 要求：只接受 JSON 结构输出
- 容错：外部失败时必须支持本地 `mock_response.json`

## 5. 固定目录与文件存放约定

当前仓库的目标结构固定如下：

```text
/
├── CODEX.md
├── PRD.md
├── APP_FLOW.md
├── TECH_STACK.md
├── FRONTEND_GUIDELINES.md
├── BACKEND_STRUCTURE.md
├── IMPLEMENTATION_PLAN.md
├── progress.txt
├── lessons.md
├── backend/
├── admin/
├── miniprogram/
├── appendices/
│   └── question_bank/
└── tests/
```

### 5.1 后端目录约定

后端代码统一放在：

```text
backend/
├── pyproject.toml
├── alembic.ini
├── alembic/
└── src/
    ├── main.py
    ├── core/
    ├── api/
    ├── models/
    ├── schemas/
    ├── services/
    ├── repositories/
    ├── utils/
    └── constants/
```

规则：

- 路由文件放在 `backend/src/api/`
- 数据模型放在 `backend/src/models/`
- Pydantic 请求与响应模型放在 `backend/src/schemas/`
- 业务逻辑放在 `backend/src/services/`
- 数据访问逻辑放在 `backend/src/repositories/`
- 配置、认证、中间件、数据库连接等放在 `backend/src/core/`
- 常量和枚举优先放在 `backend/src/constants/`

### 5.2 管理后台目录约定

管理后台代码统一放在：

```text
admin/
├── app.py
├── pages/
├── components/
├── services/
├── state/
└── utils/
```

规则：

- `admin/app.py` 作为后台入口
- 多页面内容放在 `admin/pages/`
- 可复用展示块放在 `admin/components/`
- 调后端 API 的逻辑放在 `admin/services/`
- Session state 相关逻辑放在 `admin/state/`

### 5.3 小程序目录约定

学生端小程序代码统一放在：

```text
miniprogram/
├── app.js
├── app.json
├── app.wxss
├── pages/
├── components/
├── services/
├── utils/
├── constants/
└── styles/
```

规则：

- 页面级代码放在 `miniprogram/pages/`
- 可复用业务组件放在 `miniprogram/components/`
- 网络请求封装放在 `miniprogram/services/`
- 公共工具放在 `miniprogram/utils/`
- 常量、枚举、配置项放在 `miniprogram/constants/`
- 设计令牌和公共样式放在 `miniprogram/styles/`

### 5.4 附录与题库存放约定

问卷题库和种子文件统一放在：

```text
appendices/question_bank/
```

至少包含：

- `screen_questions.json`
- `sleep_questions.json`
- `upi_questions.json`
- `sds_questions.json`
- `sas_questions.json`

### 5.5 测试目录约定

测试统一放在：

```text
tests/
├── backend/
├── admin/
└── integration/
```

规则：

- 后端单元测试放 `tests/backend/`
- 后台可测试逻辑放 `tests/admin/`
- API 集成测试放 `tests/integration/`

## 6. 文件命名约定

### 6.1 Python 文件

- 一律使用小写蛇形命名：`risk_engine.py`
- 不允许使用拼音文件名
- 不允许使用空格文件名

### 6.2 小程序页面目录

- 页面目录使用小写中划线或小写蛇形，建议统一为小写中划线：
  - `quick-screen`
  - `treehole-feed`
  - `alert-detail`

### 6.3 JSON / 配置文件

- 使用小写蛇形命名：
  - `mock_response.json`
  - `screen_questions.json`

### 6.4 数据库相关命名

- 表名：小写复数蛇形，如 `student_users`
- 字段名：小写蛇形，如 `created_at`
- 枚举值：小写下划线，如 `pending_review`

## 7. 必须遵循的编码模式

## 7.1 通用规则

- 先按规范文档实现，再做局部优化
- 不允许未解释的架构发散
- 优先可读性和可追溯性，而不是炫技式写法
- 所有关键业务逻辑必须可测试

### 7.2 后端编码模式

- 使用 FastAPI 路由 + Service + Repository 分层
- 路由层只做：
  - 参数接收
  - 权限校验
  - 调用 service
  - 返回响应
- Service 层负责：
  - 业务规则
  - 风险判定
  - 状态流转
  - 报告生成
- Repository 层负责：
  - 查询
  - 写入
  - 条件过滤
  - 事务辅助
- 使用 Pydantic 定义请求与响应模型
- 使用 SQLAlchemy 2.0 风格，不写混乱的旧式查询风格
- 所有时间统一使用 UTC

### 7.3 小程序编码模式

- 使用原生页面 + 自定义业务组件模式
- 页面脚本只负责：
  - 页面生命周期
  - 交互调度
  - 调用 service
  - 管理页面局部状态
- 网络请求统一通过 `miniprogram/services/` 封装
- 不允许在多个页面里重复手写请求逻辑
- 公共常量统一抽到 `constants/`
- 公共格式化逻辑统一抽到 `utils/`
- 页面不得变成超大单文件，单个页面脚本过长时必须拆组件或拆工具逻辑

### 7.4 管理后台编码模式

- Streamlit 页面层只负责展示和交互编排
- 后端数据请求统一通过 `admin/services/`
- 状态管理统一放 `admin/state/`
- 图表数据在服务层整形成页面可直接使用的结构

### 7.5 组件化模式

本项目不使用 React，因此不采用“函数组件 + Hooks”这套 React 模式。

本项目替代性规则如下：

- 小程序使用原生组件化
- 可复用 UI 必须抽成组件
- 不允许把多个页面重复的 UI 直接复制粘贴三次以上
- 高风险提示、结果标签、进度条、树洞卡片、问卷卡片必须组件化

## 8. 设计系统令牌引用

实现前端时，必须直接引用 `FRONTEND_GUIDELINES.md` 中的设计令牌，不得自行发明新主色。

### 8.1 核心颜色

- 主色：`#2F8F83`
- 主色深色：`#1E645C`
- 页面浅背景：`#EEF7F5`
- 卡片背景：`#FFFFFF`
- 正文主文字：`#41504C`
- 标题文字：`#1F2A28`
- 需关注色：`#E5A23A`
- 高风险色：`#D84C4C`
- 高风险深色：`#A92A2A`

### 8.2 间距

- 使用 4px 基础网格
- 常用间距：
  - `8px`
  - `12px`
  - `16px`
  - `24px`
  - `32px`

### 8.3 圆角

- 小圆角：`10px`
- 标准圆角：`14px`
- 大圆角：`20px`

### 8.4 控件规格

- 标准按钮高度：`48px`
- 最小点击区域：`44px x 44px`

## 9. 必须遵守的业务实现边界

- 高风险树洞内容不能公开发布
- UPI 是可选项，不能阻塞完整报告解锁
- 完整报告只在 70 道必做题全部完成后解锁
- 系统不能宣称具备诊断能力
- 后台确认后只能写模拟通知日志，不能默认实现真实短信发送
- 外部 AI 接口失败时必须保留 mock 容错能力

## 10. 明确禁止的操作

以下行为在本项目中明确禁止：

### 10.1 前端禁止项

- 禁止使用内联样式作为常规实现方式
- 禁止绕过 `FRONTEND_GUIDELINES.md` 自行决定主色
- 禁止在高风险页面使用趣味化、卡通化、游戏化表达
- 禁止自由文本评论功能
- 禁止学生私信功能

### 10.2 后端禁止项

- 禁止把业务规则直接散落在路由函数里
- 禁止在 API 层直接写复杂 SQL 逻辑
- 禁止把 AI 输出直接信任为最终结论而不经过系统规则整合
- 禁止省略审计日志
- 禁止删除高风险相关记录的追溯链条

### 10.3 架构禁止项

- 禁止擅自替换技术栈为 React / Next.js / Supabase
- 禁止引入与文档不一致的大型框架
- 禁止在没有更新规范文档的情况下升级核心依赖版本
- 禁止跳过 `appendices/question_bank/` 直接把题库硬编码散落在多个文件里

### 10.4 协作禁止项

- 禁止在未阅读规范文档的情况下开始编码
- 禁止忽略 `progress.txt` 与 `lessons.md`
- 禁止在发现文档冲突后继续盲写实现
- 禁止把“演示模式逻辑”和“正式逻辑”混在一起且无开关区分

## 11. AI 工作方式要求

AI 在本项目中必须遵守以下行为规则：

1. 先读规范，再动代码
2. 先检查现有结构，再创建新文件
3. 任何改动都要尽量与现有目录约定一致
4. 关键决策必须能在规范文档中找到依据
5. 如果某项实现需求超出规范范围，先指出，再建议补文档或给出默认方案

## 12. AI 输出优先级

如果 AI 同时面对“更快完成”和“更符合规范”的冲突，优先级如下：

1. 安全与伦理边界
2. 规范一致性
3. 可演示性
4. 代码可维护性
5. 开发速度

## 13. 新文件创建规则

创建新文件前，AI 必须先判断：

1. 该文件是否已有规范性归属目录？
2. 现有目录里是否已经有同职责文件？
3. 是否应该扩展现有模块，而不是新建平行模块？

如果需要新增跨模块文件，优先在对应层建立清晰目录，而不是直接丢在根目录。

## 14. 提交前自检清单

在完成一轮实现或文档修改后，AI 至少要自检以下问题：

- 是否符合 `PRD.md`
- 是否符合 `APP_FLOW.md`
- 是否符合 `TECH_STACK.md`
- 是否符合 `BACKEND_STRUCTURE.md`
- 是否违反 `FRONTEND_GUIDELINES.md`
- 是否破坏了 70 题解锁逻辑
- 是否错误地把 UPI 设为必做
- 是否遗漏审计日志
- 是否丢失 mock 容错路径

## 15. 一句话执行准则

在这个项目里，AI 的默认行为应当是：

“先读规范，按目录落位，按分层写代码，优先保证安全边界、演示闭环和可维护性。”
