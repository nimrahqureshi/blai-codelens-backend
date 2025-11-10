import requests

def fetch_repo_files(repo_url, limit=5):
    """
    Fetch a few readable source files from a GitHub repo (like .py, .js, .tsx, etc.)
    """
    try:
        # Convert normal GitHub URL → API URL
        if "github.com" not in repo_url:
            raise ValueError("Invalid GitHub repo URL")
        
        parts = repo_url.strip("/").split("/")
        owner, repo = parts[-2], parts[-1]
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
        
        headers = {}
        # Optional: support a GITHUB_TOKEN environment variable (set later in Koyeb/Render) to avoid rate limits
        import os
        if os.getenv("GITHUB_TOKEN"):
            headers["Authorization"] = f'token {os.getenv("GITHUB_TOKEN")}'

        response = requests.get(api_url, headers=headers, timeout=15)
        if response.status_code != 200:
            print("❌ GitHub API error:", response.status_code, response.text)
            return {}

        data = response.json()
        files = {}

        for item in data:
            if item.get("type") == "file" and item.get("name", "").endswith((".js", ".py", ".ts", ".jsx", ".tsx")):
                # fetch file content
                file_resp = requests.get(item.get("download_url"), headers=headers, timeout=15)
                if file_resp.status_code == 200:
                    code = file_resp.text
                    files[item["name"]] = code[:2000]  # limit snippet length
                    if len(files) >= limit:
                        break
        return files
    except Exception as e:
        print("⚠️ Error fetching repo files:", e)
        return {}

