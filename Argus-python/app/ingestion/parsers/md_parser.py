from langchain_core.documents import Document
from app.ingestion.parsers.base import DocumentParser


class MdParser(DocumentParser):
    async def parse(self, data: bytes, file_name: str) -> list[Document]:
        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = data.decode("utf-8", errors="replace")

        return [Document(
            page_content=text.strip(),
            metadata={"source": file_name, "file_type": "markdown", "char_count": len(text)}
        )]
