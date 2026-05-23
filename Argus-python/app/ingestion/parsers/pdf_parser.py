import io
import logging
from langchain_core.documents import Document
from app.ingestion.parsers.base import DocumentParser

logger = logging.getLogger(__name__)


class PdfParser(DocumentParser):
    async def parse(self, data: bytes, file_name: str) -> list[Document]:
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("pdfplumber is required for PDF parsing")

        text_parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        full_text = "\n\n".join(text_parts)
        if not full_text.strip():
            logger.warning("PDF parsing produced empty text: %s", file_name)
            return []

        return [Document(
            page_content=full_text.strip(),
            metadata={"source": file_name, "pages": len(pdf.pages) if hasattr(pdf, "pages") else 0}
        )]
