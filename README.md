# CC Pipeline Web v2.0

> Fast, async credit card statement analyzer. Upload PDFs → Get real-time transaction insights.

**Problem:** The original Streamlit app was slow (5-12 second waits on every interaction).  
**Solution:** Rebuilt as async FastAPI backend with Redis task queue and real-time processing.

## Features

✅ **No waiting** — Upload → instant response → background processing  
✅ **Real-time feedback** — Get notified when PDF processing completes  
✅ **Fast queries** — Async database with connection pooling  
✅ **Smart caching** — Same PDF = instant response (no Claude API re-call)  
✅ **Type-safe** — Pydantic validates all requests/responses  
✅ **Production-ready** — Supabase + Redis + JWT auth  

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              FRONTEND (React/Next.js)               │
│  - Login form                                       │
│  - PDF upload                                       │
│  - Real-time "Processing..." status                │
│  - Transaction list & analytics                    │
└──────────────────┬──────────────────────────────────┘
                   │ HTTP/WebSocket
                   ↓
┌─────────────────────────────────────────────────────┐
│           FASTAPI BACKEND (Async)                   │
│  - Auth (JWT + bcrypt)                             │
│  - Upload endpoint (queues to Redis)               │
│  - Transaction endpoints (list, filter, delete)    │
│  - Analytics endpoints (trends, anomalies, etc.)   │
└──────────────────┬──────────────────────────────────┘
         │         │         │
         ↓         ↓         ↓
    ┌────────┐ ┌────────┐ ┌──────────────┐
    │ Redis  │ │Postgres│ │Claude API    │
    │ Queue  │ │(via    │ │(extraction)  │
    │ & Cache│ │SQLAlchemy)              │
    └────┬───┘ └────────┘ └──────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────┐
│     BACKGROUND WORKER (Celery + Redis)             │
│  1. Extract PDF text (pdfplumber)                  │
│  2. Call Claude API (parse transactions)           │
│  3. Validate data (Pydantic)                       │
│  4. Save to Postgres (SQLAlchemy)                  │
│  5. Notify frontend (Redis Pub/Sub)                │
└─────────────────────────────────────────────────────┘
```

## Tech Stack

### Backend
- **Framework:** FastAPI 0.109.2 (async Python web framework)
- **Database:** Supabase Postgres + SQLAlchemy 2.0.28 + asyncpg (async driver)
- **Validation:** Pydantic 2.7.0 (request/response validation)
- **Authentication:** JWT tokens + bcrypt (password hashing)
- **Task Queue:** Celery 5.3.6 + Redis 5.0.1 (async PDF processing)
- **PDF Processing:** pdfplumber 0.10.3 (text extraction)
- **LLM:** Anthropic Claude API (transaction extraction)

### Frontend (Coming Soon)
- React 18 + Next.js 14
- TanStack Query (data fetching)
- Tailwind CSS (styling)

### Infrastructure
- Supabase (managed Postgres)
- Upstash or local Redis
- Railway/Render (deployment)

## Quick Start

### Prerequisites
- Python 3.12+
- Redis (local or Upstash)
- Supabase Postgres instance
- Anthropic API key

### 1. Clone & Setup

```bash
git clone https://github.com/yashitajain/cc_analyzer_pipeline.git
cd cc_pipeline_web

# Create Python 3.12 venv
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@db.supabase.co:5432/postgres

# Redis
REDIS_URL=redis://localhost:6379

# Security
SECRET_KEY=your-secret-key-here
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Start Services

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Celery worker
celery -A celery_tasks worker --loglevel=info

# Terminal 3: FastAPI server
python -m uvicorn app:app --reload
```

Server runs at: http://localhost:8000

### 4. Test It

```bash
# Register user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123","email":"test@example.com"}'

# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'

# Upload PDF
curl -X POST http://localhost:8000/api/upload \
  -F "file=@statement.pdf" \
  -H "Authorization: Bearer YOUR_TOKEN"

# List transactions
curl http://localhost:8000/api/transactions
```

## API Endpoints

### Authentication
```
POST   /api/auth/register      Register new user
POST   /api/auth/login         Login (returns JWT token)
GET    /api/me                 Get current user
```

### Upload & Processing
```
POST   /api/upload             Upload PDF for processing
GET    /api/upload/{id}/status Check processing status
```

### Transactions
```
GET    /api/transactions       List transactions (with pagination)
GET    /api/transactions?start_date=2024-10-01&category=Dining
GET    /api/transactions/categories  Category breakdown
GET    /api/transactions/{id}  Get single transaction
DELETE /api/transactions/{id}  Delete transaction
```

### Analytics
```
GET    /api/analytics/trends     Monthly spending by category
GET    /api/analytics/anomalies  Find unusual transactions
GET    /api/analytics/recurring  Find recurring merchants
GET    /api/analytics/summary    Summary statistics
```

## Example Workflows

### Upload & Process PDF

```bash
# 1. Upload
curl -X POST http://localhost:8000/api/upload \
  -F "file=@statement.pdf" \
  -H "Authorization: Bearer TOKEN"

# Response:
# {
#   "file_id": "pdf_abc123",
#   "status": "processing",
#   "message": "PDF uploaded. Processing in background."
# }

# 2. Check status (poll every 2 seconds)
curl http://localhost:8000/api/upload/pdf_abc123/status

# Progression: extracting → parsing → validating → saving → done

# 3. List transactions (when done)
curl http://localhost:8000/api/transactions
```

### Analyze Spending

```bash
# Get 6 months of trends
curl http://localhost:8000/api/analytics/trends?months=6

# Find anomalies (unusual spending)
curl http://localhost:8000/api/analytics/anomalies?threshold=2.0

# Find recurring (subscriptions)
curl http://localhost:8000/api/analytics/recurring?min_occurrences=3

# Summary
curl http://localhost:8000/api/analytics/summary
```

## Performance

### Before (Streamlit)
- Page reload on every click: ~2-3 seconds
- Tab switching: ~5 seconds
- Changing months: ~3-5 seconds
- PDF processing: ~10-15 seconds (blocking)

### After (FastAPI + Async)
- Upload response: <500ms (async in background)
- Transaction query: <100ms (cached, pooled connections)
- Analytics query: <200ms (pre-computed)
- PDF processing: 10-15 seconds (non-blocking, user sees progress)

## Project Structure

```
cc_pipeline_web/
├── api/
│   ├── __init__.py
│   ├── upload.py           # PDF upload endpoint
│   ├── transactions.py     # Transaction CRUD
│   └── analytics.py        # Analytics endpoints
├── services/
│   ├── __init__.py
│   ├── extract.py          # PDF text extraction
│   ├── parse.py            # Claude API calls
│   ├── validate.py         # Pydantic validation
│   └── analytics.py        # Analytics logic
├── app.py                  # FastAPI app + routes
├── auth.py                 # JWT + bcrypt
├── config.py               # Environment config
├── database.py             # Async DB connection
├── db_models.py            # SQLAlchemy models
├── models_pydantic.py      # Pydantic schemas
├── celery_tasks.py         # Background tasks
├── redis_client.py         # Redis connection
├── requirements.txt        # Python dependencies
├── .env.example            # Config template
├── .gitignore              # Git ignore rules
├── STEP1_GUIDE.md          # Backend foundation
├── STEP2_GUIDE.md          # Async processing
└── STEP3_GUIDE.md          # Transaction & analytics APIs
```

## Key Concepts

### Async/Await
All I/O operations are non-blocking:
```python
async def upload_pdf():
    # Database query doesn't block other requests
    result = await db.execute(query)
```

### Connection Pooling
SQLAlchemy automatically manages a pool of 20 DB connections, reusing them across requests.

### Redis Task Queue
PDFs are queued in Redis, processed by background workers:
```
Upload → Redis Queue → Celery Worker → DB → Pub/Sub notification
```

### Caching
Same PDF (by SHA-256 hash) = instant response, no Claude API call.

### Real-time Notifications
Redis Pub/Sub channels notify frontend of processing progress:
- `extracting` → `parsing` → `validating` → `saving` → `done`

## Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=. tests/
```

## Deployment

### Production Checklist

- [ ] Change `SECRET_KEY` in `.env` (generate with `openssl rand -hex 32`)
- [ ] Set `DEBUG=False`
- [ ] Use Upstash Redis (serverless)
- [ ] Enable Row Level Security in Supabase
- [ ] Set up automated backups
- [ ] Add rate limiting
- [ ] Enable HTTPS
- [ ] Configure CORS for your frontend domain
- [ ] Set up monitoring (Sentry, etc.)

### Deploy on Railway

```bash
# 1. Create Railway project
# 2. Connect GitHub repo
# 3. Set environment variables
# 4. Add PostgreSQL plugin
# 5. Add Redis plugin
# 6. Deploy
```

## Roadmap

- [x] Step 1: FastAPI foundation
- [x] Step 2: Async PDF processing pipeline
- [x] Step 3: Transaction & analytics APIs
- [ ] Step 4: Unit tests & accuracy evals
- [ ] Step 5: React/Next.js frontend
- [ ] Step 6: Docker + CI/CD deployment
- [ ] Real-time WebSocket updates
- [ ] Budget tracking & alerts
- [ ] Export to CSV/PDF
- [ ] Mobile app

## Contributing

This is a portfolio project. Feel free to fork and modify!

## License

MIT

## Author

**Yashita Jain** — [GitHub](https://github.com/yashitajain) | [Email](mailto:jain.yashita26@gmail.com)

Building AI systems. Repositioning from analytics to AI/ML engineering.

---

## Support

For issues or questions:
1. Check STEP1/2/3_GUIDE.md for setup help
2. Open a GitHub issue
3. Review the API docs at `http://localhost:8000/docs` (FastAPI Swagger UI)

**Happy analyzing! 🎉**
