import requests

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxMCwiZW1haWwiOiJockBjb21wYW55LmNvbSIsInJvbGUiOiJ1c2VyIiwiZXhwIjoxNzgyMDIyNDE5fQ.RCUQk6jEHikldaJMpkGyULsxso2mxNzxonKiM9HiUhk"

headers = {"Authorization": f"Bearer {token}"}

try:
    response = requests.get(
        "http://127.0.0.1:8000/admin/candidates/ranked",
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    data = response.json()
    print("\nRanked Candidates:")
    print(data)
    
except Exception as e:
    print(f"❌ Error: {e}")