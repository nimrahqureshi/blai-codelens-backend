import os
import uuid
import json
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ✅ Load environment variables
load_dotenv()

# ✅ Initialize FastAPI app
app = FastAPI(title="BLAI CodeLens Backend")

# ✅ Allowed origins (frontend + local)
ALLOWED_ORIGINS = [
    "https://blai-codelens-frontend.vercel.app",
    "https://www.blai-codelens-frontend.vercel.app",
    "https://blai-portfolio.vercel.app",
    "https://www.blai-portfolio.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# ✅ Add CORS middleware once
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Load API key
API_KEY = os.getenv("BLAI_API_KEY", "dev_key")
print(f"✅ Loaded BLAI_API_KEY: {API_KEY}")

# ✅ Artifacts folder
ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(exist_ok=True)

# ✅ Queue file path (used by worker)
QUEUE_FILE = Path("queue.json")
QUEUE_FILE.touch(exist_ok=True)

# ✅ Request model
class SubmitRequest(BaseModel):
    repo_url: str
    ref: str | None = None
    notify_email: str | None = None

# ------------------------------
# HELPER: Enqueue real worker job
# ------------------------------
def enqueue_job(review_id: str, payload: dict):
    """Append a new job to queue.json for worker.py to process"""
    try:
        queue_data = json.loads(QUEUE_FILE.read_text() or "[]")
    except json.JSONDecodeError:
        queue_data = []

    queue_data.append({"review_id": review_id, "payload": payload})
    QUEUE_FILE.write_text(json.dumps(queue_data, indent=2))
    print(f"📥 Enqueued review job: {review_id}")

# ------------------------------
# POST /submit — start code review
# ------------------------------
@app.post("/submit")
async def submit(req: SubmitRequest, request: Request):
    key = request.headers.get("x-api-key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized — Invalid API Key")

    review_id = str(uuid.uuid4())
    print(f"📩 Received request for repo: {req.repo_url}")

    # ✅ Use real enqueue_job to push to queue.json
    enqueue_job(review_id, req.dict())

    return {"review_id": review_id, "status": "queued"}

# ------------------------------
# GET /artifacts/{id} — fetch review result
# ------------------------------
@app.get("/artifacts/{review_id}")
async def get_artifact(review_id: str):
    artifact_file = ARTIFACTS_DIR / f"{review_id}.json"
    if not artifact_file.exists():
        raise HTTPException(status_code=404, detail="Result not ready yet — please retry later")
    return json.loads(artifact_file.read_text(encoding="utf-8"))

# ------------------------------
# GET / — health check
# ------------------------------
@app.get("/")
async def root():
    return {"message": "✅ BLAI CodeLens backend is running properly"}

# ------------------------------
# Run locally
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
