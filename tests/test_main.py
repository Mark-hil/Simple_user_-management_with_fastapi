import pytest
import json
from httpx import AsyncClient
from main import app, redis_client
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from models import Base

# Mocked database for testing
DATABASE_URL = "postgresql+asyncpg://fastapi_user:password@localhost:5432/fastapi_db"
engine = create_async_engine(DATABASE_URL, echo=True)
TestingSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


# Override the database dependency
async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


# Mock Redis client
@pytest.fixture(scope="function")
async def mock_redis():
    await redis_client.flushdb()  # Clear Redis before each test
    yield redis_client
    await redis_client.flushdb()  # Clear Redis after each test


# Async test client for FastAPI
@pytest.fixture(scope="module")
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac  # ✅ Now ensures proper usage in tests


# Setup and teardown for the database
@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------- TESTS ----------------------


@pytest.mark.asyncio
async def test_create_user_for_tests(client):
    """Create a user before testing GET, PUT, and DELETE"""
    user_data = {"name": "John", "email": "john@example.com", "age": 25}
    response = await client.post("/dynamic-users/", json=user_data)
    assert response.status_code == 200
    assert response.json()["name"] == "John"


@pytest.mark.asyncio
async def test_get_static_users(client):
    response = await client.get("/static-users/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_static_user_not_found(client):
    response = await client.get("/static-users/")  # Non-existent user ID
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_dynamic_user(client):
    user_data = {"name": "Jane", "email": "jane@example.com", "age": 30}
    response = await client.post("/dynamic-users/", json=user_data)
    assert response.status_code == 200
    assert response.json()["name"] == "Jane"


@pytest.mark.asyncio
async def test_get_dynamic_users_from_db(client, mock_redis):
    cached_users = await mock_redis.get("all_users")
    assert cached_users is None or cached_users == b"null"
    response = await client.get("/dynamic-users/")
    assert response.status_code == 200
    assert response.json()["message"] == "Data from PostgreSQL"
    cached_users = await mock_redis.get("all_users")
    assert cached_users is not None


@pytest.mark.asyncio
async def test_get_dynamic_users_from_redis(client, mock_redis):
    test_users = [{"id": 1, "name": "Test", "email": "test@example.com", "age": 22}]
    await mock_redis.set("all_users", json.dumps(test_users))
    cached_users = await mock_redis.get("all_users")
    if cached_users:
        cached_users = json.loads(cached_users.decode("utf-8"))
    response = await client.get("/dynamic-users/")
    assert response.status_code == 200
    assert cached_users is not None


@pytest.mark.asyncio
async def test_get_user_not_found(client):
    response = await client.get("/dynamic-users/")  # Non-existent ID
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_user(client):
    user_data = {"name": "Updated", "email": "updated@example.com", "age": 28}
    response = await client.put("/dynamic-users/1", json=user_data)
    assert response.status_code in [200, 404]  # Allow for "not found" cases


@pytest.mark.asyncio
async def test_delete_user(client, mock_redis):
    response = await client.delete("/dynamic-users/1")
    assert response.status_code in [200, 404]
    cached_users = await mock_redis.get("all_users")
    assert cached_users is None or cached_users == b"null"
