from typing import NewType
from uuid import UUID

# Branded type for User IDs - provides compile-time type safety.
# Based on UUID so it validates at the API boundary and needs no manual
# str <-> UUID conversion inside the services.
UserId = NewType("UserId", UUID)
