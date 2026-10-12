# Step 1: Backend Setup (FastAPI + Async) — Complete Guide

## What We Built

This is a complete, working FastAPI backend with:
- **Async database** (SQLAlchemy + asyncpg)
- **JWT authentication** (login → token → access protected endpoints)
- **Pydantic validation** (automatic request/response validation)
- **Clean architecture** (models, routes, services separated)

## Files Overview

### **config.py**
Environment configuration. Loads from `.env` file.
- `DATABASE_URL`: Postgres connection string
- `SECRET_KEY`: For JWT signing (change in production!)
- `ANTHROPIC_API_KEY`: Claude API key

### **db_models.py**
SQLAlchemy ORM models (what rows look like in database).
- `User`: username, hashed_password, email, created_at
- `Transaction`: date, merchant, category, amount, is_credit, source_file
- `ProcessedFile`: Track which PDFs have been processed (to avoid duplicates)

### **models_pydantic.py**
Pydantic schemas for request/response validation.
- `UserCreate`: Registration request
- `UserLogin`: Login request
- `TransactionCreate`: Create transaction (from extraction)
- `StandardResponse`: Standard API response wrapper

### **auth.py**
Authentication utilities.
- `hash_password()`: Bcrypt password hashing
- `verify_password()`: Check password against hash
- `create_jwt_token()`: Generate JWT token (expires in 24h)
- `decode_jwt_token()`: Validate and decode JWT

### **database.py**
Async database connection and session management.
- `engine`: Async SQLAlchemy engine (async Postgres)
- `AsyncSessionLocal`: Async session factory
- `get_db_session()`: FastAPI dependency (inject async session into endpoints)
- `init_db()`: Create tables on startup
- `close_db()`: Close connection pool on shutdown

### **app.py**
FastAPI application with routes.

**Startup/Shutdown:**
- `startup`: Creates tables when server starts
- `shutdown`: Closes DB connection when server stops

**Auth Endpoints:**
- `POST /api/auth/register`: Register new user
  - Input: `UserCreate` (username, password, email)
  - Output: `UserResponse` (id, username, email, created_at)
- `POST /api/auth/login`: Login
  - Input: `UserLogin` (username, password)
  - Output: `AuthToken` (access_token, token_type, user_id)
- `GET /api/me`: Get current user (requires JWT token)
  - Header: `Authorization: Bearer <token>`
  - Output: `UserResponse`

**Utilities:**
- `GET /api/health`: Health check
- `GET /`: Root endpoint

## How It Works (Example: Login Flow)

```
1. Frontend sends POST /api/auth/login
   {
     "username": "yashu",
     "password": "mypassword123"
   }

2. FastAPI receives request, validates with UserLogin (Pydantic)
   - If validation fails, returns 400 error

3. app.py handler:
   - Queries User table where username == "yashu"
   - Verifies password with bcrypt
   - If invalid, returns 401

4. If valid:
   - Calls create_jwt_token({"user_id": 1, "username": "yashu"})
   - Token is signed with SECRET_KEY, expires in 24h

5. Returns to frontend:
   {
     "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
     "token_type": "bearer",
     "user_id": 1
   }

6. Frontend stores token in localStorage or httpOnly cookie

7. For protected endpoints (GET /api/me):
   - Frontend sends: Authorization: Bearer eyJ0eXAi...
   - app.py decodes token with decode_jwt_token()
   - Verifies it's still valid (not expired)
   - Loads user from database
   - Returns user data
```

## Key Async Concepts

**Why async?**
- Without async: Each request blocks the entire server
- With async: Server can handle 1000s of requests concurrently
- Database queries don't block other requests

**Example (synchonous, slow):**
```python
def get_transactions():
    result = db.query(...)  # BLOCKS everything while waiting
    return result
```

**Example (async, fast):**
```python
async def get_transactions():
    result = await db.query(...)  # Other requests can run while waiting
    return result
```

## Setup Instructions

### 1. Create `.env` file
```bash
cp .env.example .env
# Edit .env with your settings:
# - DATABASE_URL (connect to your Postgres instance)
# - SECRET_KEY (generate a random string for JWT)
# - ANTHROPIC_API_KEY (from your Claude account)
```

### 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the server
```bash
python -m uvicorn app:app --reload
# Server runs at http://localhost:8000
```

### 5. Test the API
```bash
# Register a user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"yashu","password":"test1234","email":"yashu@example.com"}'

# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"yashu","password":"test1234"}'

# Get current user (use token from login response)
curl -X GET http://localhost:8000/api/me \
  -H "Authorization: Bearer <YOUR_TOKEN_HERE>"
```

## What's Next (Phase 2)

In Phase 2, we'll add:
- **Upload endpoint** (PDF upload handling)
- **Extraction service** (call Claude API)
- **Validation service** (Pydantic validation)
- **Analytics endpoints** (trends, anomalies)
- **Transaction endpoints** (list, filter, etc.)

## Pydantic Validation Example

When you send invalid data:
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"ab","password":"short"}'
```

FastAPI automatically returns:
```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "username"],
      "msg": "String should have at least 3 characters",
      "input": "ab"
    }
  ]
}
```

No code needed — Pydantic handles it!

## Security Notes

⚠️ **Before production:**
1. Change `SECRET_KEY` in `.env` (use `openssl rand -hex 32`)
2. Use strong `DATABASE_URL` password
3. Set `DEBUG=False`
4. Enable HTTPS
5. Add rate limiting
6. Implement refresh tokens (not just 24h expiration)
