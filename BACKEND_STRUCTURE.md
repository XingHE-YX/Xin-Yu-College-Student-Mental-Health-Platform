# 心语后端结构文档

## 1. 后端范围

后端承担三类职责：

1. 面向学生端的 API：登录、测评、报告、树洞、帮助资源；
2. 面向管理端的 API：预警复核、内容管理、统计分析、审计追踪；
3. 风险规则引擎与 AI 接入层。

## 2. 服务边界

- `FastAPI` 负责所有 HTTP API 与业务规则实现；
- `MySQL` 负责事务数据存储；
- `Streamlit` 只调用 FastAPI 的后台接口，不直接写数据库；
- AI 调用只能在服务端完成；
- 小程序端不得直接调用 DeepSeek。

## 3. API 约定

### 3.1 基础路径

- Base path：`/api/v1`

### 3.2 标准成功响应包

```json
{
  "code": "OK",
  "message": "success",
  "request_id": "01HXYZ...",
  "data": {}
}
```

### 3.3 标准错误响应包

```json
{
  "code": "VALIDATION_ERROR",
  "message": "questionnaire submission is incomplete",
  "request_id": "01HXYZ...",
  "errors": [
    {
      "field": "answers[5]",
      "reason": "missing answer"
    }
  ]
}
```

### 3.4 时间与主键规则

- 主键：`BIGINT UNSIGNED AUTO_INCREMENT`
- 存储时区：UTC
- 时间精度：`DATETIME(3)`

## 4. 数据库模式

### 4.1 `student_users`

用途：学生主账户表。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `phone_e164` | `VARCHAR(20)` | 否 | 唯一登录手机号 |
| `wechat_openid` | `VARCHAR(64)` | 是 | 微信唯一标识，可唯一 |
| `display_nickname` | `VARCHAR(32)` | 否 | 前台匿名昵称 |
| `display_avatar_seed` | `VARCHAR(64)` | 否 | 头像生成种子 |
| `college_name` | `VARCHAR(64)` | 否 | 学院名称 |
| `class_name` | `VARCHAR(64)` | 否 | 班级名称 |
| `risk_status` | `ENUM('normal','watch','high')` | 否 | 当前综合风险状态 |
| `consent_status` | `ENUM('granted','declined','missing')` | 否 | 授权状态 |
| `is_demo` | `TINYINT(1)` | 否 | 是否为演示账号 |
| `last_login_at` | `DATETIME(3)` | 是 | 最后登录时间 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |
| `updated_at` | `DATETIME(3)` | 否 | 更新时间 |

### 4.2 `consent_records`

用途：记录不可变更的授权决策。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `student_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `student_users.id` |
| `consent_type` | `ENUM('privacy_policy','crisis_intervention_authorization')` | 否 | 授权类型 |
| `consent_version` | `VARCHAR(16)` | 否 | 文案版本号 |
| `granted` | `TINYINT(1)` | 否 | 是否同意 |
| `granted_at` | `DATETIME(3)` | 否 | 决策时间 |
| `ip_address` | `VARCHAR(45)` | 是 | 可选 IP |
| `user_agent` | `VARCHAR(255)` | 是 | 可选终端信息 |

### 4.3 `admin_users`

用途：管理端账户与授权信息。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `username` | `VARCHAR(64)` | 否 | 唯一用户名 |
| `password_hash` | `VARCHAR(255)` | 否 | Argon2 密码哈希 |
| `role_code` | `ENUM('platform_admin','counselor','advisor')` | 否 | 预留多角色模型 |
| `display_name` | `VARCHAR(64)` | 否 | 管理员显示名 |
| `is_active` | `TINYINT(1)` | 否 | 是否允许登录 |
| `last_login_at` | `DATETIME(3)` | 是 | 最后登录时间 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |
| `updated_at` | `DATETIME(3)` | 否 | 更新时间 |

### 4.4 `questionnaire_templates`

用途：问卷模板元数据表。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `code` | `VARCHAR(32)` | 否 | 唯一编码，如 `SCREEN`、`SDS` |
| `name` | `VARCHAR(128)` | 否 | 问卷名称 |
| `category` | `ENUM('required','optional')` | 否 | 必做 / 可选 |
| `question_count` | `SMALLINT UNSIGNED` | 否 | 题量 |
| `scoring_mode` | `ENUM('sum_1_5','sum_0_3','zung_standard','yes_no')` | 否 | 评分模式 |
| `unlock_required` | `TINYINT(1)` | 否 | 是否参与完整报告解锁 |
| `is_active` | `TINYINT(1)` | 否 | 是否启用 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |

### 4.5 `question_bank`

用途：可直接录库的题库表。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `template_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `questionnaire_templates.id` |
| `question_code` | `VARCHAR(32)` | 否 | 唯一题目编码，如 `SCREEN_01` |
| `question_order` | `SMALLINT UNSIGNED` | 否 | 展示顺序 |
| `question_text` | `TEXT` | 否 | 题目正文 |
| `question_type` | `ENUM('single_choice','yes_no')` | 否 | 题目类型 |
| `options_json` | `JSON` | 否 | 选项定义 |
| `score_mapping_json` | `JSON` | 否 | 选项到分值映射 |
| `reverse_scored` | `TINYINT(1)` | 否 | SDS/SAS 反向计分标记 |
| `hard_trigger_rule_json` | `JSON` | 是 | 硬触发规则定义 |
| `seed_source` | `VARCHAR(128)` | 否 | 来源附录文件名 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |

### 4.6 `questionnaire_submissions`

用途：一次完整问卷提交记录。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `student_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `student_users.id` |
| `template_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `questionnaire_templates.id` |
| `started_at` | `DATETIME(3)` | 否 | 开始作答时间 |
| `submitted_at` | `DATETIME(3)` | 否 | 提交时间 |
| `status` | `ENUM('submitted','scored')` | 否 | 提交状态 |
| `raw_score` | `INT` | 否 | 原始得分 |
| `standardized_score` | `INT` | 是 | SDS/SAS 标准分 |
| `risk_level` | `ENUM('low','watch','high')` | 否 | 问卷结果风险等级 |
| `hard_trigger_hit` | `TINYINT(1)` | 否 | 是否命中硬触发 |
| `scoring_snapshot_json` | `JSON` | 否 | 评分说明快照 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |

### 4.7 `questionnaire_answers`

用途：问卷逐题答案明细。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `submission_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `questionnaire_submissions.id` |
| `question_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `question_bank.id` |
| `selected_option` | `VARCHAR(32)` | 否 | 用户选择项 |
| `raw_value` | `VARCHAR(32)` | 否 | 前端原始值 |
| `normalized_score` | `INT` | 否 | 归一化分值 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |

### 4.8 `assessment_reports`

用途：保存量表结果与完整报告。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `student_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `student_users.id` |
| `report_type` | `ENUM('scale_result','full_profile')` | 否 | 报告类型 |
| `report_version` | `VARCHAR(16)` | 否 | 报告版本 |
| `source_submission_ids_json` | `JSON` | 否 | 来源提交记录集合 |
| `risk_level` | `ENUM('low','watch','high')` | 否 | 报告风险等级 |
| `result_title` | `VARCHAR(128)` | 否 | 报告标题 |
| `content_json` | `JSON` | 否 | 可直接渲染的报告内容 |
| `created_at` | `DATETIME(3)` | 否 | 生成时间 |

### 4.9 `treehole_posts`

用途：树洞内容存储与发布状态管理。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `student_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `student_users.id` |
| `anonymous_name` | `VARCHAR(64)` | 否 | 匿名展示名 |
| `anonymous_avatar_key` | `VARCHAR(64)` | 否 | 匿名头像标识 |
| `content_raw` | `MEDIUMTEXT` | 否 | 原始文本 |
| `content_masked` | `MEDIUMTEXT` | 是 | 脱敏后可公开文本 |
| `ai_status` | `ENUM('pending','analyzed','mocked','failed')` | 否 | AI 处理状态 |
| `publish_status` | `ENUM('pending_review','published','blocked_high_risk','deleted_by_user','hidden_by_admin')` | 否 | 发布状态 |
| `risk_level` | `ENUM('low','watch','high')` | 否 | 树洞综合风险等级 |
| `allow_publication` | `TINYINT(1)` | 否 | 是否允许进入广场 |
| `hug_count` | `INT UNSIGNED` | 否 | 预设互动计数 |
| `published_at` | `DATETIME(3)` | 是 | 发布时间 |
| `deleted_at` | `DATETIME(3)` | 是 | 软删除时间 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |
| `updated_at` | `DATETIME(3)` | 否 | 更新时间 |

### 4.10 `ai_analysis_records`

用途：保存 AI 原始响应与解析结果。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `target_type` | `ENUM('treehole_post')` | 否 | 分析目标类型 |
| `target_id` | `BIGINT UNSIGNED` | 否 | 分析目标 ID |
| `provider` | `ENUM('deepseek')` | 否 | 服务提供方 |
| `model_name` | `VARCHAR(64)` | 否 | 固定为 `deepseek-chat` |
| `request_payload_json` | `JSON` | 否 | 请求快照 |
| `response_raw_json` | `JSON` | 是 | 原始返回 |
| `parsed_risk_level` | `ENUM('low','watch','high')` | 否 | 解析后的风险等级 |
| `parsed_risk_score` | `DECIMAL(5,4)` | 否 | 类置信度得分 |
| `emotion_tags_json` | `JSON` | 否 | 情绪标签数组 |
| `trigger_phrases_json` | `JSON` | 否 | 触发短语数组 |
| `reason_text` | `TEXT` | 否 | 可读理由 |
| `recommended_action` | `ENUM('publish','focus_list','manual_review_high')` | 否 | 推荐动作 |
| `fallback_used` | `TINYINT(1)` | 否 | 是否使用模拟回退 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |

### 4.11 `alert_cases`

用途：预警队列与工单状态机。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `student_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `student_users.id` |
| `source_type` | `ENUM('treehole','assessment','history')` | 否 | 工单来源 |
| `source_post_id` | `BIGINT UNSIGNED` | 是 | 外键 -> `treehole_posts.id` |
| `source_submission_id` | `BIGINT UNSIGNED` | 是 | 外键 -> `questionnaire_submissions.id` |
| `case_level` | `ENUM('watch','high')` | 否 | 案例级别 |
| `queue_status` | `ENUM('pending_review','confirmed_pending_intervention','dismissed_false_positive','closed')` | 否 | 状态流转 |
| `review_priority` | `ENUM('normal','urgent','highest')` | 否 | 复核优先级 |
| `ai_reason_text` | `TEXT` | 是 | AI 原因摘要 |
| `review_note` | `TEXT` | 是 | 管理员复核说明 |
| `reviewed_by` | `BIGINT UNSIGNED` | 是 | 外键 -> `admin_users.id` |
| `reviewed_at` | `DATETIME(3)` | 是 | 复核时间 |
| `simulated_notice_log` | `TEXT` | 是 | 模拟通知日志 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |
| `updated_at` | `DATETIME(3)` | 否 | 更新时间 |

### 4.12 `intervention_logs`

用途：记录每个工单的干预时间线。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `alert_case_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `alert_cases.id` |
| `admin_user_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `admin_users.id` |
| `action_type` | `ENUM('confirm_high_risk','dismiss_false_positive','simulate_contact','add_note','close_case')` | 否 | 动作类型 |
| `action_note` | `TEXT` | 是 | 动作说明 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |

### 4.13 `focus_list_entries`

用途：承载“需关注”级别的后台重点关注列表。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `student_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `student_users.id` |
| `source_type` | `ENUM('treehole','assessment','history')` | 否 | 来源类型 |
| `source_id` | `BIGINT UNSIGNED` | 否 | 来源记录 ID |
| `reason_code` | `VARCHAR(64)` | 否 | 关注原因编码 |
| `reason_text` | `TEXT` | 否 | 关注原因说明 |
| `status` | `ENUM('active','resolved')` | 否 | 生命周期 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |
| `resolved_at` | `DATETIME(3)` | 是 | 解决时间 |

### 4.14 `post_reactions`

用途：保存树洞预设互动行为。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `post_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `treehole_posts.id` |
| `student_id` | `BIGINT UNSIGNED` | 否 | 外键 -> `student_users.id` |
| `reaction_type` | `ENUM('hug','light','accompany')` | 否 | 互动类型 |
| `created_at` | `DATETIME(3)` | 否 | 创建时间 |

唯一约束：

- `UNIQUE(post_id, student_id, reaction_type)`

### 4.15 `audit_logs`

用途：追踪所有敏感操作。

| 字段 | 类型 | 可空 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT UNSIGNED` | 否 | 主键 |
| `actor_type` | `ENUM('student','admin','system')` | 否 | 操作人类型 |
| `actor_id` | `BIGINT UNSIGNED` | 是 | 操作人 ID |
| `action_code` | `VARCHAR(64)` | 否 | 操作编码，如 `ADMIN_VIEW_SENSITIVE_ALERT_DETAIL` |
| `target_type` | `VARCHAR(64)` | 否 | 目标对象类型 |
| `target_id` | `BIGINT UNSIGNED` | 是 | 目标对象 ID |
| `metadata_json` | `JSON` | 是 | 额外元数据 |
| `ip_address` | `VARCHAR(45)` | 是 | 来源 IP |
| `created_at` | `DATETIME(3)` | 否 | 时间戳 |

## 5. 关系概览

- `student_users` 1:N `consent_records`
- `student_users` 1:N `questionnaire_submissions`
- `questionnaire_templates` 1:N `question_bank`
- `questionnaire_submissions` 1:N `questionnaire_answers`
- `student_users` 1:N `assessment_reports`
- `student_users` 1:N `treehole_posts`
- `treehole_posts` 1:N `ai_analysis_records`
- `student_users` 1:N `alert_cases`
- `alert_cases` 1:N `intervention_logs`
- `student_users` 1:N `focus_list_entries`
- `treehole_posts` 1:N `post_reactions`

## 6. 认证逻辑

### 6.1 学生端认证流程

1. 小程序调用 `wx.login`。
2. 客户端将 `login_code` 发送给后端。
3. 后端与微信交换会话信息。
4. 客户端完成手机号授权。
5. 后端创建或更新 `student_users`。
6. 后端签发学生端 JWT。
7. 小程序安全存储会话令牌。

规则要求：

- 只有 `consent_status = granted` 的用户才允许发布树洞；
- 即使拒绝授权，也允许学生完成基础测评；
- 演示登录入口仅在 `ENABLE_DEMO_LOGIN=true` 时开放。

### 6.2 管理端认证流程

1. 管理员提交用户名和密码；
2. 后端通过 `pwdlib` + Argon2 校验密码；
3. 后端签发管理员 JWT；
4. Streamlit 使用 session state 保存令牌。

规则要求：

- 仅 `is_active=1` 的管理员允许登录；
- 所有敏感详情接口必须要求管理员认证。

## 7. 学生端 API 合约

### 7.1 认证接口

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/student/wechat-login` | 否 | 创建或刷新学生会话 |
| `POST` | `/api/v1/auth/student/demo-login` | 否 | 演示模式登录 |
| `GET` | `/api/v1/auth/student/me` | Student | 获取当前学生信息 |

#### `POST /api/v1/auth/student/wechat-login`

请求体：

```json
{
  "login_code": "wx_login_code",
  "phone_ticket": "encrypted_phone_payload",
  "phone_signature": "signature_if_needed",
  "consent_status": "granted"
}
```

响应体：

```json
{
  "code": "OK",
  "message": "success",
  "request_id": "01HX...",
  "data": {
    "access_token": "jwt",
    "student": {
      "id": 1,
      "display_nickname": "Quiet Ginkgo",
      "college_name": "Computer Science College",
      "class_name": "Class 1"
    }
  }
}
```

### 7.2 授权接口

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/consents` | Student | 保存授权决策 |

### 7.3 问卷元数据与提交流程

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/questionnaires` | Student | 获取问卷列表 |
| `GET` | `/api/v1/questionnaires/{code}` | Student | 获取单份问卷详情 |
| `POST` | `/api/v1/questionnaires/{code}/submissions` | Student | 提交问卷答案 |
| `GET` | `/api/v1/questionnaires/progress` | Student | 获取必做进度 |

#### `POST /api/v1/questionnaires/{code}/submissions`

请求体：

```json
{
  "answers": [
    {
      "question_code": "SCREEN_01",
      "selected_option": "4"
    }
  ]
}
```

响应体：

```json
{
  "code": "OK",
  "message": "success",
  "request_id": "01HX...",
  "data": {
    "submission_id": 1001,
    "questionnaire_code": "SCREEN",
    "raw_score": 52,
    "standardized_score": null,
    "risk_level": "watch",
    "hard_trigger_hit": false
  }
}
```

### 7.4 报告接口

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/reports/summary` | Student | 获取报告解锁状态与摘要 |
| `GET` | `/api/v1/reports/full` | Student | 获取完整报告 |
| `GET` | `/api/v1/reports/history` | Student | 获取历史测评记录 |

### 7.5 树洞接口

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/treehole/feed` | Student | 获取公开广场内容 |
| `POST` | `/api/v1/treehole/posts` | Student | 提交树洞内容 |
| `DELETE` | `/api/v1/treehole/posts/{post_id}` | Student | 软删除自己的帖子 |
| `POST` | `/api/v1/treehole/posts/{post_id}/reactions` | Student | 提交预设互动 |

#### `POST /api/v1/treehole/posts`

请求体：

```json
{
  "content": "I feel exhausted and do not know what to do anymore."
}
```

低风险响应：

```json
{
  "code": "OK",
  "message": "success",
  "request_id": "01HX...",
  "data": {
    "post_id": 501,
    "risk_level": "low",
    "publish_status": "published"
  }
}
```

高风险响应：

```json
{
  "code": "OK",
  "message": "safety_intercepted",
  "request_id": "01HX...",
  "data": {
    "post_id": 502,
    "risk_level": "high",
    "publish_status": "blocked_high_risk",
    "hotline": "Campus hotline placeholder"
  }
}
```

### 7.6 帮助资源接口

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/resources/help` | Student | 获取静态帮助资源与热线信息 |

## 8. 管理端 API 合约

### 8.1 管理员认证

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/admin/auth/login` | 否 | 管理员登录 |
| `GET` | `/api/v1/admin/auth/me` | Admin | 获取当前管理员信息 |

### 8.2 总览与统计

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/dashboard/summary` | Admin | 获取总览 KPI |
| `GET` | `/api/v1/admin/analytics/trends` | Admin | 获取趋势统计数据 |

### 8.3 预警队列

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/alerts` | Admin | 获取工单列表 |
| `GET` | `/api/v1/admin/alerts/{alert_id}` | Admin | 获取工单详情 |
| `POST` | `/api/v1/admin/alerts/{alert_id}/confirm` | Admin | 确认高风险 |
| `POST` | `/api/v1/admin/alerts/{alert_id}/dismiss` | Admin | 标记误报 |
| `POST` | `/api/v1/admin/alerts/{alert_id}/close` | Admin | 结案 |

#### `POST /api/v1/admin/alerts/{alert_id}/confirm`

请求体：

```json
{
  "review_note": "Manual review confirms strong self-harm language.",
  "intervention_note": "Simulated outreach logged."
}
```

响应体：

```json
{
  "code": "OK",
  "message": "success",
  "request_id": "01HX...",
  "data": {
    "alert_id": 301,
    "queue_status": "confirmed_pending_intervention",
    "simulated_notice_log": "[SIMULATED] Notification recorded for counselor follow-up."
  }
}
```

### 8.4 帖子管理

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/posts` | Admin | 按状态获取帖子列表 |
| `GET` | `/api/v1/admin/posts/{post_id}` | Admin | 获取帖子详情 |
| `PATCH` | `/api/v1/admin/posts/{post_id}/visibility` | Admin | 隐藏或恢复帖子 |

### 8.5 用户目录

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/users` | Admin | 获取脱敏用户列表 |
| `GET` | `/api/v1/admin/users/{student_id}` | Admin | 获取用户敏感详情 |

### 8.6 审计接口

| Method | Path | Auth | 用途 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/audit-logs` | Admin | 查询审计日志 |

## 9. 规则引擎行为

### 9.1 问卷规则

- 快速筛查：
  - `SCREEN_15 >= 4` -> 高风险
  - 总分 `>= 45` -> 至少为需关注
- SDS：
  - 第 15 题回答 `>= 4` -> 高风险
  - 标准分 `53-62` -> 需关注
  - 标准分 `>= 63` -> 高风险
- SAS：
  - 第 13 题回答 `>= 4` -> 高风险
  - 标准分 `50-59` -> 需关注
  - 标准分 `>= 60` -> 高风险
- 睡眠问卷：
  - `8-14` -> 需关注
  - `>= 15` -> 高风险
- UPI：
  - `UPI_01=yes` 或 `UPI_02=yes` -> 高风险
  - 其余情况仅做辅助参考

### 9.2 树洞 + AI 规则

- 低风险：
  - 发布帖子
  - 不创建预警工单
- 需关注：
  - 发布帖子
  - 写入 `focus_list_entries`
  - 不写模拟通知
- 高风险：
  - 阻止发布
  - 创建最高优先级 `alert_cases`
  - 给学生端返回安全拦截提示

### 9.3 不完整数据场景规则

- 只有树洞：
  - AI 高风险 -> 高风险
  - AI 消极但不涉自伤自杀 -> 需关注
- 只有量表：
  - SDS / SAS 任一阳性 -> 需关注
  - SDS `>= 63` 或 SAS `>= 60` -> 高风险
- 历史高风险但本次中性：
  - 标记为需关注并提示复查

## 10. 审计规则

以下操作必须写入 `audit_logs`：

- 管理员登录成功
- 管理员展开敏感预警详情
- 管理员展开敏感用户详情
- 管理员导出任何表格或报表
- 管理员确认、驳回、结案
- 管理员查看完整手机号
- 系统生成模拟通知日志

## 11. 安全规则

- 学生端公开广场接口绝不返回 `content_raw`；
- 公开广场只返回 `content_masked`；
- 管理员列表接口只返回脱敏手机号；
- 完整手机号只允许在详情页显式展开；
- MVP 不强制采集真实姓名。

## 12. 种子数据与附录策略

题库最终通过以下目录中的文件录入数据库：

```text
appendices/question_bank/
```

必须包含的种子文件：

- `screen_questions.json`
- `sleep_questions.json`
- `upi_questions.json`
- `sds_questions.json`
- `sas_questions.json`

每条题目数据至少包含以下字段：

- `question_id`
- `question_text`
- `question_type`
- `options`
- `score_mapping`
- `reverse_scored`
- `hard_trigger_rule`
