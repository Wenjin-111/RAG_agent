# TODO

> 本文件记录待实施的方案。分节记录，各自独立。

---

# 一、管理助手（管理员 Agent）

> 状态：方案已定稿（2026-08-02 决策确认），待实施。

## 背景

现有 Assistant 只有 `knowledge_base_search` 一个工具（仅 KB_SEARCH 模式）。本需求为**管理员**新增一个"管理助手"：独立入口 + 管理类工具（文档/群组）+ 工具调用可视化（实时卡片 + 落库回显）。普通用户工具扩展见文末"后续"。

**已确认决策**：独立管理页（/admin/assistant）｜可视化一起做｜普通用户暂不做｜一条调用一条 TOOL 消息｜参数截断 200 / 结果截断 500｜**含写操作**（对话确认机制）。

---

## 工具集（9 个）

读工具（蓝色卡片）：

| 工具 | 参数 | 数据来源 |
|---|---|---|
| `list_groups` | 无 | 群组 admin 全量列表 |
| `get_group_stats` | group_id | 群组详情（文档数/存储/成员数） |
| `list_group_members` | group_id | 群组成员 |
| `list_documents` | group_id?, status?, keyword? | 文档 admin 分页 |
| `search_knowledge` | query | 复用现有 HybridChunkRetrievalService |

写工具（琥珀色卡片，**必须对话确认后调用**）：

| 工具 | 参数 | 说明 |
|---|---|---|
| `ban_group` | group_id | 停用群组 |
| `unban_group` | group_id | 恢复群组 |
| `delete_document` | document_id | 删除文档 |

**写操作确认机制（对话确认）**：
- 管理助手 prompt 强约束：涉及停用/删除必须先向用户说明影响（群组名/文档名）并取得明确同意，才能调用写工具
- 工具描述中同样注明"仅当用户明确同意后调用"
- 前端写工具卡片用琥珀色警示
- 后续升级项：LangGraph `interrupt()` 硬确认（human-in-the-loop）

## 权限模型

- `config` 传 `system_role`，所有管理工具内部校验 `system_role == "ADMIN"`，非管理员返回"无权访问"（工具层校验，防绕过前端）
- 创建 agent 时按角色挂载工具：仅 ADMIN 挂管理工具（双保险）
- 工具复用现有 admin service（`AdminUserService` / group service / document service），不重复实现

## 工具调用处理（可视化 + 落库）

**事件捕获**（`facade.py`，沿用 LangGraph `astream_events` 标准模式）：
- `on_tool_start`：`event["name"]` + `event["data"]["input"]` → SSE `tool_start` {id, name, args}
- `on_tool_end`：`event["data"]["output"]` → SSE `tool_end` {id, name, result(截断500), status}
- 稳定 key 用 `event["run_id"]`（前端原地更新卡片）
- 同时追加到 `result_holder.tool_calls`（流结束后落库）

**落库**：
- `AssistantMessage.role` 扩展 `TOOL`（现有 USER/ASSISTANT）
- 一条工具调用 = 一条 TOOL 消息，content 存 JSON：`{tool_name, args, result, status}`（args 截断 200 / result 截断 500）
- 角色顺序：USER → TOOL... → ASSISTANT

**会话区分**：
- `AssistantSession` 加 `mode` 字段（CHAT / KB_SEARCH / ADMIN），管理助手会话 mode=ADMIN，会话列表按 mode 过滤

## 前端

**流式工具卡片**（扩展 `AssistantMessage.vue` / 新增组件）：
- `tool_start` 到达 → 插入卡片（工具名 + 参数摘要 + 加载动画，默认展开）
- `tool_end` 到达 → 原地更新（成功显示结果摘要、失败红字；超长截断 + 点击展开）
- 读工具蓝调 / 写工具琥珀调；多工具按顺序堆叠

**管理助手页面** `/admin/assistant`：
- 管理控制台侧边栏入口，独立会话列表（mode=ADMIN）
- 历史 TOOL 消息 → 同款卡片（默认收起）

## 实施清单

1. 后端 `tools.py`：新增 8 个工具（5 读 + 3 写），全部校验 ADMIN；写工具返回格式带 warning
2. 后端 `factory.py`：新增 `ADMIN` tool_mode，挂全部工具；recursion_limit 10 → 15
3. 后端 `facade.py`：捕获 on_tool_start / on_tool_end → SSE 事件 + result_holder.tool_calls
4. 后端 `models.py`：AssistantSession.mode 字段；AssistantMessage.role 支持 TOOL
5. 后端 `service.py`：TOOL 消息落库（args/result 截断）；历史加载包含 TOOL 消息
6. 后端 `router.py`：SSE 事件扩展（tool_start / tool_end）；会话列表按 mode 过滤
7. 前端 `types/assistant.ts` / `api/assistant.ts`：事件类型 + TOOL 消息类型
8. 前端：管理助手页面（路由 + 菜单 + 会话列表 + 聊天区）
9. 前端：工具卡片组件（流式 + 历史回显）
10. 验证：admin 权限校验、多工具协作、写工具确认链路、历史 TOOL 回显

---

## 后续（普通用户工具扩展）

TODO 旧方案（list_my_groups / list_group_documents / list_group_members / get_group_stats，带 `require_group_access` 校验，CHAT 模式开放）——管理员助手落地后再做，机制完全复用。

---

# 二、ES 安装 IK 中文分词插件

> 状态：待办。2026-08-02 排查 ES 检索 0 命中时发现。

## 背景

docker-compose.yml 中 ES 用的是官方原版镜像（`docker.elastic.co/elasticsearch/elasticsearch:8.15.0`，注释写"+ IK 中文分词"但实际从未安装插件）。`ensure_index` 创建索引时指定的 `ik_max_word_analyzer` 实际失败（代码只 `logger.warning` 未报错），当前索引 mapping 是 standard 逐字分词 → **中文全文检索质量差**（短语匹配基本失效）。已确认：`settings.analysis` 为空、`ik_max_word_analyzer` 分析器不存在。

## 方案（推荐 A）

- **A. 换镜像（推荐）**：`image: medcl/elasticsearch:8.15.0`（ik 作者维护，版本对齐官方）→ `docker compose up -d elasticsearch` 重建。改一行，1 分钟。
- B. 手动装进现有容器：`docker exec argus-es bin/elasticsearch-plugin install --batch https://get.infini.cloud/elasticsearch/analysis-ik/8.15.0` + restart。容器重建后需重装，不持久。
- C. Dockerfile 自定义镜像（最正规，多一个文件，build 流程带插件）。

## 数据影响与恢复

- ik 只对新索引生效，**旧索引 mapping 定死必须删掉重建**（删除后 ES 检索数据丢失；PG 向量、DB chunks 不受影响）。
- 已有 READY 文档恢复方式：写一次性脚本遍历已 READY 文档，从 `document_chunks` 读 chunks 重新写入 ES（不用重传文件）。
- 新索引由 `ensure_index` 启动时自动创建（带 ik 分析器）。

## 实施清单

1. docker-compose.yml 换 medcl 镜像（或按方案 B/C 装插件）
2. 删除旧索引：`curl -X DELETE http://127.0.0.1:9200/new_rag_document_chunks`（或 `DELETE /rag_document_chunks`，确认实际索引名）
3. `docker compose up -d elasticsearch` 重建 + 重启后端
4. 写一次性重索引脚本：遍历已 READY 文档 → 读 chunks → `es_service.index_chunks` 重建 ES 数据
5. 验证：`_analyze` 接口确认 ik 分词生效；真实 QA 检索中文短语命中
