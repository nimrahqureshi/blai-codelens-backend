import os
import json
import time
import tempfile
import shutil
import subprocess
from git import Repo
from pathlib import Path
import asyncio
from datetime import datetime

# --- Import LLM functions (optional) ---
try:
    from server.llm_client import triage_via_llm, patch_via_llm
except ImportError:
    triage_via_llm = None
    patch_via_llm = None


ARTIFACTS_DIR = Path("artifacts")
QUEUE_FILE = Path("queue.json")


# ------------------------------
# UTILITIES
# ------------------------------
def run_pylint(workdir):
    """Run pylint and return JSON results"""
    try:
        print("🔎 Running pylint...")
        p = subprocess.run(
            ["pylint", workdir, "-f", "json"],
            capture_output=True,
            text=True,
            timeout=90
        )
        out = p.stdout.strip() or "[]"
        return json.loads(out)
    except Exception as e:
        print("⚠️ Pylint failed:", e)
        return []


def run_semgrep(workdir):
    """Run semgrep and return JSON results"""
    try:
        print("🔎 Running semgrep...")
        p = subprocess.run(
            ["semgrep", "--config", "auto", workdir, "--json"],
            capture_output=True,
            text=True,
            timeout=150
        )
        out = p.stdout.strip() or "{}"
        return json.loads(out)
    except Exception as e:
        print("⚠️ Semgrep failed:", e)
        return {}


# ------------------------------
# MAIN REVIEW PROCESS
# ------------------------------
async def process_review(review_id, payload):
    repo_url = payload.get("repo_url")
    ref = payload.get("ref") or "HEAD"

    print(f"🚀 Starting review for {repo_url}")
    base_dir = tempfile.mkdtemp(prefix=f"rev_{review_id}_")
    ARTIFACTS_DIR.mkdir(exist_ok=True)

    try:
        # --- Clone repo ---
        print("📦 Cloning repo...")
        Repo.clone_from(repo_url, base_dir, depth=1)

        # --- Static analysis ---
        pylint_results = run_pylint(base_dir)
        semgrep_results = run_semgrep(base_dir)
        static_findings = {"pylint": pylint_results, "semgrep": semgrep_results}

        # --- Collect Python files ---
        files = []
        for p in Path(base_dir).rglob("*.py"):
            files.append({
                "path": str(p.relative_to(base_dir)),
                "snippet": p.read_text(errors="ignore")[:2000]
            })
            if len(files) >= 8:
                break

        # --- LLM triage ---
        triage = None
        patch_resp = None

        if triage_via_llm:
            try:
                print("🧠 Running LLM triage...")
                triage = triage_via_llm(review_id, repo_url, static_findings, files)
                if triage and triage.get("findings"):
                    patch_resp = patch_via_llm(triage["findings"][0], files, static_findings)
            except Exception as e:
                print("⚠️ LLM triage failed:", e)

        # --- Fallback mock ---
        if not triage:
            print("⚙️ Using mock analysis fallback...")
            triage = {
                "findings": [
                    {
                        "id": "mock-1",
                        "severity": "medium",
                        "short_reason": "Missing docstring in setup.py",
                        "evidence": [
                            {
                                "path": "setup.py",
                                "snippet": "# Example snippet (mock)",
                            }
                        ],
                    },
                    {
                        "id": "mock-2",
                        "severity": "low",
                        "short_reason": "Long function in main.py",
                        "evidence": [
                            {
                                "path": "src/app/main.py",
                                "snippet": "def long_function(): pass",
                            }
                        ],
                    },
                ]
            }
            patch_resp = {"diff": "", "test": ""}

        # --- Save results ---
        result = {
            "review_id": review_id,
            "repo": repo_url,
            "triage": triage,
            "patch": patch_resp,
            "timestamp": datetime.now().isoformat(),
        }

        ARTIFACTS_DIR.joinpath(f"{review_id}.json").write_text(
            json.dumps(result, indent=2),
            encoding="utf-8"
        )

        print(f"✅ Review completed for {repo_url} ({review_id})")

    except Exception as e:
        print(f"❌ Error processing {repo_url}: {e}")
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


# ------------------------------
# QUEUE HANDLING
# ------------------------------
def enqueue_review(review_id, payload):
    """
    Add a new review job to the queue.json file.
    """
    QUEUE_FILE.touch(exist_ok=True)
    try:
        queue_data = json.loads(QUEUE_FILE.read_text() or "[]")
    except json.JSONDecodeError:
        queue_data = []

    queue_data.append({"review_id": review_id, "payload": payload})
    QUEUE_FILE.write_text(json.dumps(queue_data, indent=2))
    print(f"📥 Enqueued review job: {review_id}")


async def main_loop():
    print("👀 Worker started — waiting for new jobs...")

    while True:
        if QUEUE_FILE.exists():
            try:
                queue_data = json.loads(QUEUE_FILE.read_text() or "[]")
                if queue_data:
                    job = queue_data.pop(0)
                    QUEUE_FILE.write_text(json.dumps(queue_data, indent=2))
                    await process_review(job["review_id"], job["payload"])
            except Exception as e:
                print("⚠️ Queue processing error:", e)

        await asyncio.sleep(3)  # Poll every 3 seconds


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n🛑 Worker stopped manually.")
