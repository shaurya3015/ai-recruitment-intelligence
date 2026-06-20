import requests

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxMCwiZW1haWwiOiJockBjb21wYW55LmNvbSIsInJvbGUiOiJ1c2VyIiwiZXhwIjoxNzgyMDIyNDE5fQ.RCUQk6jEHikldaJMpkGyULsxso2mxNzxonKiM9HiUhk"

headers = {"Authorization": f"Bearer {token}"}

try:
    # Step 1: Trigger ranking calculation
    print("📊 Triggering ranking calculation...")
    response = requests.post(
        "http://127.0.0.1:8000/admin/rank-candidates?job_title=Software%20Engineer",
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Ranked: {data.get('total_candidates')} candidates")
    print(f"\nTop candidates:")
    for candidate in data.get('ranked_candidates', [])[:5]:
        print(f"  - {candidate}")
    
except Exception as e:
    print(f"❌ Error: {e}")