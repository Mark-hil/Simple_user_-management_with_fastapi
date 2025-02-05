from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
import os 

DATABASE_URL = os.getenv("DATABASE_URL")
try:
    engine = create_async_engine(DATABASE_URL, echo=True)
except Exception as Error: 
    print(Error, "conneting to db failed")

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    print("-------attemting to create db session-----")
    async with async_session() as session:
        print(session)
        print("-------db created session-----")
        yield session
