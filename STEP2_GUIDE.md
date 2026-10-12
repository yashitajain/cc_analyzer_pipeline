# Step 2: Async Processing + Redis — Complete Guide

## What We Built

A **complete async PDF processing pipeline** that:
- Accepts PDF uploads instantly (no waiting)
- Processes in background (extract → parse → validate → save)
- Notifies frontend in real-time when done
- Caches results to avoid re-processing

## Architecture

```
1. User uploads PDF
   ↓ (instant response)
   └→ Stored in Redis queue
       ↓
   2. Background worker (Celery)
       - Extract text (pdfplumber)
       - Call Claude API
       - Validate (Pydantic)
       - Save to Postgres
       ↓
   3. Notify frontend (Redis Pub/Sub)
       ↓
   4. User sees "Processing complete!"
```

## New Files

### **services/extract.py**
PDF text extraction with pdfplumber.
- `extract_text_from_pdf()`: Extract all text from PDF
- `get_pdf_hash()`: Get SHA-256 hash for deduplication

### **services/parse.py**
Claude API integration for transaction parsing.
- `parse_transactions_with_claude()`: Call Claude to extract transactions
- Returns validated `TransactionCreate` objects

### **services/validate.py**
Transaction validation and control total checks.
- `validate_transactions()`: Separate valid from invalid
- `check_control_total()`: Verify transaction sum

### **celery_tasks.py**
Background task processing.
- `process_pdf_task`: Main async task
  - Extracts text
  - Checks cache (if PDF already processed)
  - Calls Claude API
  - Validates
  - Saves to database
  - Notifies frontend
- Publishes status updates to Redis Pub/Sub

### **api/upload.py**
PDF upload endpoint.
- `POST /api/upload`: Queue PDF for processing
- `GET /api/upload/{file_id}/status`: Check processing status

### **redis_client.py**
Redis connection management.
- `init_redis()`: Connect on startup
- `close_redis()`: Disconnect on shutdown
- `get_redis()`: FastAPI dependency

## How It Works (Example)

### User uploads PDF:
```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@statement.pdf" \
  -H "Authorization: Bearer <token>"
```

### Server responds instantly:
```json
{
  "success": true,
  "data": {
    "file_id": "pdf_abc123",
    "task_id": "celery_task_xyz",
    "status": "processing",
    "message": "PDF uploaded. Processing in background."
  }
}
```

### Frontend polls for status:
```bash
# Check every 2 seconds
curl http://localhost:8000/api/upload/pdf_abc123/status
```

### Status progression:
```
1. {"status": "processing"}
2. {"status": "extracting"}
3. {"status": "parsing"}
4. {"status": "validating"}
5. {"status": "saving"}
6. {"status": "done", "transactions_count": 42}
```

### Or listen via Redis Pub/Sub (real-time):
```python
# Frontend connects to WebSocket
# Listens on: user:123:uploads
# Receives updates as they happen (no polling)
```

## Setup Instructions

### 1. Update requirements.txt

Add to your existing `requirements.txt`:
```
redis==5.0.0
aioredis==2.0.1
celery==5.3.0
pdfplumber==0.10.0
httpx==0.25.0
python-multipart==0.0.6
```

Then:
```bash
pip install -r requirements.txt
```

### 2. Update config.py

Add to your existing `config.py`:
```python
# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Celery configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
```

### 3. Update .env

```bash
# Add to your .env
REDIS_URL=redis://localhost:6379
```

### 4. Copy new files

Move these files to your project:
- `services/extract.py`
- `services/parse.py`
- `services/validate.py`
- `celery_tasks.py`
- `redis_client.py`
- `api/upload.py`

### 5. Update app.py

Add to your existing `app.py`:

```python
from redis_client import init_redis, close_redis
from api import upload

# Add Redis startup/shutdown
@app.on_event("startup")
async def startup():
    await init_db()
    await init_redis()  # ← Add this

@app.on_event("shutdown")
async def shutdown():
    await close_db()
    await close_redis()  # ← Add this

# Include upload routes
app.include_router(upload.router)
```

### 6. Start Redis

```bash
# On macOS with Homebrew:
brew services start redis

# Or run directly:
redis-server
```

### 7. Start Celery worker

In a separate terminal:
```bash
celery -A celery_tasks worker --loglevel=info
```

### 8. Start FastAPI server

```bash
python -m uvicorn app:app --reload
```

You should see:
```
✓ Database tables created
✓ Redis connected
✓ Server running at http://localhost:8000
```

## Testing

### Upload a PDF:
```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@sample.pdf" \
  -H "Authorization: Bearer your_token"
```

### Check status:
```bash
curl http://localhost:8000/api/upload/pdf_xyz/status
```

### Watch worker logs:
```
celery worker output:
[tasks] process_pdf: Starting
[tasks] extract: Extracting text...
[tasks] parse: Calling Claude API...
[tasks] validate: Validating transactions...
[tasks] save: Saving to database...
[tasks] process_pdf: Done! 42 transactions
```

## Key Concepts

### **Async/Await Pattern**
- `async def` functions don't block
- `await` pauses on I/O (database, API calls)
- Other requests handled while waiting

### **Redis Queue**
- Celery stores tasks in Redis
- Worker picks up tasks and processes
- Supports 1000s of tasks concurrently

### **Pub/Sub Notifications**
- Redis channel: `user:123:uploads`
- Server publishes status updates
- Frontend subscribes (WebSocket/polling)
- Real-time feedback to user

### **Caching via Hash**
- Calculate SHA-256 of PDF
- Check if hash already processed
- Return cached transactions (skip Claude call)
- Saves money + time

## What's Next (Step 3)

In Step 3, we'll add:
- `GET /api/transactions` — List user's transactions
- `GET /api/transactions/categories` — Filter by category
- `GET /api/analytics/trends` — Monthly spending trends
- `GET /api/analytics/anomalies` — Unusual transactions
- `GET /api/analytics/budgets` — Budget tracking

---

## Troubleshooting

**Redis connection refused?**
```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# If not, start it:
redis-server
```

**Celery tasks not processing?**
```bash
# Check worker is running:
celery -A celery_tasks worker --loglevel=info

# Check Redis connection:
redis-cli
> INFO
```

**Claude API errors?**
```bash
# Verify ANTHROPIC_API_KEY in .env
echo $ANTHROPIC_API_KEY

# Test with curl:
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model": "claude-3-5-sonnet-20241022", "max_tokens": 10, "messages": [{"role": "user", "content": "test"}]}'
```

---

## Performance Tips

1. **Cache frequently-processed PDFs** (hash-based)
2. **Batch transactions** (save multiple at once)
3. **Use connection pooling** (SQLAlchemy handles this)
4. **Monitor Redis memory** (set max eviction policy)
5. **Scale workers** (add more Celery workers for load)

You're now ready for real-time, async transaction processing!
