import os
import json
import time
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
ARTIFACTS_DIR = Path("artifacts")
QUEUE_FILE = Path("queue.json")
# NOTE: The worker relies on the `git` command being installed (handled by Dockerfile)

# --- HELPER FUNCTIONS ---

def run_code_analysis(repo_path: Path) -> dict:
    """
    Simulates running actual code analysis tools (like pylint or semgrep)
    on the cloned repository.
    """
    print(f"🔬 Starting analysis in: {repo_path}")
    
    # 1. Pylint Example (requires 'requirements.txt' to list pylint)
    try:
        # Scan all Python files in the repository
        result = subprocess.run(
            ["pylint", "--disable=all", "--enable=C0114,C0116,W0613", str(repo_path)],
            capture_output=True,
            text=True,
            check=False # Do not raise error if linter fails
        )
        pylint_output = result.stdout
        
    except FileNotFoundError:
        pylint_output = "Pylint not found or not configured."

    # 2. Simple File Count/Size Metric
    file_count = len(list(repo_path.rglob('*.*')))
    
    return {
        "summary": f"Initial review complete. Found {file_count} files.",
        "pylint_result": pylint_output,
        "metrics": {"total_files": file_count},
        "recommendations": [
            "Consider adding comprehensive type hints.",
            "Break down large functions into smaller, focused units."
        ]
    }

def process_job(job: dict):
    """Clones the repo, runs analysis, and saves the artifact."""
    review_id = job["review_id"]
    payload = job["payload"]
    repo_url = payload.get("repo_url")
    ref = payload.get("ref") or "main" # default branch

    print(f"⚙️ Processing job {review_id} for {repo_url} at ref {ref}")

    # Create a temporary directory for cloning
    with TemporaryDirectory() as temp_dir_str:
        repo_path = Path(temp_dir_str) / "repo"

        # 1. Clone the repository
        try:
            clone_cmd = ["git", "clone", "--depth", "1", "--branch", ref, repo_url, str(repo_path)]
            subprocess.run(clone_cmd, check=True, capture_output=True, text=True)
            print(f"✅ Successfully cloned repo to {repo_path}")
            
            # 2. Run the analysis
            analysis_result = run_code_analysis(repo_path)

            # 3. Compile final artifact
            final_artifact = {
                "id": review_id,
                "timestamp": time.time(),
                "repo_url": repo_url,
                "ref": ref,
                "status": "completed",
                "result": analysis_result
            }
            
        except subprocess.CalledProcessError as e:
            final_artifact = {
                "id": review_id,
                "timestamp": time.time(),
                "repo_url": repo_url,
                "status": "failed",
                "error": f"Git clone failed. Check if repo is public, URL is correct, or branch '{ref}' exists.",
                "details": e.stderr.strip()
            }
            print(f"❌ Worker failed for {review_id}: {final_artifact['error']}")
        except Exception as e:
            final_artifact = {
                "id": review_id,
                "timestamp": time.time(),
                "repo_url": repo_url,
                "status": "error",
                "error": f"An unexpected worker error occurred: {str(e)}"
            }
            print(f"💥 Worker exception for {review_id}: {e}")

    # 4. Save the artifact result to the file system
    artifact_file = ARTIFACTS_DIR / f"{review_id}.json"
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    artifact_file.write_text(json.dumps(final_artifact, indent=2), encoding="utf-8")
    print(f"💾 Saved artifact: {artifact_file}")

# --- MAIN WORKER LOOP ---

def worker_main():
    """Main function to run the worker loop"""
    print("🚀 BLAI CodeLens Worker started.")
    
    while True:
        try:
            # 1. Read and lock the queue file
            if not QUEUE_FILE.exists():
                time.sleep(5)
                continue

            queue_content = QUEUE_FILE.read_text()
            if not queue_content:
                queue_data = []
            else:
                queue_data = json.loads(queue_content)
                
            if not queue_data:
                # print("😴 Queue is empty. Sleeping...")
                time.sleep(5)
                continue

            # 2. Pop the first job
            job = queue_data.pop(0)
            
            # 3. Overwrite the queue file (removes the job)
            QUEUE_FILE.write_text(json.dumps(queue_data, indent=2))
            
            # 4. Process the job (this is where the long work happens)
            process_job(job)

        except json.JSONDecodeError:
            print(f"🚨 Error decoding {QUEUE_FILE}. Clearing file.")
            QUEUE_FILE.write_text("[]")
        except Exception as e:
            print(f"Unhandled exception in worker loop: {e}")
        
        # Prevent the worker from spinning too fast
        time.sleep(1)

if __name__ == "__main__":
    worker_main()
