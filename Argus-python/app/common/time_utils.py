import datetime as dt


def utcnow() -> dt.datetime:
    """Return the current UTC time as a naive datetime. Compatible with
    TIMESTAMP WITHOUT TIME ZONE columns in PostgreSQL."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
