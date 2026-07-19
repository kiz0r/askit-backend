from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC datetime for TIMESTAMP WITHOUT TIME ZONE DB columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
