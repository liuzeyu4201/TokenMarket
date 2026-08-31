# 有界指标标签

允许：`protocol` `endpoint` `status` `plane` `stream` `result` `reason` `state`

禁止：`user_id` `project_id` `request_id` `account_id` `api_key` 及任何无界标识。

系列组合上限由实现守卫；超出则丢弃样本而不是扩展基数。
