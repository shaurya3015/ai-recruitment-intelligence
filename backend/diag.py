import requests
import json
import os

BASE_URL = "http://127.0.0.1:8000"

print("1. Signing up/Logging in...")
try:
    res = requests.post(f"{BASE_URL}/auth/signup", json={"email": "test@test.com", "password": "password123", "role": "user"})
    if res.status_code == 400: # Already exists
        res = requests.post(f"{BASE_URL}/auth/login", json={"email": "test@test.com", "password": "password123"})
    token = res.json()["access_token"]
    print("Got Token successfully!")
except Exception as e:
    print("Auth failed:", str(e))
    exit(1)

print("2. Testing new chat creation...")
headers = {"Authorization": f"Bearer {token}"}
res2 = requests.post(f"{BASE_URL}/conversations", headers=headers, json={})
print("Chat creation response:", res2.status_code, res2.text)

print("3. Testing file upload...")
with open("test.txt", "w") as f:
    f.write("This is a test resume")
with open("test.txt", "rb") as f:
    res3 = requests.post(f"{BASE_URL}/upload/resume", headers=headers, files={"file": f})
print("Upload response:", res3.status_code, res3.text)

if os.path.exists("test.txt"):
    os.remove("test.txt")
