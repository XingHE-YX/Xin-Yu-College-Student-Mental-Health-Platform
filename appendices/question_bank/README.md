# 题库种子文件结构

本目录用于存放可直接录入 `questionnaire_templates` 和 `question_bank` 的题库附录文件。

## 顶层结构

每个题库文件都使用统一 JSON 结构：

```json
{
  "template": {
    "code": "SCREEN",
    "name": "快速筛查",
    "category": "required",
    "question_count": 15,
    "scoring_mode": "sum_1_5",
    "unlock_required": true,
    "is_active": true
  },
  "questions": [
    {
      "question_id": "SCREEN_01",
      "question_text": "最近一周，你是否经常感到紧张？",
      "question_type": "single_choice",
      "options": [
        { "value": "1", "label": "从不" },
        { "value": "2", "label": "偶尔" },
        { "value": "3", "label": "有时" },
        { "value": "4", "label": "经常" },
        { "value": "5", "label": "总是" }
      ],
      "score_mapping": {
        "1": 1,
        "2": 2,
        "3": 3,
        "4": 4,
        "5": 5
      },
      "reverse_scored": false,
      "hard_trigger_rule": null
    }
  ]
}
```

## 必填字段

每条题目必须包含以下字段：

- `question_id`
- `question_text`
- `question_type`
- `options`
- `score_mapping`
- `reverse_scored`
- `hard_trigger_rule`

## 字段约束

- `template.code` 必须与题目 `question_id` 前缀一致，例如 `SCREEN_01`、`SDS_15`。
- `template.question_count` 必须等于 `questions` 数组长度。
- `question_id` 的数字后缀必须与数组顺序一致，数组顺序将被后续导入脚本映射为 `question_order`。
- `question_type` 目前仅支持 `single_choice` 和 `yes_no`。
- `options` 中的 `value` 必须唯一，`score_mapping` 的键必须与 `options.value` 完全一致。
- `yes_no` 题型必须使用 `yes` / `no` 作为选项值，且不能设置 `reverse_scored=true`。
- `hard_trigger_rule` 可以为 `null`，也可以使用以下结构：

```json
{
  "operator": ">=",
  "value": 4,
  "risk_level": "high",
  "reason_code": "HT-01"
}
```

- `single_choice` 题常用 `>=` 触发阈值，`yes_no` 题必须使用 `==`，例如：

```json
{
  "operator": "==",
  "value": "yes",
  "risk_level": "high",
  "reason_code": "HT-04"
}
```

## 校验脚本

在仓库根目录运行：

```bash
PYTHONPATH=backend backend/.venv/bin/python -m src.utils.validate_question_bank_seeds appendices/question_bank
```

或先进入 `backend/` 再运行：

```bash
.venv/bin/python -m src.utils.validate_question_bank_seeds
```

当前阶段只定义统一结构和校验方式。实际题目内容文件将在后续步骤中写入：

- `screen_questions.json`
- `sleep_questions.json`
- `upi_questions.json`
- `sds_questions.json`
- `sas_questions.json`
