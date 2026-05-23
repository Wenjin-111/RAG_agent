import json
import logging
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from app.engine.vector_store import PgVectorRetrievalAdapter
from app.qa.retrieval import HybridChunkRetrievalService
from app.config import settings

logger = logging.getLogger(__name__)


@tool
async def knowledge_base_search(query: str, config: RunnableConfig = None) -> str:
    """Search the knowledge base for documents matching the query. Use this when you need to find information from uploaded documents."""

    cfg = config.get("configurable", {}) if config else {}
    result_holder = cfg.get("result_holder")
    group_id = cfg.get("group_id")

    logger.info("KB search tool called: query=%s, group_id=%s", query[:100], group_id)

    if result_holder and getattr(result_holder, "has_completed_search", False):
        return json.dumps({
            "found": False,
            "reasonCode": "DUPLICATE_TOOL_CALL",
            "message": "本轮已经完成过一次知识库检索，请基于上一条工具返回的 evidences 直接给出最终回答。",
            "evidences": None,
            "citations": getattr(result_holder, "current_citations", []),
        }, ensure_ascii=False)

    if not group_id:
        return json.dumps({"found": False, "reasonCode": "NO_GROUP", "message": "未指定知识库群组"})

    vector_adapter = PgVectorRetrievalAdapter(settings.database_url)
    retrieval = HybridChunkRetrievalService(vector_adapter)
    bundle = await retrieval.retrieve(group_id, query, [query])

    citations = []
    evidences = []
    for doc in bundle.documents:
        citations.append({"index": len(citations) + 1, "file_name": doc.source_file})
        evidences.append({"content": doc.content})

    if result_holder:
        result_holder.has_completed_search = True
        result_holder.current_citations = citations

    return json.dumps({
        "found": True,
        "reasonCode": "SUCCESS",
        "evidences": evidences,
        "citations": citations,
    }, ensure_ascii=False)
