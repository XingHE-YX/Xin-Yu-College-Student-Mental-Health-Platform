# 心语人工端到端演练脚本

本文档对应 `IMPLEMENTATION_PLAN.md` 步骤 `13.3`，用于在答辩前按固定顺序人工演练当前 MVP 的关键闭环，避免现场临时 improvisation。

## 1. 演练范围

本轮人工脚本覆盖 4 条链路：

1. 完整测评链路
2. 低风险树洞发布
3. 高风险树洞拦截
4. 管理员复核与模拟干预

页面与状态命名统一遵循 `APP_FLOW.md`：

- 学生端：`S01 - S16`
- 管理端：`A01 - A08`

## 2. 前置条件

### 2.1 环境准备

1. 复制并填写后端环境变量：

```bash
cd backend
cp .env.example .env
```

2. 确认 `.env` 中至少包含以下有效配置：

```env
DATABASE_URL=mysql+pymysql://xinyu_user:your_password@127.0.0.1:3306/xinyu
JWT_SECRET_KEY=your-long-random-secret
DEEPSEEK_API_KEY=your-deepseek-api-key
WECHAT_APP_ID=your-wechat-app-id
WECHAT_APP_SECRET=your-wechat-app-secret
ENABLE_DEMO_LOGIN=true
```

3. 导入题库：

```bash
cd /Users/xingheluqi/心语大学生心理健康平台/backend
.venv/bin/python -m src.utils.import_question_bank_seeds ../appendices/question_bank
```

4. 启动后端：

```bash
cd /Users/xingheluqi/心语大学生心理健康平台/backend
.venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

5. 启动管理后台：

```bash
cd /Users/xingheluqi/心语大学生心理健康平台
backend/.venv/bin/streamlit run admin/app.py
```

6. 在微信开发者工具中打开 `miniprogram/`。

### 2.2 接口地址检查

- 学生端默认请求 `http://127.0.0.1:8000/api/v1`
- 管理端默认请求 `http://127.0.0.1:8000/api/v1`

若后台接口不在本机：

- 管理端通过环境变量覆盖：
  - `XINYU_ADMIN_API_BASE_URL`
  - `ADMIN_API_BASE_URL`
- 学生端需要同步修改 [miniprogram/constants/config.js](/Users/xingheluqi/心语大学生心理健康平台/miniprogram/constants/config.js)

### 2.3 管理员账号准备

若数据库里还没有管理员账号，先创建一条本地演练账号。推荐口径：

- 用户名：`platform.admin`
- 密码：`Admin#2026`
- 角色：`platform_admin`

可用下面的一次性命令插入：

```bash
cd /Users/xingheluqi/心语大学生心理健康平台/backend
.venv/bin/python - <<'PY'
from pwdlib import PasswordHash
from sqlalchemy import select
from src.constants.account_enums import AdminRoleCode
from src.core.database import create_database_engine, create_session_factory
from src.core.settings import get_settings
from src.models import AdminUser

settings = get_settings()
engine = create_database_engine(settings)
SessionFactory = create_session_factory(engine)
password_hasher = PasswordHash.recommended()

with SessionFactory() as session:
    existing = session.scalar(
        select(AdminUser).where(AdminUser.username == "platform.admin")
    )
    if existing is None:
        session.add(
            AdminUser(
                username="platform.admin",
                password_hash=password_hasher.hash("Admin#2026"),
                role_code=AdminRoleCode.PLATFORM_ADMIN,
                display_name="平台管理员",
                is_active=True,
            )
        )
        session.commit()
        print("created platform.admin / Admin#2026")
    else:
        print("platform.admin already exists")
PY
```

### 2.4 演练账号规划

建议使用 2 个学生账号，避免不同脚本互相污染：

- 学生 A：`13800001001`
  - 用于完整测评链路
  - 用于低风险树洞发布
- 学生 B：`13800001002`
  - 用于高风险树洞拦截
  - 方便后台只出现一条新的高风险树洞工单

推荐学院 / 班级：

- 学院：`计算机学院`
- 班级：`2026级1班`

### 2.5 高风险树洞特别说明

当前 `backend/mock_response.json` 默认是低风险回退结果：

- 当 DeepSeek 可正常访问时，高风险树洞脚本按标准流程演练；
- 当 DeepSeek 不可访问时，树洞会回退成低风险发布，不适合做“高风险树洞拦截”现场演示；
- 因此在正式答辩前，应先确认 `DEEPSEEK_API_KEY` 有效且外网可达，再执行脚本 3 和脚本 4。

## 3. 开场自检

开始正式演练前，先做 5 个快速检查：

1. `GET /health` 返回 `200`
2. 小程序打开后能进入 `S01`
3. 学生端首页可显示问卷中心和树洞入口
4. `A01` 能用 `platform.admin / Admin#2026` 登录
5. `A02` 总览页能正常加载 KPI

若以上任何一项失败，本轮演练暂停，不进入正式脚本。

## 4. 脚本一：完整测评链路

### 4.1 目标

验证 `S01 -> S10A` 的必做 70 题解锁链路，确认可选 UPI 不阻塞完整报告。

### 4.2 操作账号

- 学生 A：`13800001001`

### 4.3 操作步骤

1. 打开小程序，进入 `S01 启动入口页`。
2. 若无本地会话，系统跳转到 `S02 登录页`。
3. 点击“使用微信登录”。
4. 在“手机号授权（开发联调模式）”输入：
   - 手机号：`13800001001`
   - 学院：`计算机学院`
   - 班级：`2026级1班`
5. 点击“授权手机号并登录”。
6. 首次登录应进入 `S03 授权页`。
7. 选择同意危机干预授权，进入 `S04 首页`。
8. 在首页依次进入并完成：
   - `S05 快速筛查`
   - `S06 SDS`
   - `S07 SAS`
   - `S08 睡眠问卷`
9. 每份问卷提交后确认：
   - 页面显示结果摘要
   - 风险标签可见
   - 首页进度持续增加
10. 四份必做问卷完成后，回到首页，打开“我的报告”进入 `S10 报告页`。
11. 在 `S10` 确认：
   - `70 / 70`
   - 状态为已解锁
   - 出现“查看完整报告”
12. 点击“查看完整报告”，进入 `S10A 完整报告详情页`。
13. 可选：返回首页后进入 `S09 UPI`，验证页面文案明确标注“仅作辅助参考”，且不影响已解锁状态。

### 4.4 预期结果

- 登录成功后首次用户进入 `S03`，而不是直接跳首页
- 四份必做问卷完成后才解锁 `S10A`
- 报告页展示：
  - 已完成量表摘要
  - 历史记录
  - 免责声明
- 可选 UPI 不影响完整报告解锁

### 4.5 失败即停条件

- `S10` 仍显示锁定且进度不是 `70 / 70`
- `S10A` 无法进入
- 页面出现“本结果构成诊断”之类错误表述

## 5. 脚本二：低风险树洞发布

### 5.1 目标

验证 `S11 -> S12 -> S13` 的低风险公开链路。

### 5.2 操作账号

- 学生 A：沿用脚本一账号

### 5.3 建议文案

使用明显低风险、非危机、无联系方式的内容，例如：

> 今天把测评做完了，心里轻了一点，想继续慢慢调整作息。

### 5.4 操作步骤

1. 从 `S04 首页` 进入树洞，打开 `S11 树洞广场页`。
2. 点击发帖，进入 `S12 树洞发布页`。
3. 输入建议文案。
4. 点击“匿名发布”。
5. 进入 `S13 发布成功页`。
6. 点击“返回广场”。
7. 在广场确认刚才的帖子可见。
8. 点击该帖子，进入 `S16 / 我的帖子详情` 或详情页，确认正文仍为脱敏公开版本。

### 5.5 预期结果

- 发布结果页显示“发布成功”
- 风险标签为低风险或需关注，但不是高风险
- 帖子出现在广场中
- 正文不暴露手机号、邮箱等联系方式

### 5.6 失败即停条件

- 低风险内容被错误拦截
- 广场看不到刚发布的帖子
- 公开正文出现明显联系方式

## 6. 脚本三：高风险树洞拦截

### 6.1 目标

验证 `S11 -> S12 -> S14` 的高风险拦截链路，以及“高风险内容绝不进入公开广场”。

### 6.2 操作账号

- 学生 B：`13800001002`

### 6.3 建议文案

仅用于安全演练，不在真实公开环境传播。建议使用与现有测试口径一致、能稳定表达高风险信号的文本，例如：

> 我真的不想活了，感觉没有任何意义。

### 6.4 操作步骤

1. 以学生 B 完成脚本一中的登录与授权步骤，但不要求完成全部问卷。
2. 从 `S04 首页` 进入 `S11 树洞广场页`。
3. 点击发帖，进入 `S12 树洞发布页`。
4. 输入高风险建议文案。
5. 点击“匿名发布”。
6. 观察是否进入 `S14 安全拦截页`。
7. 在拦截页确认：
   - 有严肃提醒
   - 展示热线电话
   - 没有“发布成功”反馈
8. 返回广场，确认该内容没有出现在 `S11`。

### 6.5 预期结果

- 后端返回 `safety_intercepted`
- 小程序进入 `S14`
- 页面显示求助热线
- 该内容不进入公开广场

### 6.6 失败即停条件

- 高风险内容被公开发布
- 进入的是 `S13` 而不是 `S14`
- 拦截页没有热线电话

## 7. 脚本四：管理员复核与模拟干预

### 7.1 目标

验证 `A01 -> A03 -> A04` 的人工复核、敏感详情查看、模拟通知和结案流程。

### 7.2 前置依赖

- 已先执行脚本三，并成功制造一条高风险树洞工单

### 7.3 操作账号

- 管理员：`platform.admin / Admin#2026`

### 7.4 操作步骤

1. 打开 Streamlit 管理后台，进入 `A01 管理员登录页`。
2. 使用管理员账号登录，进入 `A02 总览页`。
3. 点击“进入 A03”。
4. 在 `A03 预警队列页` 确认待复核列表里出现来自学生 B 的高风险树洞案例。
5. 点击“打开案例”进入 `A04 详情`。
6. 在详情页确认默认看到的是脱敏身份和脱敏正文，而不是完整原文。
7. 点击“展开完整原文”。
8. 核对以下信息：
   - AI 风险等级
   - AI 触发短语
   - 历史测评摘要
   - 当前可执行动作
9. 在“确认高风险”区域填写：
   - 复核说明：`人工复核确认存在持续性危险表达。`
   - 干预说明：`已写入给辅导员的模拟联系说明。`
10. 提交“确认高风险”。
11. 确认页面出现“已确认高风险，并写入模拟通知日志。”
12. 在“添加干预记录”区域补记一条跟进说明，例如：
   - `已安排次日继续跟进。`
13. 可选：最后执行“结案”，确认状态切到已结案。
14. 返回 `A03`，切换状态筛选，确认该案例已不在 `pending_review`，而进入 `confirmed_pending_intervention` 或 `closed`。

### 7.5 预期结果

- 打开详情和展开完整原文都不报错
- 确认高风险后写入模拟通知日志
- 工单状态推进成功
- 后续可继续补记干预记录和结案

### 7.6 失败即停条件

- `A03` 看不到由脚本三产生的案例
- 点击“展开完整原文”无响应或报错
- “确认高风险”后状态不变化
- “已确认”案例还能被错误驳回

## 8. 推荐演练顺序

建议按下面顺序一次性完整走查：

1. 开场自检
2. 脚本一：完整测评链路
3. 脚本二：低风险树洞发布
4. 脚本三：高风险树洞拦截
5. 脚本四：管理员复核与模拟干预

这样可以把学生端“平静、可信、低压”的常规路径与后台“高信息密度、可审计”的风险路径分开演示，节奏更稳定。

## 9. 演练记录模板

每次演练后，至少记录以下结果：

- 日期：
- 后端地址：
- 数据库：
- DeepSeek 是否可用：
- 管理员账号是否可登录：
- 脚本一是否通过：
- 脚本二是否通过：
- 脚本三是否通过：
- 脚本四是否通过：
- 中断点：
- 下次演练前需修复项：

## 10. 与当前实现的边界

1. 当前还没有 `14.2` 里的 `ENABLE_MOCK_AI` 与 `SHOW_SEEDED_CASES`，所以高风险树洞演练依赖可用的 DeepSeek 外网调用。
2. 当前还没有 `14.1` 的演示种子数据，因此工单、帖子和用户目录主要依赖现场手动制造。
3. 当前手册已经能指导“从空库到一轮可走通演练”，但若要做到答辩现场完全离线、完全可控，后续仍应继续完成 `14.1` 和 `14.2`。
