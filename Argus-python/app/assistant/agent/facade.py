import logging
from typing import AsyncIterator, Optional

from langchain_core.messages import HumanMessage

from app.assistant.agent.factory import AssistantAgentFactory, ResultHolder

logger = logging.getLogger(__name__)

factory = AssistantAgentFactory()


async def chat_sync(
    instruction: str, user_message: str, tool_mode: str,
    group_id: Optional[int], thread_id: str, user_id: int = 1,
) -> dict:
    result_holder = ResultHolder()
    chat_model = await factory._get_chat_model(user_id)
    agent, tools = factory.create_agent(chat_model, instruction, tool_mode, group_id, result_holder)

    config = {
        "configurable": {
            "thread_id": thread_id,
            "group_id": group_id,
            "result_holder": result_holder,
        }
    }

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
    }


async def chat_stream(
    instruction: str, user_message: str, tool_mode: str,
    group_id: Optional[int], thread_id: str, user_id: int = 1,
) -> AsyncIterator[str]:
    result_holder = ResultHolder()
    chat_model = await factory._get_chat_model(user_id)
    agent, tools = factory.create_agent(chat_model, instruction, tool_mode, group_id, result_holder)

    config = {
        "configurable": {
            "thread_id": thread_id,
            "group_id": group_id,
            "result_holder": result_holder,
        }
    }

    full_reply = ""
    try:
        async for event in agent.astream_events(
            {"messages": [HumanMessage(content=user_message)]},
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
                        yield delta
            elif kind == "on_tool_end":
                tool_name = event.get("name", "")
                tool_output = event.get("data", {}).get("output", "")
                if tool_name == "knowledge_base_search" and tool_output:
                    try:
                        import json
                        import re
                        clean = re.sub(r"```(?:json)?\s*", "", str(tool_output)).strip("`").strip()
                        parsed = json.loads(clean) if isinstance(tool_output, str) else tool_output
                        if parsed.get("citations"):
                            result_holder.current_citations = parsed["citations"]
                            result_holder.has_completed_search = True
                    except Exception:
                        pass
    except Exception as e:
        logger.error("Agent stream error: %s", e)

    result_holder.reply = full_reply
