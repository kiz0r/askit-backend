from typing import NewType

# Branded types for Quiz-related IDs - provide compile-time type safety
QuizId = NewType("QuizId", str)
QuestionId = NewType("QuestionId", str)
AnswerId = NewType("AnswerId", str)
SessionId = NewType("SessionId", str)
