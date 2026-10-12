# Step 3: Transaction & Analytics Endpoints — Complete Guide

## What We Built

Three new API modules with full transaction management and spending analytics:

### **1. Transaction Endpoints** (`api/transactions.py`)
- List user's transactions with pagination
- Filter by date range, category
- Get single transaction details
- Delete transactions

### **2. Analytics Endpoints** (`api/analytics.py`)
- Monthly spending trends by category
- Anomaly detection (unusual transactions)
- Recurring transaction detection
- Summary statistics

### **3. Analytics Service** (`services/analytics.py`)
- Spending trends calculation
- Statistical anomaly detection
- Recurring merchant detection
- Summary aggregation

---

## New Files

### **api/transactions.py**
Transaction listing and management.

**Endpoints:**
- `GET /api/transactions` — List with pagination & filters
- `GET /api/transactions/categories` — Get category breakdown
- `GET /api/transactions/{id}` — Get single transaction
- `DELETE /api/transactions/{id}` — Delete transaction

**Query Parameters:**
- `skip` — Pagination offset (default: 0)
- `limit` — Items per page, max 100 (default: 50)
- `start_date` — Filter from date (YYYY-MM-DD)
- `end_date` — Filter to date (YYYY-MM-DD)
- `category` — Filter by category name

### **api/analytics.py**
Spending analytics and insights.

**Endpoints:**
- `GET /api/analytics/trends` — Monthly spending by category
- `GET /api/analytics/anomalies` — Unusual transactions
- `GET /api/analytics/recurring` — Recurring merchants
- `GET /api/analytics/summary` — Total stats

### **services/analytics.py**
Analytics calculation logic.

**Functions:**
- `get_spending_trends()` — Group transactions by month/category
- `detect_anomalies()` — Find outliers using std dev
- `detect_recurring()` — Find merchants appearing 3+ times
- `get_summary()` — Aggregate totals

---

## How It Works (Examples)

### **List transactions:**
```bash
curl http://localhost:8000/api/transactions
```

Response:
```json
{
  "success": true,
  "data": {
    "transactions": [
      {
        "id": 1,
        "date": "2024-10-15",
        "merchant_name": "Starbucks",
        "category": "Dining",
        "amount": 5.50,
        "is_credit": false,
        "source_file": "pdf_abc123"
      }
    ],
    "count": 42
  }
}
```

### **Filter by date range and category:**
```bash
curl "http://localhost:8000/api/transactions?start_date=2024-10-01&end_date=2024-10-31&category=Dining"
```

### **Get spending trends:**
```bash
curl http://localhost:8000/api/analytics/trends?months=6
```

Response:
```json
{
  "success": true,
  "data": {
    "trends": {
      "2024-10": {
        "Dining": 150.50,
        "Shopping": 200.00,
        "Travel": 0
      },
      "2024-09": {
        "Dining": 120.00,
        "Shopping": 180.00
      }
    }
  }
}
```

### **Find anomalies:**
```bash
curl "http://localhost:8000/api/analytics/anomalies?threshold=2.0"
```

Response:
```json
{
  "success": true,
  "data": {
    "anomalies": [
      {
        "id": 42,
        "date": "2024-10-20",
        "merchant": "Fancy Restaurant",
        "category": "Dining",
        "amount": 250.00,
        "mean_for_category": 45.50,
        "std_dev": 35.20,
        "threshold": 116.10
      }
    ]
  }
}
```

### **Get recurring transactions:**
```bash
curl "http://localhost:8000/api/analytics/recurring?min_occurrences=3"
```

Response:
```json
{
  "success": true,
  "data": {
    "recurring": [
      {
        "merchant": "Netflix",
        "count": 12,
        "total": 120.00,
        "average": 10.00
      },
      {
        "merchant": "Gym Membership",
        "count": 6,
        "total": 180.00,
        "average": 30.00
      }
    ]
  }
}
```

### **Get summary:**
```bash
curl http://localhost:8000/api/analytics/summary
```

Response:
```json
{
  "success": true,
  "data": {
    "summary": {
      "total_transactions": 127,
      "total_spent": 5430.50,
      "total_credits": 120.00,
      "average_transaction": 42.86,
      "net_amount": 5310.50,
      "top_category": "Shopping"
    }
  }
}
```

---

## Setup Instructions

### **1. Create directories:**
```bash
cd ~/Documents/AI\ projects/cc_pipeline_web

# Create folders if they don't exist
mkdir -p api services
```

### **2. Copy new files:**

Move these files to your project:
- `api/transactions.py`
- `api/analytics.py`
- `api/__init__.py`
- `services/analytics.py`
- `services/__init__.py`

### **3. Update app.py:**

Add imports at the top:
```python
from api import upload, transactions, analytics
```

Update the "Include Routers" section:
```python
# Include upload routes
app.include_router(upload.router)
app.include_router(transactions.router)  # ← ADD
app.include_router(analytics.router)     # ← ADD
```

### **4. Test it:**

```bash
# Start server
python -m uvicorn app:app --reload

# In another terminal, test endpoints:
curl http://localhost:8000/api/transactions
curl http://localhost:8000/api/analytics/summary
curl http://localhost:8000/api/analytics/trends
```

---

## Key Concepts

### **Pagination**
- `skip` + `limit` for large result sets
- Default: 50 items per page, max 100
- Usage: `/api/transactions?skip=50&limit=50` (page 2)

### **Filtering**
- Date range: `start_date` and `end_date` (YYYY-MM-DD format)
- Category: exact match on `category_name`
- Combine filters: `/api/transactions?start_date=2024-10-01&category=Dining`

### **Anomaly Detection**
- Uses **standard deviation** method
- Formula: `anomaly_if: amount > mean + (std_dev * threshold)`
- Threshold:
  - 1.0 = very sensitive (many false positives)
  - 2.0 = balanced (recommended)
  - 3.0+ = less sensitive (only extreme outliers)

### **Recurring Detection**
- Counts transactions by exact merchant name match
- Minimum 3 occurrences by default
- Useful for finding subscriptions and regular purchases

### **Summary Stats**
- Total spent: sum of charges only
- Total credits: sum of refunds/credits
- Net amount: spent minus credits
- Average: per-charge amount only
- Top category: highest spending category

---

## What's Next (Step 4)

In Step 4, we'll build:
- Unit tests (pytest)
- Accuracy evaluations (comparing Claude extractions vs. manual)
- Integration tests
- Test fixtures

---

## Troubleshooting

**Import errors?**
```bash
# Make sure __init__.py files exist:
touch api/__init__.py
touch services/__init__.py
```

**404 on endpoints?**
```bash
# Check routers are included in app.py:
grep "include_router" app.py
# Should see: upload.router, transactions.router, analytics.router
```

**No transactions returned?**
```bash
# Upload a PDF first to generate test data
curl -X POST http://localhost:8000/api/upload \
  -F "file=@sample.pdf"

# Wait for Celery worker to process
# Then query transactions
```

---

## Full API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/transactions` | GET | List transactions |
| `/api/transactions/categories` | GET | Category breakdown |
| `/api/transactions/{id}` | GET | Get single transaction |
| `/api/transactions/{id}` | DELETE | Delete transaction |
| `/api/analytics/trends` | GET | Monthly trends |
| `/api/analytics/anomalies` | GET | Find outliers |
| `/api/analytics/recurring` | GET | Find recurring |
| `/api/analytics/summary` | GET | Summary stats |
| `/api/upload` | POST | Upload PDF |
| `/api/auth/register` | POST | Register user |
| `/api/auth/login` | POST | Login user |
| `/api/me` | GET | Get current user |

---

**You now have a complete transaction management & analytics API!**

Ready for Step 4 (testing & evals)?
