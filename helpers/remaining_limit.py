import os
import requests
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Get token
token = os.getenv("GITHUB_TOKEN")

url = "https://api.github.com/rate_limit"

headers = {
    "Authorization": f"Bearer {token}",
    "X-GitHub-Api-Version": "2022-11-28"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    print(response.json())
else:
    print("Error:", response.status_code, response.text)