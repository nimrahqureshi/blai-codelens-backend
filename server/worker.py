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

        # --- Build triage from static analyzers (deterministic) ---
        def map_pylint_to_finding(item):
            typ = item.get("type", "").lower()
            severity = "low"
            if typ in ("error", "fatal"):
                severity = "high"
            elif typ == "warning":
                severity = "medium"
            elif typ in ("refactor", "convention", "info"):
                severity = "low"

            path = item.get("path") or item.get("module") or "<unknown>"
            line = item.get("line") or 0
            message = item.get("message") or item.get("symbol") or "pylint issue"

            return {
                "id": f"pylint-{path}-{line}-{item.get('symbol','')}",
                "tool": "pylint",
                "severity": severity,
                "title": item.get("symbol", typ),
                "description": message,
                "evidence": [{"path": path, "start_line": line, "snippet": ""}],
                "confidence": 0.8,
            }

        def map_semgrep_to_finding(item):
            extra = item.get("extra", {})
            check_id = item.get("check_id") or extra.get("id") or "semgrep"
            path = item.get("path") or extra.get("path") or "<unknown>"
            start = None
            if isinstance(item.get("start"), dict):
                start = item["start"].get("line")
            elif isinstance(extra.get("lines"), str):
                start = 0
            severity = extra.get("severity") or "medium"

            sev_map = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
            severity = sev_map.get(severity.upper(), "medium")

            message = extra.get("message") or item.get("metadata", {}).get("message") or check_id
            return {
                "id": f"semgrep-{check_id}-{path}-{start}",
                "tool": "semgrep",
                "severity": severity,
                "title": check_id,
                "description": message,
                "evidence": [{"path": path, "start_line": start or 0, "snippet": extra.get("lines","")[:400]}],
                "confidence": 0.9 if severity == "high" else 0.7,
            }

        findings = []

        try:
            for item in (pylint_results or []):
                findings.append(map_pylint_to_finding(item))
        except Exception as e:
            print("⚠️ pylint mapping failed:", e)

        try:
            semg_results_list = []
            if isinstance(semgrep_results, dict) and "results" in semgrep_results:
                semg_results_list = semgrep_results.get("results", [])
            elif isinstance(semgrep_results, list):
                semg_results_list = semgrep_results
            for item in semg_results_list:
                findings.append(map_semgrep_to_finding(item))
        except Exception as e:
            print("⚠️ semgrep mapping failed:", e)

        if not findings:
            triage = {
                "findings": [
                    {
                        "id": "no-issues",
                        "severity": "low",
                        "short_reason": "No issues detected by static analyzers.",
                        "evidence": []
                    }
                ]
            }
        else:
            severity_order = {"high": 3, "medium": 2, "low": 1}
            findings_sorted = sorted(findings, key=lambda f: severity_order.get(f.get("severity", "low"), 1), reverse=True)
            triage = {"findings": findings_sorted[:25]}

        patch_resp = None  # not using LLM yet

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

