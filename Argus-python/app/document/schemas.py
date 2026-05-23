from typing import Optional
from pydantic import BaseModel, Field


class UploadInitRequest(BaseModel):
    file_name: str = Field(..., alias="fileName")
    file_ext: str = Field(default="", alias="fileExt")
    content_type: str = Field(default="", alias="contentType")
    file_size: int = Field(..., alias="fileSize")
    file_hash: str = Field(..., alias="fileHash")
    chunk_size: int = Field(..., alias="chunkSize")
    chunk_count: int = Field(..., alias="chunkCount")

    model_config = {"populate_by_name": True}


class UploadInitResponse(BaseModel):
    upload_id: str
    chunk_size: int


class UploadChunkResult(BaseModel):
    uploaded_chunks: int
    status: str


class UploadCompleteResponse(BaseModel):
    document_id: int
    file_name: str


class DocumentListItemResponse(BaseModel):
    id: int
    file_name: str
    file_ext: str
    content_type: str
    file_size: int
    status: str
    uploader_user_id: int
    processed_at: Optional[str] = None
    uploaded_at: Optional[str] = None
    created_at: Optional[str] = None


class DocumentDetailResponse(BaseModel):
    id: int
    file_name: str
    file_ext: str
    content_type: str
    file_size: int
    status: str
    preview_text: Optional[str] = None
    uploader_user_id: int
    group_id: int
    uploaded_at: Optional[str] = None
    processed_at: Optional[str] = None
    created_at: Optional[str] = None
