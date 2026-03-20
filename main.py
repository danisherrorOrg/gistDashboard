def fetch_gists(username, token=None):
    import requests

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10"
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/users/{username}/gists"
    return requests.get(url, headers=headers).json()

def fetch_commits(username, token=None):
    import requests

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10"
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/gists/22df59de9dfb3e5b2241b7bb5f8c626e/commits"
    return requests.get(url, headers=headers).json()
print(fetch_commits("danisherror"))