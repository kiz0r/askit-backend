from typing import NewType
from uuid import UUID

# Branded types for Quiz-related IDs - provide compile-time type safety.
# Based on UUID so FastAPI/Pydantic validate them at the API boundary
# (a malformed id yields 422 rather than a 500 from a later UUID() call).
QuizId = NewType("QuizId", UUID)
QuestionId = NewType("QuestionId", UUID)
AnswerId = NewType("AnswerId", UUID)
