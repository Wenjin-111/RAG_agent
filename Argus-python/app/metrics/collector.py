import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.metrics.models import LlmUsageRecord

logger = logging.getLogger(__name__)

# Pricing per 1K tokens (CNY)
PRICING = {
    "qwen-plus": {"input": 0.0008, "output": 0.002},
    "qwen-turbo": {"input": 0.0003, "output": 0.0006},
    "qwen-max": {"input": 0.02, "output": 0.06},
}


class LlmUsageCollector:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        user_id: int,
        module: str,
        endpoint: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: int = 0,
        success: bool = True,
        model_name: Optional[str] = None,
        group_id: Optional[int] = None,
        session_id: Optional[str] = None,
        error_message: Optional[str] = None,
        is_estimated: bool = False,
    ) -> None:
        cost = self._calculate_cost(model_name or "", prompt_tokens, completion_tokens)

        record = LlmUsageRecord(
            user_id=user_id,
            group_id=group_id,
            module=module,
            endpoint=endpoint,
            session_id=session_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            is_estimated=is_estimated,
            cost_amount=Decimal(str(cost)),
            cost_currency="CNY",
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            model_name=model_name,
        )
        self.session.add(record)
        await self.session.flush()

    @staticmethod
    def _calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = PRICING.get(model_name, {"input": 0.0008, "output": 0.002})
        input_cost = prompt_tokens / 1000 * pricing["input"]
        output_cost = completion_tokens / 1000 * pricing["output"]
        return round(input_cost + output_cost, 6)
