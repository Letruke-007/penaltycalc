"""
Batch processing schemas for validation.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID


class BatchCreateRequest(BaseModel):
    """Request schema for creating a batch processing job."""

    file_count: int = Field(..., gt=0, description="Number of files to process")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    description: Optional[str] = Field(None, description="Batch description")

    class Config:
        json_schema_extra = {
            "example": {
                "file_count": 10,
                "user_id": "user123",
                "description": "Monthly statements batch",
            }
        }


class BatchItemResponse(BaseModel):
    """Response schema for individual item in a batch."""

    item_id: str = Field(..., description="Item identifier")
    filename: str = Field(..., description="Original filename")
    status: str = Field(..., description="Processing status: pending, processing, completed, failed")
    xlsx_url: Optional[str] = Field(None, description="URL to download result")
    error: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        json_schema_extra = {
            "example": {
                "item_id": "item-001",
                "filename": "statement_jan.pdf",
                "status": "completed",
                "xlsx_url": "/api/download/item-001",
            }
        }


class BatchStatusResponse(BaseModel):
    """Response schema for batch status."""

    batch_id: UUID = Field(..., description="Batch identifier")
    status: str = Field(..., description="Batch status: pending, processing, completed, failed")
    total_count: int = Field(..., description="Total number of files")
    processed_count: int = Field(default=0, description="Successfully processed files")
    failed_count: int = Field(default=0, description="Failed files")
    created_at: datetime = Field(..., description="Batch creation time")
    updated_at: datetime = Field(..., description="Last update time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    items: Optional[List[BatchItemResponse]] = Field(None, description="Batch items details")

    class Config:
        json_schema_extra = {
            "example": {
                "batch_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "processing",
                "total_count": 10,
                "processed_count": 7,
                "failed_count": 1,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:15:00Z",
            }
        }
