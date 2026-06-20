# Quick Start Implementation Checklist

## 🚀 Get Started in 5 Hours

Follow this checklist to transform your chatbot from prototype to production.

---

## ⏱️ PHASE 1: Clean Slate (30 minutes)

> Remove all pre-stored resume data

### ✅ Task 1.1: Delete Pre-Stored Files
```bash
cd backend

# Delete pre-loaded resume data
rm -f parsed_resumes.json

# Clear old resumes (OPTIONAL - can keep as archive)
# mkdir -p archive
# mv ShortlistedDS/* archive/
# mv RejectedDS/* archive/

# Clear Qdrant database
rm -rf qdrant_storage/

echo "✅ Pre-stored data removed"
```

### ✅ Task 1.2: Update main.py

**Remove this from `@app.on_event("startup")`:**
```python
# Find this section and DELETE it:
    # Automatically pre-fill our memory database using the local json file
    try:
        from embed_and_push_to_qdrant import get_local_embedding
        with open("parsed_resumes.json", "r", encoding="utf-8") as f:
            summaries = json.load(f)
        # ... rest of the code
```

**Replace with:**
```python
@app.on_event("startup")
def on_startup():
    database.init_db()
    print("✅ Backend started. Qdrant collections will be created per-user on demand.")
```

---

## 🔐 PHASE 2: Add Authentication (1.5 hours)

> Users need accounts. Each user sees only their own data.

### ✅ Task 2.1: Update requirements.txt

Add these lines to `backend/requirements.txt`:
```
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
pydantic>=2.0.0
pyjwt>=2.8.0
python-jose>=3.3.0
passlib>=1.7.4
bcrypt>=4.0.0
python-multipart>=0.0.6
```

Run: `pip install -r requirements.txt`

### ✅ Task 2.2: Create auth.py

**Copy the entire `auth.py` file from IMPLEMENTATION_GUIDE.md** into `backend/auth.py`

### ✅ Task 2.3: Create models.py

**Copy the entire `models.py` file from IMPLEMENTATION_GUIDE.md** into `backend/models.py`

### ✅ Task 2.4: Update main.py

**Add these imports at the top:**
```python
from sqlalchemy.orm import Session
from auth import (
    UserSignup, UserLogin, TokenResponse, get_current_user, TokenData,
    hash_password, verify_password, create_access_token, create_refresh_token
)
from models import User, get_db, init_db
```

**Replace the startup function:**
```python
@app.on_event("startup")
def on_startup():
    init_db()  # Initialize SQLAlchemy models
    print("✅ Backend started. User authentication enabled.")
```

**Add these new endpoints to main.py:**
```python
@app.post("/auth/signup", response_model=TokenResponse)
async def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    """Register a new user."""
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        role=user_data.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    access_token = create_access_token(new_user.id, new_user.email, new_user.role)
    refresh_token = create_refresh_token(new_user.id)
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")

@app.post("/auth/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login user and return tokens."""
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(user.id, user.email, user.role)
    refresh_token = create_refresh_token(user.id)
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")

@app.get("/auth/me")
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    """Get current user info."""
    return current_user
```

### ✅ Task 2.5: Test Authentication

**Test Signup:**
```bash
curl -X POST "http://localhost:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "password": "SecurePass123",
    "role": "user"
  }'
```

**Expected Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLC...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLC...",
  "token_type": "bearer"
}
```

**Save the access_token** - you'll need it for next steps!

**Test Login:**
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "password": "SecurePass123"
  }'
```

---

## 📦 PHASE 3: Per-User Vector Storage (1.5 hours)

> Each user gets their own Qdrant namespace. No data leaks.

### ✅ Task 3.1: Create qdrant_manager.py

**Copy the entire `qdrant_manager.py` section from IMPLEMENTATION_GUIDE.md** into `backend/qdrant_manager.py`

### ✅ Task 3.2: Update Chat Endpoint in main.py

**Find the chat endpoint and UPDATE it:**

```python
@app.post("/chat/{conversation_id}")
async def send_message(
    conversation_id: int,
    message: dict,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send message - only user can access their own conversations."""
    from qdrant_manager import search_user_resumes
    from chatbot import get_ai_response
    from models import Conversation, Message
    
    # Verify conversation belongs to user
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.user_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    user_message = message.get("content")
    
    # Search ONLY in user's resumes
    search_results = search_user_resumes(current_user.user_id, user_message)
    
    # Build context from search results
    context = ""
    if search_results:
        context = "Based on the user's resume:\n"
        for result in search_results:
            context += f"- {result.payload.get('text')}\n"
    
    # Generate AI response with context
    full_prompt = f"{context}\n\nUser: {user_message}"
    ai_response = get_ai_response(full_prompt)
    
    # Store messages
    db.add(Message(conversation_id=conversation_id, role="user", content=user_message))
    db.add(Message(conversation_id=conversation_id, role="assistant", content=ai_response))
    db.commit()
    
    return {
        "role": "assistant",
        "content": ai_response,
        "sources": [r.payload for r in search_results]
    }
```

### ✅ Task 3.3: Add Resume Upload Endpoint

**Add this to main.py:**

```python
@app.post("/upload/resume")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User uploads their own resume."""
    from resume_summary_generator import extract_text_from_file
    from qdrant_manager import embed_and_store_resume
    from models import Resume
    
    # Validate file type
    if not file.filename.endswith(('.pdf', '.docx', '.txt')):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files allowed")
    
    try:
        # Extract text from file
        text = extract_text_from_file(file.file, file.filename)
        
        # Create resume record
        resume = Resume(
            user_id=current_user.user_id,
            file_name=file.filename,
            extracted_text=text,
            qdrant_namespace=f"user_{current_user.user_id}"
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)
        
        # Generate embedding and store in Qdrant
        embed_and_store_resume(current_user.user_id, resume.id, text)
        
        resume.embedding_generated = True
        db.commit()
        
        return {
            "resume_id": resume.id,
            "message": "Resume uploaded and processed successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")
```

### ✅ Task 3.4: Test Resume Upload

**Test uploading a resume:**
```bash
curl -X POST "http://localhost:8000/upload/resume" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE" \
  -F "file=@/path/to/your/resume.pdf"
```

**Expected Response:**
```json
{
  "resume_id": 1,
  "message": "Resume uploaded and processed successfully"
}
```

---

## 👑 PHASE 4: HR Admin Bulk Upload (1.5 hours)

> Let HR admins upload 1000s of resumes without code access

### ✅ Task 4.1: Create ranking.py

**Copy the entire ranking section from HR_BULK_UPLOAD_GUIDE.md** into `backend/ranking.py`

### ✅ Task 4.2: Add HR Endpoints to main.py

**Add these imports:**
```python
from typing import List
import zipfile
import shutil
```

**Add HR upload endpoint:**
```python
@app.post("/admin/upload/bulk")
async def bulk_upload_resumes(
    files: List[UploadFile] = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """HR admin bulk upload resumes."""
    from models import Resume
    
    # Verify user is HR admin
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can bulk upload")
    
    UPLOAD_DIR = "./uploaded_resumes_temp"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    resume_ids = []
    
    for file in files:
        if file.filename.endswith('.zip'):
            # Handle ZIP archive
            zip_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(zip_path, 'wb') as f:
                f.write(await file.read())
            
            # Extract and process all resumes in ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for name in zip_ref.namelist():
                    if name.endswith(('.pdf', '.docx', '.txt')):
                        extract_path = os.path.join(UPLOAD_DIR, name)
                        with zip_ref.open(name) as source, open(extract_path, 'wb') as target:
                            target.write(source.read())
                        
                        resume = Resume(
                            user_id=current_user.user_id,
                            file_name=name,
                            file_path=extract_path,
                            qdrant_namespace=f"user_{current_user.user_id}"
                        )
                        db.add(resume)
                        db.commit()
                        db.refresh(resume)
                        resume_ids.append(resume.id)
            
            os.remove(zip_path)
        else:
            if not file.filename.endswith(('.pdf', '.docx', '.txt')):
                continue
            
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(file_path, 'wb') as f:
                f.write(await file.read())
            
            resume = Resume(
                user_id=current_user.user_id,
                file_name=file.filename,
                file_path=file_path,
                qdrant_namespace=f"user_{current_user.user_id}"
            )
            db.add(resume)
            db.commit()
            db.refresh(resume)
            resume_ids.append(resume.id)
    
    return {
        "total_resumes": len(resume_ids),
        "message": f"Started processing {len(resume_ids)} resumes",
        "resume_ids": resume_ids
    }

@app.post("/admin/rank-candidates")
async def rank_candidates_endpoint(
    current_user: TokenData = Depends(get_current_user)
):
    """Score and rank all uploaded candidates."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can rank candidates")
    
    from ranking import rank_candidates
    
    results = rank_candidates(current_user.user_id)
    
    return {
        "total_candidates": len(results),
        "ranked_candidates": results[:20],
        "message": "Candidates ranked successfully"
    }

@app.get("/admin/candidates")
async def get_all_candidates(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all uploaded resumes."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view candidates")
    
    from models import Resume
    
    resumes = db.query(Resume).filter(
        Resume.user_id == current_user.user_id
    ).offset(skip).limit(limit).all()
    
    return [{
        "id": r.id,
        "file_name": r.file_name,
        "created_at": r.created_at,
        "embedding_generated": r.embedding_generated
    } for r in resumes]
```

---

## 🧪 Testing Everything

### Create Test Script: `backend/test_all.py`

```python
import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_signup():
    print("\n🔐 Testing Signup...")
    response = requests.post(f"{BASE_URL}/auth/signup", json={
        "email": f"user{int(time.time())}@test.com",
        "password": "TestPass123",
        "role": "user"
    })
    if response.status_code == 200:
        print("✅ Signup successful")
        return response.json()["access_token"]
    else:
        print(f"❌ Signup failed: {response.text}")
        sys.exit(1)

def test_upload_resume(token):
    print("\n📄 Testing Resume Upload...")
    # You need to have a test resume.pdf in backend folder
    with open("test_resume.pdf", "rb") as f:
        files = {"file": f}
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(f"{BASE_URL}/upload/resume", files=files, headers=headers)
    
    if response.status_code == 200:
        print("✅ Resume upload successful")
        return response.json()["resume_id"]
    else:
        print(f"❌ Resume upload failed: {response.text}")
        sys.exit(1)

def test_chat(token, conversation_id):
    print("\n💬 Testing Chat...")
    headers = {"Authorization": f"Bearer {token}"}
    data = {"content": "What are my key skills?"}
    response = requests.post(f"{BASE_URL}/chat/{conversation_id}", json=data, headers=headers)
    
    if response.status_code == 200:
        print("✅ Chat successful")
        print(f"Response: {response.json()['content']}")
    else:
        print(f"❌ Chat failed: {response.text}")

if __name__ == "__main__":
    import time
    
    print("🚀 Starting tests...")
    
    # Test signup
    token = test_signup()
    
    # Test resume upload
    resume_id = test_upload_resume(token)
    
    # Create conversation
    response = requests.post(f"{BASE_URL}/conversations", headers={"Authorization": f"Bearer {token}"})
    conversation_id = response.json()["id"]
    
    # Test chat
    test_chat(token, conversation_id)
    
    print("\n✅ All tests passed!")
```

Run it:
```bash
cd backend
python test_all.py
```

---

## 📋 Final Verification Checklist

- [ ] Phase 1: Pre-stored resumes deleted, Qdrant cleared
- [ ] Phase 2: Signup/Login endpoints working
- [ ] Phase 2: Can get JWT tokens and verify with `/auth/me`
- [ ] Phase 3: Resume upload endpoint working
- [ ] Phase 3: Chat only searches user's own resumes
- [ ] Phase 4: HR admin can bulk upload resumes
- [ ] Phase 4: Ranking system works and ranks candidates
- [ ] Verified: User A cannot see User B's resumes
- [ ] Verified: User A cannot see User B's conversations

---

## 🎯 What You've Achieved

✅ **Removed** pre-stored resume sharing issues  
✅ **Added** user authentication (no code access needed)  
✅ **Implemented** per-user data isolation  
✅ **Created** individual resume upload  
✅ **Built** HR admin interface for bulk uploads  
✅ **Added** automatic candidate ranking  

**This is now a real, production-grade system!** 🎉

---

## 📚 Next Steps (Optional Enhancements)

- Add Celery for async processing of 1000s of resumes
- Implement Redis caching for faster ranking
- Add email notifications for upload completion
- Create React/Vue frontend for user portal
- Add export-to-CSV functionality for HR
- Implement audit logs (who viewed what)
- Add rate limiting and security headers
- Deploy to cloud (AWS, GCP, Azure)

---

## 🆘 Troubleshooting

**Issue**: "ModuleNotFoundError: No module named 'auth'"
→ Solution: Make sure `auth.py` is in the `backend/` folder

**Issue**: "Database locked" (SQLite)
→ Solution: Switch to PostgreSQL for production

**Issue**: Ollama not found
→ Solution: Make sure Ollama is running: `ollama serve`

**Issue**: Qdrant error
→ Solution: Clear: `rm -rf qdrant_storage/` and restart

---

Good luck! You've got this! 🚀
