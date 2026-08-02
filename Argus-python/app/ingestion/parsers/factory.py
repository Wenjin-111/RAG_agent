from app.ingestion.parsers.base import DocumentParser
from app.ingestion.parsers.mineru_parser import MineruParser
from app.ingestion.parsers.txt_parser import TxtParser
from app.ingestion.parsers.md_parser import MdParser

# MinerU 云端解析覆盖 PDF / Word / PPT / Excel / 图片（扫描件、表格、公式由云端模型处理）
_MINERU_EXTS = [
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "png", "jpg", "jpeg", "webp", "bmp",
]


class DocumentParserFactory:
    _parsers: dict[str, DocumentParser] = {}

    @classmethod
    def register(cls, ext: str, parser: DocumentParser):
        cls._parsers[ext.lower()] = parser

    @classmethod
    def get(cls, file_ext: str) -> DocumentParser:
        ext = file_ext.lower().lstrip(".")
        parser = cls._parsers.get(ext)
        if parser is None:
            return cls._parsers["txt"]  # fallback
        return parser


# 纯文本格式本地解析（无需上云，节省 MinerU 额度）
DocumentParserFactory.register("txt", TxtParser())
DocumentParserFactory.register("md", MdParser())

# 复杂文档统一走 MinerU 云端解析
mineru_parser = MineruParser()
for ext in _MINERU_EXTS:
    DocumentParserFactory.register(ext, mineru_parser)
