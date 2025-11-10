import requests

def fetch_repo_files(repo_url, limit=5):
    if "github.com" not in repo_url:
        raise ValueError("Invalid GitHub repo URL")
    parts = repo_url.strip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
    response = requests.get(api_url)
    if response.status_code != 200:
        print("❌ GitHub API error:", response.text)
        return {}
    data = response.json()
    files = {}
    for item in data:
        if item["type"] == "file" and item["name"].endswith((".js", ".py", ".ts", ".jsx", ".tsx")):
            code = requests.get(item["download_url"]).text
            files[item["name"]] = code[:2000]
            if len(files) >= limit:
                break
    return files
