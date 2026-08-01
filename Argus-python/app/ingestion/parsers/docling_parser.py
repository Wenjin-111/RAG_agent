import tempfile
import asyncio
import logging
from pathlib import Path
from langchain_core.documents import Document
from app.ingestion.parsers.base import DocumentParser

logger = logging.getLogger(__name__)


class DoclingPdfParser(DocumentParser):
    """PDF parser using Docling for table/formula-aware Markdown extraction."""

    async def parse(self, data: bytes, file_name: str) -> list[Document]:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()

        # Docling's convert() requires a Path or str (file path), not BytesIO
        suffix = Path(file_name).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        try:
            result = await asyncio.to_thread(converter.convert, tmp_path)
            markdown = result.document.export_to_markdown()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if not markdown or not markdown.strip():
            logger.warning("Docling parsing produced empty text: %s", file_name)
            return []

        return [Document(
            page_content=markdown.strip(),
            metadata={"source": file_name}
        )]
