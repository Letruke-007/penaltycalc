"""
Common schemas used across the application.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    code: Optional[str] = Field(None, description="Error code for client handling")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Processing failed",
                "detail": "Invalid PDF format",
                "code": "INVALID_PDF",
            }
        }


class SuccessResponse(BaseModel):
    """Standard success response format."""

    message: str = Field(..., description="Success message")
    data: Optional[Any] = Field(None, description="Response data")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "File processed successfully",
                "data": {"file_id": "123e4567-e89b-12d3-a456-426614174000"},
            }
        }
