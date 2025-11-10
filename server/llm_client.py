import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load .env so your API key is available
load_dotenv()
print("🔑 Loaded OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def triage_via_llm(review_id, repo_url, static_findings, files):
    """
    Analyze repo using OpenAI GPT model and produce structured findings.
    """
    prompt = f"""
You are a senior AI code reviewer named BLAI CodeLens.
Repo: {repo_url}

Static findings: {json.dumps(static_findings)[:4000]}
Files snippets: {json.dumps(files)[:4000]}

Task: Return JSON with 3–5 key code review findings.
Each finding must include:
  - id (short string)
  - severity (low/medium/high)
  - title
  - reason (why it's a problem)
  - evidence (file + line context)
  - recommendation (how to fix)
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise, senior code reviewer. Output ONLY valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        print("❌ Error in triage_via_llm:", e)
        return {"findings": [{"id": "error", "title": str(e)}]}


def patch_via_llm(finding, files, static_findings):
    """
    Ask the model to propose a patch or fix for one finding.
    """
    prompt = f"""
You are an expert Python developer.
Based on this finding: {json.dumps(finding)}
and file context: {json.dumps(files)[:2000]},
produce a minimal patch (diff format) that fixes the issue.
Then output ===TEST=== followed by a small test verifying the fix.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Output plain text diff and test, separated by ===TEST===",
                },
                {"role": "user", "content": prompt},
            ],
        )

        content = response.choices[0].message.content
        parts = content.split("===TEST===")
        return {
            "diff": parts[0].strip(),
            "test": parts[1].strip() if len(parts) > 1 else "",
        }

    except Exception as e:
        print("❌ Error in patch_via_llm:", e)
        return {"diff": "", "test": "", "error": str(e)}

