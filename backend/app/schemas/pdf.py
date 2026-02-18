"""
PDF-related schemas for validation.
"""

from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class PDFUploadRequest(BaseModel):
    """Request schema for PDF upload."""

    filename: str = Field(..., description="Name of the PDF file")
    file_size: int = Field(..., gt=0, description="File size in bytes")
    content_type: str = Field(default="application/pdf", description="MIME type")

    class Config:
        json_schema_extra = {
            "example": {
                "filename": "statement_2024.pdf",
                "file_size": 1024000,
                "content_type": "application/pdf",
            }
        }


class PDFProcessingResponse(BaseModel):
    """Response schema for PDF processing result."""

    file_id: str = Field(..., description="Unique file identifier")
    status: str = Field(..., description="Processing status")
    xlsx_url: Optional[str] = Field(None, description="URL to download XLSX file")
    created_at: datetime = Field(..., description="Processing start time")
    completed_at: Optional[datetime] = Field(None, description="Processing completion time")
    error: Optional[str] = Field(None, description="Error message if processing failed")

    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "completed",
                "xlsx_url": "/api/download/123e4567-e89b-12d3-a456-426614174000",
                "created_at": "2024-01-15T10:30:00Z",
                "completed_at": "2024-01-15T10:30:05Z",
            }
        }
