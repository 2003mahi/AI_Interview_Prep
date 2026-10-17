# AI Interview Prep Assistant

A full-stack AI-powered interview preparation assistant.

## Tech Stack

| Layer     | Technology                        |
|-----------|-----------------------------------|
| Frontend  | Next.js 16, TypeScript, Tailwind CSS |
| Backend   | FastAPI (Python 3.14)             |
| Database  | Supabase PostgreSQL               |
| Auth      | Supabase Auth                     |
| DevOps    | Docker, Docker Compose            |

## Project Structure

```
├── frontend/          # Next.js app
│   ├── app/           # App Router pages
│   └── package.json
├── backend/           # FastAPI app
│   ├── app/
│   │   ├── main.py        # Entry point
│   │   ├── config.py      # Environment settings
│   │   ├── logger.py      # Structured logging
│   │   └── api/v1/        # Versioned API routes
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

# ── Backend ─────────────────────────────────────────────────────
cd backend

# (once) create and activate a virtual‑env
python -m venv venv                # creates ./venv
.\venv\Scripts\Activate.ps1        # PowerShell – use `source venv/bin/activate` on Linux/macOS

# install Python requirements
pip install -r requirements.txt

# copy the example env and fill in your Supabase creds
cp .env.example .env   # edit .env afterwards

# start the FastAPI server (auto‑reload enabled)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# → API available at http://localhost:8000
# → Swagger docs at http://localhost:8000/docs


# ── Frontend (Next.js) ─────────────────────────────────────────────
cd ../frontend

# install Node dependencies (run only the first time)
npm install

# start the development server
npm run dev
# → App available at http://localhost:3000



## Quick Start

### Backend

```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
cp .env.example .env           # Edit with your Supabase creds
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker

```bash
docker compose up --build
```

## API Endpoints

| Method | Path             | Description               |
|--------|------------------|---------------------------|
| GET    | `/health`        | Health check              |
| POST   | `/api/v1/interview` | Generate interview questions |

## Environment Variables

See `backend/.env.example` for required variables.


## One–liner version (if you just want to copy‑paste everything):
cd backend && python -m venv venv && .\venv\Scripts\Activate.ps1 && pip install -r requirements.txt && cp .env.example .env && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
cd ../frontend && npm install && npm run dev

