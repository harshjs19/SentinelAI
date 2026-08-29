from sqlalchemy import text

from backend.app.db.session import engine


async def database_is_ready() -> bool:
    """Return whether the critical database dependency accepts a lightweight query."""

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
