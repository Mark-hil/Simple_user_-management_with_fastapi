from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import get_db
from models import User
from pydantic import BaseModel
from typing import List, Optional
import redis
import json
# from cors import configure_cors

app = FastAPI()


# Redis connection using redis-py
REDIS_URL = "redis://localhost:6379"
redis_client = redis.asyncio.from_url(REDIS_URL)
# ------------------- Static Users -------------------
static_users = {
    1: {"name": "mark", "email": "mark@example.com", "age": 25},
    2: {"name": "kofi", "email": "kofi@example.com", "age": 30},
    3: {"name": "ama", "email": "ama@example.com", "age": 22},
    4: {"name": "kwame", "email": "kwame@example.com", "age": 28},
    5: {"name": "esi", "email": "esi@example.com", "age": 26},
}

# Pydantic Models
class UserCreate(BaseModel):
    name: str
    email: str
    age: Optional[int] = None

class UserResponse(UserCreate):
    id: int
    class Config:
        orm_mode = True

# ----------- Static User Endpoints -----------
@app.get("/static-users/", response_model=List[UserResponse])
def get_static_users():
    return [{"id": user_id, **user} for user_id, user in static_users.items()]

@app.get("/static-users/{user_id}", response_model=UserResponse)
def get_static_user(user_id: int):
    user = static_users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user_id, **user}

# ----------- Dynamic User Endpoints (PostgreSQL) -----------
@app.post("/dynamic-users/", response_model=UserResponse)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    new_user = User(name=user.name, email=user.email, age=user.age)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Clear Redis cache to force fetching fresh data
    await redis_client.delete("all_users")

    return new_user

# Get all users
# ------------------- Get Users with Redis Caching -------------------
@app.get("/dynamic-users/", response_model=dict)
async def get_users(db: AsyncSession = Depends(get_db)):
    cache_key = "all_users"
    
    # Check if data exists in Redis
    cached_users = await redis_client.get(cache_key)
    if cached_users:
        # Deserialize from JSON to Python list of users
        users = json.loads(cached_users)
        return {"message": "Data from Redis Cache", "users": users}

    # Fetch from database if not in cache
    result = await db.execute(select(User))
    users = result.scalars().all()

    # Convert list of users to JSON
    user_data = [
        UserResponse(id=user.id, name=user.name, email=user.email, age=user.age).dict()
        for user in users
    ]
    user_data_json = json.dumps(user_data)  # Serialize list to JSON string

    # Cache in Redis for 10 minutes
    await redis_client.setex(cache_key,600, user_data_json)  # 600 seconds = 10 minutes

    return {"message": "Data from PostgreSQL", "users": user_data}

# Get a single user by ID
@app.get("/dynamic-users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"user:{user_id}"  # Redis key

    # Check Redis Cache
    cached_user = await redis.get(cache_key)
    if cached_user:
        return UserResponse.parse_raw(cached_user)  # Deserialize JSON

    # Fetch from DB if not in Redis
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Cache user data in Redis for 10 minutes
    user_data = UserResponse(id=user.id, name=user.name, email=user.email, age=user.age).json()
    await redis.setex(cache_key, 600, user_data)  # 600 sec = 10 min

    return UserResponse(id=user.id, name=user.name, email=user.email, age=user.age)

@app.put("/dynamic-users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).filter(User.id == user_id))
    existing_user = result.scalar_one_or_none()
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_user.name = user.name
    existing_user.email = user.email
    existing_user.age = user.age
    await db.commit()
    await db.refresh(existing_user)
    return existing_user

# ------------------- Delete User with Redis Cache -------------------
@app.delete("/dynamic-users/{user_id}", status_code=200)
async def delete_dynamic_user(user_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = "all_users"
    
    # Check if user exists in database
    result = await db.execute(select(User).filter(User.id == user_id))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete user from the database
    await db.delete(db_user)
    await db.commit()

    # Fetch the updated list of users from the database after deletion
    result = await db.execute(select(User))
    users = result.scalars().all()

    # Convert list of users to JSON
    user_data = [
        UserResponse(id=u.id, name=u.name, email=u.email, age=u.age).dict()
        for u in users
    ]
    user_data_json = json.dumps(user_data)  # Serialize list to JSON string

    # Update Redis cache with the new list after deletion
    await redis_client.setex(cache_key, 600, user_data_json)  # 600 seconds = 10 minutes

    return {"message": "User deleted successfully and cache refreshed"}
