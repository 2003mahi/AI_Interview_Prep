from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import rag_router, ingest_router

app = FastAPI(title="Production RAG API")

# CORS (configured for frontend origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag_router, prefix="/api")
app.include_router(ingest_router, prefix="/api")
