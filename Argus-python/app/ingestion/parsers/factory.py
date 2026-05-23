from app.ingestion.parsers.base import DocumentParser
from app.ingestion.parsers.pdf_parser import PdfParser
from app.ingestion.parsers.docx_parser import DocxParser
from app.ingestion.parsers.txt_parser import TxtParser
from app.ingestion.parsers.md_parser import MdParser


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


DocumentParserFactory.register("pdf", PdfParser())
DocumentParserFactory.register("docx", DocxParser())
DocumentParserFactory.register("doc", DocxParser())
DocumentParserFactory.register("txt", TxtParser())
DocumentParserFactory.register("md", MdParser())
