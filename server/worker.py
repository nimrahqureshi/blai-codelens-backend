import os, subprocess, json, tempfile, shutil, time
from git import Repo
from pathlib import Path
# from llm_client import triage_via_llm, patch_via_llm
from server.llm_client import triage_via_llm, patch_via_llm


def run_pylint(workdir):
    try:
        p = subprocess.run(["pylint", workdir, "-f", "json"], capture_output=True, text=True, timeout=60)
        out = p.stdout or "[]"
        return json.loads(out)
    except Exception:
        return []

def run_semgrep(workdir):
    try:
        p = subprocess.run(["semgrep", "--config", "auto", workdir, "--json"], capture_output=True, text=True, timeout=120)
        out = p.stdout or "{}"
        return json.loads(out)
    except Exception:
        return {}

async def enqueue_review(review_id, payload):
    repo_url = payload.get("repo_url")
    ref = payload.get("ref") or "HEAD"
    base_dir = tempfile.mkdtemp(prefix=f"rev_{review_id}_")
    try:
        Repo.clone_from(repo_url, base_dir, depth=1)
        pylint_results = run_pylint(base_dir)
        semgrep_results = run_semgrep(base_dir)

        static_findings = {
            "pylint": pylint_results,
            "semgrep": semgrep_results
        }

        files = []
        for p in Path(base_dir).rglob("*.py"):
            files.append({
                "path": str(p.relative_to(base_dir)),
                "snippet": p.read_text()[:2000]
            })
            if len(files) >= 8:
                break

        triage = triage_via_llm(review_id, repo_url, static_findings, files)
        patch_resp = None
        if triage and len(triage.get("findings", [])) > 0:
            top = triage["findings"][0]
            patch_resp = patch_via_llm(top, files, static_findings)

        result = {
            "review_id": review_id,
            "repo": repo_url,
            "triage": triage,
            "patch": patch_resp,
            "timestamp": time.time()
        }
        Path("artifacts").mkdir(exist_ok=True)
        Path(f"artifacts/{review_id}.json").write_text(json.dumps(result, indent=2))
        print(f"✅ Review completed: {review_id}")
    except Exception as e:
        print("❌ Error in job:", e)
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)
