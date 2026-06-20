import requests
import json
import os

BASE_URL = "http://127.0.0.1:8000"

print("1. Signing up/Logging in...")
try:
    res = requests.post(f"{BASE_URL}/auth/signup", json={"email": "test2@test.com", "password": "password123", "role": "user"})
    if res.status_code == 400: # Already exists
        res = requests.post(f"{BASE_URL}/auth/login", json={"email": "test2@test.com", "password": "password123"})
    token = res.json()["access_token"]
except Exception as e:
    print("Auth failed:", str(e))
    exit(1)

headers = {"Authorization": f"Bearer {token}"}
res2 = requests.post(f"{BASE_URL}/conversations", headers=headers, json={})
chat_id = res2.json()["id"]

print("2. Uploading test resume...")
with open("test2.txt", "w") as f:
    f.write("Shaurya Varshney is a great software engineer who loves AI and coding in Python.")
with open("test2.txt", "rb") as f:
    res3 = requests.post(f"{BASE_URL}/upload/resume", headers=headers, files={"file": f})
print("Upload:", res3.status_code)

print("3. Testing chat search logic...")
res4 = requests.post(f"{BASE_URL}/chat/{chat_id}", headers=headers, json={"message": "Who is Shaurya Varshney?"})
print("Chat Response:", res4.status_code, res4.text)

if os.path.exists("test2.txt"):
    os.remove("test2.txt")
