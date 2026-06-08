from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error_code: str = Field(alias="errorCode")
    message: str

    model_config = {"populate_by_name": True}


class MessageResponse(BaseModel):
    message: str
