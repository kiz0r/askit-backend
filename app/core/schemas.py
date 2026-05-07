"""Core schemas for error responses used across the API."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    error_code: str = Field(alias="errorCode")
    message: str

    model_config = {"populate_by_name": True}
