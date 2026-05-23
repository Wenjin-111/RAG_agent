from abc import ABC, abstractmethod
from langchain_core.documents import Document


class DocumentParser(ABC):
    @abstractmethod
    async def parse(self, data: bytes, file_name: str) -> list[Document]:
        ...
