# TODO — Agent 能力扩展

> 状态：方案讨论中，尚未实施。决策确认后按此文档实施。

## 背景

当前 Assistant（AI 助手）只有 `knowledge_base_search` 一个工具，且仅 KB_SEARCH 模式可用；CHAT 模式 `tools=[]`（`app/assistant/agent/factory.py:42`）。本批需求扩展 Agent 的工具能力与可观测性。

---

## 需求 1：更多 Agent 工具

**目标**：Agent 能管理文档、查看群组，而不只是搜索内容。

**新工具清单**（复用现有 service，新增 `app/assistant/agent/tools.py`）：

| 工具 | 参数 | 数据来源 |
|---|---|---|
| `list_my_groups` | 无 | group service（无需 group_id，无权限问题） |
| `list_group_documents` | group_id, status? | DocumentQueryService.list_documents |
| `list_group_members` | group_id | GroupMembershipService.list_members |
| `get_group_stats` | group_id | 轻量统计（文档数/切片数/成员数） |
| `knowledge_base_search` | query, group_id | 已有 |

**安全约束**：带 group_id 的工具内部必须调 `require_group_access(user_id, system_role, group_id)` 校验成员身份；校验失败返回"无权访问"，由 Agent 如实告知用户。

## 需求 2：多工具协作

**目标**：Agent 在一轮对话中调用多个工具（如：list_my_groups → 选群组 → 列文档 → 搜索内容）。

**现状障碍**：
- CHAT 模式 `tools=[]`
- KB_SEARCH 模式 `has_completed_search` 限制每轮仅 1 次搜索

**设计**：
- CHAT 模式开放全部工具；KB_SEARCH 保持单工具 + 单次搜索（检索模式的产品语义）
- `recursion_limit` 10 → 15~20（多轮工具调用消耗轮次，`factory.py`）
- 工具返回统一 JSON 格式（found / data / message）

## 需求 3：工具调用可视化

**目标**：前端展示 Agent 的"思考过程"——调用了哪些工具、参数是什么、结果如何。

**现状**：
- 后端从不保存 TOOL 消息（`service.py` 只存 USER/ASSISTANT）
- `facade.chat_stream` 只捕获 `on_tool_end` 提取 citations，无 `on_tool_start`
- 前端 `AssistantMessage.vue` 已有 TOOL 消息 `<details>` 折叠样式基础，但只显示 content 原文

**设计（实时 + 落库双轨）**：
- 后端：facade 补捕获 `on_tool_start` / `on_tool_end` → SSE 新增 `tool_start` {name, args} / `tool_end` {name, result 截断} 事件
- 后端：工具调用落库为 TOOL 消息（content 存 JSON：tool_name / args / result），重进会话可查
- 前端：流式时插入"工具调用"卡片（工具名 + 参数 + 结果摘要，可折叠，按顺序堆叠）；历史 TOOL 消息从 DB 加载并结构化渲染

---

## 待决策问题（确认后开始实施）

- [ ] **P1 工具集开放范围**
  - A. CHAT 全开放（推荐）：CHAT 挂全部 5 个工具；KB_SEARCH 保持单工具 + 单次搜索
  - B. 只加管理工具：文档/群组工具全局可用，KB 搜索仍只限 KB_SEARCH
  - C. 全部模式全开放：KB_SEARCH 也取消单次搜索限制

- [ ] **P2 CHAT 模式群组确定方式**
  - A. 选择器 + 自发现（推荐）：CHAT 模式 Composer 可选群组（选了就传给 Agent）；没选时 Agent 用 `list_my_groups` 自发现或询问
  - B. 仅 Agent 自发现：CHAT 不传群组，一律靠工具/对话确认
  - C. 必须显式选择：CHAT 也要先选群组才能提问

- [ ] **P3 可视化是否持久化**
  - A. 实时 + 落库持久化（推荐）：流式实时卡片 + TOOL 消息落库，历史可查
  - B. 仅实时展示：不落库，重进会话看不到工具调用

---

## 实施清单（决策后按序执行）

1. `app/assistant/agent/tools.py`：新增 4 个工具（list_my_groups / list_group_documents / list_group_members / get_group_stats），带 group_id 的工具加权限校验
2. `app/assistant/agent/factory.py`：按决策开放工具集；recursion_limit 调整
3. `app/assistant/agent/facade.py`：捕获 on_tool_start / on_tool_end，输出结构化事件；返回工具调用记录
4. `app/assistant/service.py`：工具调用落库 TOOL 消息（chat / chat_stream）
5. `app/assistant/router.py`：SSE 事件扩展（tool_start / tool_end）
6. 前端 `types/assistant.ts` / `api/assistant.ts`：事件类型扩展
7. 前端 `AssistantView.vue`：流式工具卡片渲染
8. 前端 `AssistantMessage.vue`：TOOL 消息结构化展示（工具名/参数/结果）
9. 验证：权限校验（非成员调工具拒绝）、多工具协作链路、历史 TOOL 消息回显
