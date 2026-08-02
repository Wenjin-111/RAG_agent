"""MinerU 云端文档解析器（https://mineru.net）

调用流程（单文件）：
    ① POST /api/v4/file-urls/batch        申请签名上传链接
    ② PUT  签名 URL                        直传文件字节流
    ③ GET  /api/v4/extract-results/batch/{batch_id}   轮询解析结果
    ④ 下载 full_zip_url 并解压             读取 full.md（Markdown 主结果）

支持 PDF / Word / PPT / Excel / 图片；扫描件 OCR、复杂表格与公式由云端模型处理。

配置来源：管理员在系统设置 → 添加模型中维护（model_configs 表 model_type="mineru"：
api_key=token, model_name=vlm|pipeline, base_url=mineru.net），未配置时回退 .env。
"""
import asyncio
import io
import logging
import time
import zipfile

import httpx

from app.config import settings
from app.ingestion.parsers.base import DocumentParser

logger = logging.getLogger(__name__)

API_UPLOAD_BATCH = "/api/v4/file-urls/batch"
API_RESULTS_BATCH = "/api/v4/extract-results/batch/{batch_id}"


class MineruParser(DocumentParser):
    async def parse(self, data: bytes, file_name: str) -> list:
        from langchain_core.documents import Document
        from app.models_config.resolver import get_mineru_config

        cfg = await get_mineru_config(1)
        token = (cfg.get("api_key") or "").strip()
        model = (cfg.get("model_name") or "").strip() or "vlm"
        base = (cfg.get("base_url") or settings.mineru.base_url).rstrip("/")
        if not token:
            raise RuntimeError("MinerU 未配置：请在系统设置 → 添加模型中填写 MinerU Token")
        if len(data) > settings.mineru.max_file_size:
            raise RuntimeError(f"文件超过 MinerU 200MB 限制: {file_name}")

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

        # ① 申请签名上传链接
        batch_id, upload_url = await self._submit_batch(base, headers, file_name, model)
        # ② 直传文件
        await self._upload_file(upload_url, data, file_name)
        # ③ 轮询解析结果
        full_zip_url = await self._poll_results(base, headers, batch_id, file_name)
        # ④ 下载并解压，读取 full.md
        markdown = await self._download_markdown(full_zip_url)

        if not markdown or not markdown.strip():
            logger.warning("MinerU produced empty text: %s", file_name)
            return []

        return [Document(
            page_content=markdown.strip(),
            metadata={"source": file_name, "parser": "mineru", "model": model},
        )]

    async def _submit_batch(self, base: str, headers: dict, file_name: str,
                            model: str) -> tuple[str, str]:
        payload = {"files": [{"name": file_name}], "model_version": model}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(base + API_UPLOAD_BATCH, headers=headers, json=payload)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"MinerU 申请上传链接失败: {data.get('msg')} "
                               f"(trace_id: {data.get('trace_id')})")
        urls = data["data"]["file_urls"]
        if not urls:
            raise RuntimeError("MinerU 未返回上传链接")
        return data["data"]["batch_id"], urls[0]

    async def _upload_file(self, url: str, data: bytes, file_name: str) -> None:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.put(url, content=data)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"{file_name} 上传失败 HTTP {resp.status_code}: {resp.text[:300]}")

    async def _poll_results(self, base: str, headers: dict, batch_id: str,
                            file_name: str) -> str:
        url = base + API_RESULTS_BATCH.format(batch_id=batch_id)
        start = time.time()
        while time.time() - start < settings.mineru.poll_timeout:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=headers)
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"MinerU 查询结果失败: {data.get('msg')}")

            results = data["data"]["extract_result"]
            pending = 0
            for item in results:
                state = item["state"]
                if state == "done":
                    return item["full_zip_url"]
                if state == "failed":
                    raise RuntimeError(f"{file_name} 解析失败: {item.get('err_msg')}")
                pending += 1
            if not pending:
                raise RuntimeError(f"MinerU 返回空结果: {file_name}")
            await asyncio.sleep(settings.mineru.poll_interval)
        raise RuntimeError(f"MinerU 轮询超时 ({settings.mineru.poll_timeout}s): {file_name}")

    async def _download_markdown(self, full_zip_url: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(full_zip_url)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            try:
                with z.open("full.md") as f:
                    return f.read().decode("utf-8")
            except KeyError:
                return ""
