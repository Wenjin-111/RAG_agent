import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.engine.vector_store import PgVectorRetrievalAdapter
from app.qa.query_planning import QueryPlanningService, EvidenceLevel
from app.qa.retrieval import HybridChunkRetrievalService, RetrievedEvidenceBundle
from app.qa.citation import CitationAssembler
from app.metrics.collector import LlmUsageCollector

logger = logging.getLogger(__name__)


class QaService:
    def __init__(self):
        self._query_planning = QueryPlanningService()
        self._vector_adapter = PgVectorRetrievalAdapter(settings.database_url)

    async def ask(self, user_id: int, group_id: int, question: str) -> dict:
        start_time = time.perf_counter()

        # Query planning
        plan = await self._query_planning.plan(question)
        planned_queries = plan.get("queries", [question])
        logger.info("QA plan: strategy=%s, queries=%s", plan.get("strategy"), planned_queries)

        # Hybrid retrieval
        retrieval = HybridChunkRetrievalService(self._vector_adapter)
        bundle = await retrieval.retrieve(group_id, question, planned_queries)
        logger.info("Retrieved %d documents, level=%s", len(bundle.documents), bundle.evidence_level.value)

        # Assemble context
        citations = []
        for doc in bundle.documents:
            citations.append({"index": len(citations) + 1, "file_name": doc.source_file})

        MAX_EVIDENCE_CHARS = 3000
        evidence_text = ""
        for doc in bundle.documents:
            chunk = f"\n\n--- 证据 {doc.evidence_id} ---\n{doc.content}"
            if len(evidence_text) + len(chunk) > MAX_EVIDENCE_CHARS:
                remaining = MAX_EVIDENCE_CHARS - len(evidence_text)
                if remaining > 50:
                    evidence_text += chunk[:remaining] + "..."
                break
            evidence_text += chunk

        # LLM generation — use active model config if available
        from app.models_config.resolver import get_chat_config
        chat_cfg = await get_chat_config(user_id)
        chat_model = ChatOpenAI(
            model=chat_cfg["model_name"],
            openai_api_key=chat_cfg["api_key"],
            openai_api_base=chat_cfg["base_url"],
            temperature=settings.chat.temperature,
            max_tokens=2048,
        )

        system_msg = """你是一个知识库智能助手，必须严格基于下方提供的证据内容回答问题。证据中的每条信息都是真实可靠的，直接引用证据中的具体内容来回答，不要自己编造或说"资料中没有"。不要在答案中写"证据E1"之类的编号。如果没有提供任何证据或证据等级为NONE，才可以说找不到相关信息。

用以下格式输出：
<<<ANSWER>>>
你的回答内容
<<<END>>>
<<<THINKING>>>
推理过程
<<<END>>>
<<<CITATIONS>>>
1,2
<<<END>>>"""

        user_msg = f"""证据等级：{bundle.evidence_level.value}
证据指导：{bundle.evidence_guidance}

证据内容：
{evidence_text}

问题：{question}

请基于证据回答问题。如果证据不足，请说明。"""

        response = await chat_model.ainvoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=user_msg),
        ])

        # Parse delimiter-based response format
        raw = response.content.strip()
        logger.info("QA raw LLM response (first 200 chars): %s", raw[:200])
        answer, thinking, citation_nums = _parse_delimited_response(raw)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # Build citations with actual snippets from retrieved evidence
        formatted_citations = []
        for i in citation_nums:
            idx = i - 1 if 0 <= i - 1 < len(bundle.documents) else -1
            if 0 <= idx < len(bundle.documents):
                doc = bundle.documents[idx]
                snippet = doc.content[:150] if len(doc.content) > 150 else doc.content
                formatted_citations.append({
                    "documentId": None, "chunkId": None, "chunkIndex": doc.chunk_ids[0] if doc.chunk_ids else None,
                    "fileName": doc.source_file, "score": doc.rrf_score, "snippet": snippet.strip(),
                })

        if not answer or bundle.evidence_level == EvidenceLevel.NONE:
            await self._record_usage(user_id, group_id, "qa", "/api/qa/ask", 0, 0, True)
            return {
                "answered": False,
                "answer": None,
                "reasonCode": "NO_EVIDENCE" if bundle.evidence_level == EvidenceLevel.NONE else "LOW_CONFIDENCE",
                "reasonMessage": "未检索到相关文档" if bundle.evidence_level == EvidenceLevel.NONE else "证据不足",
                "citations": [],
            }

        await self._record_usage(user_id, group_id, "qa", "/api/qa/ask",
            len(evidence_text) // 4, len(answer) // 4, True)
        return {
            "answered": True,
            "answer": answer,
            "reasonCode": None,
            "reasonMessage": None,
            "citations": formatted_citations,
        }

    async def _record_usage(self, user_id: int, group_id: int, module: str,
                            endpoint: str, prompt_tokens: int, completion_tokens: int,
                            success: bool):
        from app.dependencies import async_session_factory
        try:
            async with async_session_factory() as session:
                collector = LlmUsageCollector(session)
                await collector.record(
                    user_id=user_id, group_id=group_id, module=module,
                    endpoint=endpoint, prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    success=success, is_estimated=True,
                    model_name=settings.chat.model_name,
                )
                await session.commit()
        except Exception:
            pass  # metrics failure should never break QA

    async def ask_stream(self, user_id: int, group_id: int,
                         question: str) -> AsyncIterator[dict]:
        start_time = time.perf_counter()

        # Query planning
        plan = await self._query_planning.plan(question)
        planned_queries = plan.get("queries", [question])

        # Hybrid retrieval
        retrieval = HybridChunkRetrievalService(self._vector_adapter)
        bundle = await retrieval.retrieve(group_id, question, planned_queries)

        # Assemble citations with snippets (only if evidence found)
        citations = []
        if bundle.evidence_level != EvidenceLevel.NONE:
            for doc in bundle.documents:
                snippet = doc.content[:150] if len(doc.content) > 150 else doc.content
                citations.append({
                    "index": len(citations) + 1,
                    "file_name": doc.source_file,
                    "snippet": snippet.strip(),
                    "chunkIndex": doc.chunk_ids[0] if doc.chunk_ids else None,
                    "score": doc.rrf_score,
                })

        # Limit total evidence text to avoid overflowing model context window
        MAX_EVIDENCE_CHARS = 3000
        evidence_text = ""
        for doc in bundle.documents:
            chunk = f"\n\n--- 证据 {doc.evidence_id} ---\n{doc.content}"
            if len(evidence_text) + len(chunk) > MAX_EVIDENCE_CHARS:
                remaining = MAX_EVIDENCE_CHARS - len(evidence_text)
                if remaining > 50:
                    evidence_text += chunk[:remaining] + "..."
                break
            evidence_text += chunk

        # LLM generation with streaming — use active model config if available
        from app.models_config.resolver import get_chat_config
        chat_cfg = await get_chat_config(user_id)
        chat_model = ChatOpenAI(
            model=chat_cfg["model_name"],
            openai_api_key=chat_cfg["api_key"],
            openai_api_base=chat_cfg["base_url"],
            temperature=settings.chat.temperature,
            streaming=True,
            max_tokens=2048,
        )

        system_msg = """你是一个知识库智能助手，必须严格基于下方提供的证据内容回答问题。证据中的每条信息都是真实可靠的，直接引用证据中的具体内容来回答，不要自己编造或说"资料中没有"。不要在答案中写"证据E1"之类的编号。如果没有提供任何证据或证据等级为NONE，才可以说找不到相关信息。

用以下格式输出（严格按照标记，不要遗漏）：
<<<ANSWER>>>
你的回答内容
<<<END>>>
<<<THINKING>>>
推理过程
<<<END>>>
<<<CITATIONS>>>
1,2
<<<END>>>"""

        user_msg = f"""证据等级：{bundle.evidence_level.value}
证据内容：
{evidence_text}

问题：{question}"""

        full_content = ""
        try:
            async for chunk in chat_model.astream([
                SystemMessage(content=system_msg),
                HumanMessage(content=user_msg),
            ]):
                if chunk.content:
                    full_content += chunk.content
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
            return

        # Parse delimiter-based response format
        logger.info("QA stream full_content (first 300 chars): %s", full_content[:300])
        answer_text, thinking_text, _ = _parse_delimited_response(full_content.strip())
        logger.info("QA stream parsed answer (first 200 chars): %s", answer_text[:200])

        if answer_text:
            yield {"event": "answer", "data": json.dumps({"text": answer_text})}
        # Record usage
        await self._record_usage(user_id, group_id, "qa", "/api/qa/stream-ask",
            len(evidence_text) // 4, len(answer_text) // 4, True)
        yield {"event": "citations",
               "data": json.dumps({
                   "citations": [{
                       "documentId": None,
                       "chunkId": None,
                       "chunkIndex": c.get("chunkIndex"),
                       "fileName": c["file_name"],
                       "score": c.get("score", 1.0),
                       "snippet": c.get("snippet"),
                   } for c in citations],
                   "thinking": thinking_text,
               })}

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        yield {"event": "done", "data": json.dumps({"elapsed_ms": elapsed_ms})}


def _parse_delimited_response(text: str) -> tuple:
    """Parse LLM response with <<<TAG>>>...<<<END>>> delimiters.
    Returns (answer, thinking, citation_numbers)."""
    import re

    def _extract(tag: str) -> str:
        pattern = rf"<<<{tag}>>>\s*(.*?)\s*<<<END>>>"
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else ""

    answer = _extract("ANSWER")
    thinking = _extract("THINKING")
    citations_raw = _extract("CITATIONS")

    citation_nums = []
    for part in re.split(r"[,\s]+", citations_raw):
        part = part.strip()
        if part.isdigit():
            citation_nums.append(int(part))

    if not answer:
        # Fallback: if no delimiters found, try old JSON format
        try:
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[-1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
            clean = clean.removeprefix("json").strip().strip("`").strip()
            parsed = json.loads(clean)
            answer = parsed.get("answer", "") or ""
            thinking = parsed.get("thinking", "")
            citation_nums = parsed.get("citations", [])
        except Exception:
            answer = text  # raw fallback

    return answer, thinking, citation_nums
