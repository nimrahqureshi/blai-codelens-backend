import os
import uuid
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from server.worker import enqueue_review

# Load environment variables early
load_dotenv()

# Create FastAPI app once
app = FastAPI()

# CORS setup (frontend can call backend)
origins = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API key (for security)
API_KEY = os.getenv("BLAI_API_KEY", "dev_key")
print("✅ Loaded BLAI_API_KEY:", API_KEY)

# Request body model
class SubmitRequest(BaseModel):
    repo_url: str
    ref: str | None = None
    notify_email: str | None = None

# POST /submit — queue a new code review
@app.post("/submit")
async def submit(req: SubmitRequest, request: Request):
    key = request.headers.get("x-api-key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    review_id = str(uuid.uuid4())
    asyncio.create_task(enqueue_review(review_id, req.dict()))
    return {"review_id": review_id, "status": "queued"}

# Optional: quick health check
@app.get("/")
async def root():
    return {"message": "BLAI CodeLens backend running ✅"}
