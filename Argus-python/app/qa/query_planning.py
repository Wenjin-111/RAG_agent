import json
import logging
import re
from enum import Enum

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class QueryPlanStrategy(str, Enum):
    DIRECT = "DIRECT"
    REWRITE = "REWRITE"
    DECOMPOSE = "DECOMPOSE"


class EvidenceLevel(str, Enum):
    NONE = "NONE"
    WEAK = "WEAK"
    PARTIAL = "PARTIAL"
    SUFFICIENT = "SUFFICIENT"


class QueryPlanningService:
    MAX_QUERY_COUNT = 3

    def __init__(self):
        self.chat_model = ChatOpenAI(
            model=settings.chat.model_name,
            openai_api_key=settings.chat.api_key,
            openai_api_base=settings.chat.base_url,
            temperature=0.1,
        )

    async def _get_chat_model(self, user_id: int) -> ChatOpenAI:
        from app.models_config.resolver import get_chat_config
        try:
            cfg = await get_chat_config(user_id)
            if cfg:
                return ChatOpenAI(
                    model=cfg["model_name"],
                    openai_api_key=cfg["api_key"],
                    openai_api_base=cfg["base_url"],
                    temperature=0.1,
                )
        except Exception:
            pass
        return self.chat_model

    async def plan(self, question: str, user_id: int = 1) -> dict:
        chat_model = await self._get_chat_model(user_id)
        prompt = f"""分析以下问题，决定最佳查询策略。

策略选项：
- DIRECT: 问题可以直接检索回答
- REWRITE: 需要改写问题以提高检索效果
- DECOMPOSE: 复杂问题，需要拆分为多个子问题

输出JSON格式：
{{"strategy": "DIRECT|REWRITE|DECOMPOSE", "queries": ["query1", "query2", ...], "reasoning": "分析原因"}}

问题: {question}"""

        try:
            response = await chat_model.ainvoke([HumanMessage(content=prompt)])
            raw = response.content.strip()
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip("` ").strip()

            result = json.loads(raw)
            strategy = result.get("strategy", "DIRECT")
            queries = result.get("queries", [question])

            if not queries:
                queries = [question]

            return self._validate_plan(strategy, queries[:self.MAX_QUERY_COUNT], question)
        except Exception as e:
            logger.warning("Query planning failed, using fallback: %s", e)
            return {"strategy": QueryPlanStrategy.DIRECT.value, "queries": [question]}

    def _validate_plan(self, strategy: str, queries: list[str], original: str) -> dict:
        if strategy == QueryPlanStrategy.DIRECT.value:
            return {"strategy": strategy, "queries": [original]}
        elif strategy == QueryPlanStrategy.REWRITE.value:
            return {"strategy": strategy, "queries": [original] + queries[:self.MAX_QUERY_COUNT - 1]}
        elif strategy == QueryPlanStrategy.DECOMPOSE.value:
            return {"strategy": strategy, "queries": queries[:self.MAX_QUERY_COUNT]}
        return {"strategy": QueryPlanStrategy.DIRECT.value, "queries": [original]}
