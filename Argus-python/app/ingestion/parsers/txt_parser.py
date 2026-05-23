from langchain_core.documents import Document
from app.ingestion.parsers.base import DocumentParser


class TxtParser(DocumentParser):
    async def parse(self, data: bytes, file_name: str) -> list[Document]:
        text = None
        for encoding in ("utf-8", "gbk", "gb2312", "latin-1"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = data.decode("utf-8", errors="replace")

        return [Document(
            page_content=text.strip(),
            metadata={"source": file_name, "char_count": len(text)}
        )]
