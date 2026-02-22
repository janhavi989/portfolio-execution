"""
Seed the database with a demo user on first startup.
Password: demo123
"""
import asyncio
import uuid
from sqlalchemy import select
from app.database import AsyncSessionLocal, init_db
from app.models.user import User
from app.services.auth_service import hash_password
import structlog

logger = structlog.get_logger()


async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.username == "demo"))
        if existing.scalar_one_or_none():
            logger.info("seed.skip", reason="demo user already exists")
            return

        user = User(
            id=str(uuid.uuid4()),
            username="demo",
            email="demo@kalpi.com",
            hashed_password=hash_password("demo123"),
            is_active=True,
        )
        db.add(user)
        await db.commit()
        logger.info("seed.created", username="demo", password="demo123")


if __name__ == "__main__":
    asyncio.run(seed())


