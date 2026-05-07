"""User module type definitions."""

from typing import NewType

# Branded type for User IDs - provides compile-time type safety
UserId = NewType("UserId", str)
