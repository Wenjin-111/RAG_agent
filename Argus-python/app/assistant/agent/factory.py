import logging
from typing import Optional

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.assistant.agent.tools import knowledge_base_search, ADMIN_TOOLS

logger = logging.getLogger(__name__)


class ResultHolder:
    def __init__(self):
        self.reply = ""
        self.has_completed_search = False
        self.current_citations = []
        self.thinking = ""
        self.tool_calls = []  # [{id, name, args, result, status}]


class AssistantAgentFactory:
    RECURSION_LIMIT = 10
    RECURSION_LIMIT_ADMIN = 15

    def __init__(self):
        self.chat_model = None  # Lazily created per-request with active config
        self._memory = MemorySaver()

    async def _get_chat_model(self, user_id: int = 1) -> ChatOpenAI:
        from app.models_config.resolver import get_chat_config
        cfg = await get_chat_config(user_id)
        return ChatOpenAI(
            model=cfg["model_name"],
            openai_api_key=cfg["api_key"],
            openai_api_base=cfg["base_url"],
            temperature=settings.chat.temperature,
        )

    def create_agent(self, chat_model, instruction: str, tool_mode: str,
                     group_id: Optional[int], result_holder: ResultHolder):
        tools = []
        recursion_limit = self.RECURSION_LIMIT
        if tool_mode == "KB_SEARCH":
            tools = [knowledge_base_search]
        elif tool_mode == "ADMIN":
            tools = ADMIN_TOOLS
            recursion_limit = self.RECURSION_LIMIT_ADMIN

        agent = create_react_agent(
            model=chat_model,
            tools=tools,
            prompt=instruction,
            checkpointer=self._memory,
        )

        return agent.with_config(
            config={"recursion_limit": recursion_limit}
        ), tools
