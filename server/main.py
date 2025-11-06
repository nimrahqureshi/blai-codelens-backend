import os
import uuid
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ✅ Load environment variables
load_dotenv()

# ✅ Initialize FastAPI app
app = FastAPI(title="BLAI CodeLens Backend")

# ✅ Define allowed origins (your frontend + local)
ALLOWED_ORIGINS = [
    "https://blai-codelens-frontend.vercel.app",   # your deployed frontend
    "https://www.blai-codelens-frontend.vercel.app",
    "https://blai-portfolio.vercel.app",           # optional secondary domain
    "https://www.blai-portfolio.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# ✅ Add CORS middleware after app initialization
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],       # allow all HTTP methods
    allow_headers=["*"],       # allow all headers
)

# ✅ Load API key safely
API_KEY = os.getenv("BLAI_API_KEY", "dev_key")
print(f"✅ Loaded BLAI_API_KEY: {API_KEY}")

# ✅ In-memory job results
JOB_RESULTS = {}

# ✅ Request model
class SubmitRequest(BaseModel):
    repo_url: str
    ref: str | None = None
    notify_email: str | None = None


# ✅ Simulated async review process
async def enqueue_review(review_id: str, data: dict):
    print(f"📥 Started review job {review_id} for {data.get('repo_url')}")
    await asyncio.sleep(4)  # simulate AI code review delay

    result = {
        "repo": data.get("repo_url"),
        "summary": "✅ Code review completed successfully.",
        "issues": [
            {"type": "style", "message": "Variable names follow Python naming conventions."},
            {"type": "security", "message": "No exposed API keys or secrets detected."},
            {"type": "structure", "message": "Project folder structure looks clean and modular."},
        ],
    }

    JOB_RESULTS[review_id] = result
    print(f"✅ Job {review_id} finished and stored results")


# ✅ POST /submit — start code review
@app.post("/submit")
async def submit(req: SubmitRequest, request: Request):
    key = request.headers.get("x-api-key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized — Invalid API Key")

    review_id = str(uuid.uuid4())
    print(f"📩 Received request for repo: {req.repo_url}")

    asyncio.create_task(enqueue_review(review_id, req.dict()))
    return {"review_id": review_id, "status": "queued"}


# ✅ GET /artifacts/{id} — retrieve code review results
@app.get("/artifacts/{review_id}")
async def get_artifact(review_id: str):
    if review_id not in JOB_RESULTS:
        raise HTTPException(status_code=404, detail="Result not ready yet — please retry later")
    return JOB_RESULTS[review_id]


# ✅ Health check
@app.get("/")
async def root():
    return {"message": "✅ BLAI CodeLens backend is running properly"}


# ✅ Run locally
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
