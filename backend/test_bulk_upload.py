import requests

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxMCwiZW1haWwiOiJockBjb21wYW55LmNvbSIsInJvbGUiOiJ1c2VyIiwiZXhwIjoxNzgyMDIyNDE5fQ.RCUQk6jEHikldaJMpkGyULsxso2mxNzxonKiM9HiUhk"
zip_path = r"C:\Users\Shaurya Varshney\Desktop\Codes\bulk_resumes.zip"

headers = {"Authorization": f"Bearer {token}"}

try:
    with open(zip_path, "rb") as f:
        files = {"files": f}
        response = requests.post(
            "http://127.0.0.1:8000/admin/upload/bulk",
            headers=headers,
            files=files
        )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
except FileNotFoundError:
    print(f"❌ ZIP file not found at: {zip_path}")
except Exception as e:
    print(f"❌ Error: {e}")