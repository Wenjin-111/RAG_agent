import re
from langchain_core.documents import Document

CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
CODE_FENCE_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)


class TextCleanupTransformer:
    """Removes control characters while preserving code blocks and normalizes whitespace."""

    def transform(self, documents: list[Document]) -> list[Document]:
        cleaned = []
        for doc in documents:
            text = doc.page_content
            if not text:
                continue
            # Preserve code blocks
            code_blocks = {}
            counter = [0]

            def _save(m):
                key = f"__CODE_BLOCK_{counter[0]}__"
                code_blocks[key] = m.group(0)
                counter[0] += 1
                return key

            text = CODE_FENCE_PATTERN.sub(_save, text)
            # Remove control chars
            text = CONTROL_CHAR_PATTERN.sub("", text)
            # Normalize whitespace
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            # Restore code blocks
            for key, block in code_blocks.items():
                text = text.replace(key, block)

            text = text.strip()
            if text:
                cleaned.append(Document(
                    page_content=text,
                    metadata=doc.metadata,
                ))
        return cleaned
