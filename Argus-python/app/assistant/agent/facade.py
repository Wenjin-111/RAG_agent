import json
import logging
import re
from typing import AsyncIterator, Optional

from langchain_core.messages import HumanMessage

from app.assistant.agent.factory import AssistantAgentFactory, ResultHolder

logger = logging.getLogger(__name__)

factory = AssistantAgentFactory()

TOOL_ARGS_MAX = 200
TOOL_RESULT_MAX = 500


def _truncate(obj, limit: int) -> str:
    if isinstance(obj, str):
        s = obj
    elif hasattr(obj, "content"):
        s = str(obj.content)  # ToolMessage 等取 content
    else:
        try:
            s = json.dumps(obj, ensure_ascii=False, default=str)
        except TypeError:
            s = str(obj)
    return s[:limit] + ("..." if len(s) > limit else "")


def _agent_config(thread_id: str, group_id: Optional[int], result_holder: ResultHolder,
                  user_id: int, user_code: str, system_role: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
            "group_id": group_id,
            "result_holder": result_holder,
            "user_id": user_id,
            "user_code": user_code,
            "system_role": system_role,
        }
    }


async def chat_sync(
    instruction: str, user_message: str, tool_mode: str,
    group_id: Optional[int], thread_id: str, user_id: int = 1,
    system_role: str = "USER", user_code: str = "",
) -> dict:
    result_holder = ResultHolder()
    chat_model = await factory._get_chat_model(user_id)
    agent, tools = factory.create_agent(chat_model, instruction, tool_mode, group_id, result_holder)

    config = _agent_config(thread_id, group_id, result_holder, user_id, user_code, system_role)

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_message)]},
        config=config,
    )

    reply = ""
    for msg in result.get("messages", []):
        if hasattr(msg, "type") and msg.type == "ai":
            reply = msg.content or ""

    return {
        "reply": reply or result_holder.reply,
        "citations": result_holder.current_citations,
        "thinking": result_holder.thinking,
        "tool_calls": result_holder.tool_calls,
    }


async def chat_stream(
    instruction: str, user_message: str, tool_mode: str,
    group_id: Optional[int], thread_id: str, user_id: int = 1,
    system_role: str = "USER", user_code: str = "",
    resume: Optional[str] = None,
) -> AsyncIterator[dict]:
    """Yield structured events: {event: delta|tool_start|tool_end|confirmation|done, ...}.

    - resume=None：新提问；写工具 interrupt 暂停时发 confirmation 事件
    - resume="confirm"/"cancel"：恢复被暂停的图（Command(resume=...)）
    """
    result_holder = ResultHolder()
    chat_model = await factory._get_chat_model(user_id)
    agent, tools = factory.create_agent(chat_model, instruction, tool_mode, group_id, result_holder)

    config = _agent_config(thread_id, group_id, result_holder, user_id, user_code, system_role)

    from langgraph.types import Command
    if resume is not None:
        # 多中断恢复：langgraph 要求按 interrupt id 指定 resume 值
        # （格式 {interrupt_id: value}，interrupt_id 是 xxh3_128 hex digest）
        resume_map: dict = {}
        try:
            state = await agent.aget_state(config)
            interrupts = []
            for task in (state.tasks or []):
                interrupts.extend(task.interrupts or [])
            if interrupts:
                resume_map = {i.id: resume for i in interrupts}
        except Exception:
            pass
        graph_input = Command(resume=resume_map if resume_map else resume)
    else:
        graph_input = {"messages": [HumanMessage(content=user_message)]}

    full_reply = ""
    try:
        async for event in agent.astream_events(
            graph_input,
            config=config,
            version="v2",
        ):
            kind = event.get("event", "")
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and chunk.content:
                    delta = chunk.content
                    # Dedup prefix
                    if delta.startswith(full_reply):
                        delta = delta[len(full_reply):]
                    if delta:
                        full_reply += delta
                        yield {"event": "delta", "data": delta}
            elif kind == "on_tool_start":
                tool_name = event.get("name", "")
                tool_input = event.get("data", {}).get("input") or {}
                call_id = event.get("run_id", f"tool_{len(result_holder.tool_calls)}")
                yield {"event": "tool_start", "data": {
                    "id": call_id,
                    "name": tool_name,
                    "args": _truncate(tool_input, TOOL_ARGS_MAX),
                }}
            elif kind == "on_tool_end":
                tool_name = event.get("name", "")
                tool_output = event.get("data", {}).get("output", "")
                call_id = event.get("run_id", f"tool_{len(result_holder.tool_calls)}")
                status = "success"
                if isinstance(tool_output, str) and '"ok": false' in tool_output:
                    status = "failed"
                result_holder.tool_calls.append({
                    "id": call_id,
                    "name": tool_name,
                    "args": _truncate(event.get("data", {}).get("input") or {}, TOOL_ARGS_MAX),
                    "result": _truncate(tool_output, TOOL_RESULT_MAX),
                    "status": status,
                })
                yield {"event": "tool_end", "data": {
                    "id": call_id,
                    "name": tool_name,
                    "result": _truncate(tool_output, TOOL_RESULT_MAX),
                    "status": status,
                }}
                if tool_name == "knowledge_base_search" and tool_output:
                    try:
                        clean = re.sub(r"```(?:json)?\s*", "", str(tool_output)).strip("`").strip()
                        parsed = json.loads(clean) if isinstance(tool_output, str) else tool_output
                        if parsed.get("citations"):
                            result_holder.current_citations = parsed["citations"]
                            result_holder.has_completed_search = True
                    except Exception:
                        pass
            elif kind == "on_tool_error":
                # interrupt() 抛 GraphInterrupt 是正常的 human-in-the-loop 暂停，
                # 不是失败——跳过，稍后由 confirmation 事件驱动确认卡片
                from langgraph.errors import GraphInterrupt
                err = event.get("data", {}).get("error")
                if isinstance(err, GraphInterrupt):
                    continue
                # 真实工具异常：补发失败事件，否则前端工具卡片永远停在"执行中"
                tool_name = event.get("name", "")
                call_id = event.get("run_id", f"tool_{len(result_holder.tool_calls)}")
                error = str(err or "工具执行异常")[:TOOL_RESULT_MAX]
                result_holder.tool_calls.append({
                    "id": call_id,
                    "name": tool_name,
                    "args": _truncate(event.get("data", {}).get("input") or {}, TOOL_ARGS_MAX),
                    "result": error,
                    "status": "failed",
                })
                yield {"event": "tool_end", "data": {
                    "id": call_id,
                    "name": tool_name,
                    "result": error,
                    "status": "failed",
                }}
    except Exception as e:
        logger.error("Agent stream error: %s", e)

    # 首次请求：检测写工具是否被 interrupt 暂停（图进入 human-in-the-loop）。
    # langgraph 1.2 中断信息在 state.tasks[].interrupts（不在 state.values）
    if resume is None:
        try:
            state = await agent.aget_state(config)
            interrupts = []
            for task in (state.tasks or []):
                interrupts.extend(task.interrupts or [])
            if interrupts:
                values = [i.value for i in interrupts]
                first = values[0] if isinstance(values[0], dict) else {}
                # 多中断合并为一张确认卡片（同一操作合并目标列表）
                merged = {
                    **first,
                    "target": "、".join(
                        v.get("target", "") for v in values if isinstance(v, dict)
                    ),
                    "count": len(values),
                }
                logger.info("Agent interrupted for confirmation: %s", merged)
                yield {"event": "confirmation", "data": merged}
        except Exception as e:
            logger.warning("Interrupt detection failed: %s", e)

    result_holder.reply = full_reply
    yield {"event": "done", "data": {"tool_calls": result_holder.tool_calls}}
