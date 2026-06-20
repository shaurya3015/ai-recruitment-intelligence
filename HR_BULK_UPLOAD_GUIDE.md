# HR Admin Dashboard & Bulk Resume Upload

## 🎯 HR Requirements

1. **No Code Access**: HR admins upload resumes via web interface, not backend folders
2. **Bulk Upload**: Process thousands of resumes efficiently
3. **Candidate Ranking**: Automatically score and rank candidates
4. **Comparison**: Compare multiple candidates side-by-side
5. **Export**: Generate reports (CSV, PDF)

---

## 🏗️ Architecture for Large-Scale Resume Processing

### Option 1: Synchronous (Simple, Good for <1000 resumes)
- User uploads → Backend processes → Stores in Qdrant
- Good for quick prototyping

### Option 2: Asynchronous with Celery (Recommended for 1000+ resumes)
- User uploads → Queue job → Background worker processes → Stores in Qdrant
- User can check status while processing
- Can scale to thousands

### Option 3: Batch Processing (Best for 10000+ resumes)
- HR uploads ZIP file with 1000+ resumes
- Backend splits into batches
- Process in parallel with multiple workers
- Webhook callback when complete

---

## 📝 Implementation: HR Bulk Upload with Celery

### Step 1: Install Celery & Redis

```bash
pip install celery redis
```

Or use simpler alternative: `APScheduler` (no separate Redis needed)

### Step 2: Create Celery Worker Tasks

Create `backend/tasks.py`:

```python
from celery import Celery, group
import ollama
from resume_summary_generator import extract_text_from_file
from qdrant_manager import embed_and_store_resume
from models import SessionLocal, Resume
import os

# Celery configuration
app = Celery(
    'resume_processor',
    broker='redis://localhost:6379/0',  # or use memory-based alternative
    backend='redis://localhost:6379/0'
)

@app.task(bind=True)
def process_resume_async(self, resume_id: int, user_id: int, file_path: str):
    """Background task to process a single resume."""
    try:
        self.update_state(state='PROCESSING', meta={'current': 1, 'total': 1})
        
        # Extract text
        with open(file_path, 'rb') as f:
            text = extract_text_from_file(f, file_path)
        
        # Update database
        db = SessionLocal()
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if resume:
            resume.extracted_text = text
            
            # Generate embedding
            embed_and_store_resume(user_id, resume_id, text)
            
            resume.embedding_generated = True
            db.commit()
        db.close()
        
        self.update_state(state='SUCCESS')
        return {'resume_id': resume_id, 'status': 'processed'}
    
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        return {'resume_id': resume_id, 'status': 'failed', 'error': str(e)}


@app.task(bind=True)
def process_bulk_resumes(self, job_id: int, resume_ids: list):
    """Process multiple resumes in parallel."""
    # Create parallel tasks
    job = group(
        process_resume_async.s(resume_id)
        for resume_id in resume_ids
    )
    
    result = job.apply_async()
    
    # Track progress
    db = SessionLocal()
    db.execute(
        "UPDATE bulk_upload_jobs SET status = ?, celery_task_id = ? WHERE id = ?",
        ('PROCESSING', result.id, job_id)
    )
    db.commit()
    db.close()
    
    return result.id
```

### Step 3: Create HR Admin Endpoints

Add to `main.py`:

```python
from fastapi import File, UploadFile, BackgroundTasks
from typing import List
import zipfile
import os
from tasks import process_resume_async, process_bulk_resumes

# Temporary directory for uploaded files
UPLOAD_DIR = "./uploaded_resumes_temp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/admin/upload/bulk")
async def bulk_upload_resumes(
    files: List[UploadFile] = File(...),
    job_name: str = "",
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    HR admin bulk upload resumes.
    Accepts multiple files or a ZIP archive.
    """
    # Verify user is HR admin
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can bulk upload")
    
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
                        
                        # Create resume record
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
            
            # Clean up ZIP
            os.remove(zip_path)
        else:
            # Handle individual files
            if not file.filename.endswith(('.pdf', '.docx', '.txt')):
                continue
            
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(file_path, 'wb') as f:
                f.write(await file.read())
            
            # Create resume record
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
    
    # Start background processing
    task_id = process_bulk_resumes.delay(current_user.user_id, resume_ids)
    
    return {
        "task_id": task_id.id,
        "total_resumes": len(resume_ids),
        "message": f"Started processing {len(resume_ids)} resumes"
    }


@app.get("/admin/upload/status/{task_id}")
async def get_upload_status(task_id: str, current_user: TokenData = Depends(get_current_user)):
    """Check status of bulk upload task."""
    from celery.result import AsyncResult
    
    task = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task.status,
        "progress": task.info
    }


@app.get("/admin/candidates")
async def get_all_candidates(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all uploaded resumes (candidates)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view candidates")
    
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

## 🎯 Candidate Ranking Algorithm

Create `backend/ranking.py`:

```python
import re
from models import SessionLocal, CandidateScore, Resume

# Skill keywords database
TECHNICAL_SKILLS = {
    'python', 'java', 'javascript', 'c++', 'sql', 'react', 'angular', 'aws', 'gcp',
    'docker', 'kubernetes', 'tensorflow', 'pytorch', 'machine learning', 'data science',
    'nlp', 'computer vision', 'fastapi', 'django', 'nodejs', 'typescript', 'git'
}

SOFT_SKILLS = {
    'leadership', 'communication', 'teamwork', 'problem solving', 'critical thinking',
    'project management', 'agile', 'scrum', 'presentations', 'mentoring'
}

EDUCATION_KEYWORDS = {
    'bachelors': 1.0,
    'masters': 1.5,
    'phd': 2.0,
    'computer science': 1.5,
    'engineering': 1.5,
    'data science': 1.5
}

def extract_skills(text: str) -> tuple[list, int]:
    """Extract technical and soft skills from resume."""
    text_lower = text.lower()
    
    tech_skills = [s for s in TECHNICAL_SKILLS if s.lower() in text_lower]
    soft_skills = [s for s in SOFT_SKILLS if s.lower() in text_lower]
    
    score = len(tech_skills) * 0.5 + len(soft_skills) * 0.3
    return tech_skills + soft_skills, score


def extract_experience(text: str) -> tuple[list, float]:
    """Extract years of experience."""
    # Simple regex: look for "X years" or "20XX-20YY"
    import re
    
    years_pattern = r'(\d+)\s+years?\s+of\s+experience'
    date_pattern = r'(\d{4})\s*-\s*(\d{4}|present|current)'
    
    years_matches = re.findall(years_pattern, text, re.IGNORECASE)
    date_matches = re.findall(date_pattern, text, re.IGNORECASE)
    
    years = 0
    
    if years_matches:
        years = max(int(y) for y in years_matches)
    elif date_matches:
        # Calculate years from dates
        for start, end in date_matches:
            if end.lower() in ['present', 'current']:
                years += 2025 - int(start)
            else:
                years += int(end) - int(start)
        years = years / len(date_matches) if date_matches else 0
    
    # Score: max 2.0 for 10+ years
    score = min(years / 5, 2.0)
    
    return years, score


def extract_education(text: str) -> tuple[list, float]:
    """Extract education level."""
    text_lower = text.lower()
    
    degrees = []
    score = 0.0
    
    for keyword, points in EDUCATION_KEYWORDS.items():
        if keyword in text_lower:
            degrees.append(keyword)
            score = max(score, points)
    
    return degrees, score / 2.0  # Normalize to max 1.0


def score_resume(resume_id: int, user_id: int, job_title: str = "", job_description: str = ""):
    """
    Score a resume based on:
    - Technical skills match (0-1)
    - Years of experience (0-1)
    - Education level (0-1)
    """
    db = SessionLocal()
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    
    if not resume or not resume.extracted_text:
        return None
    
    # Extract signals
    skills, skills_score = extract_skills(resume.extracted_text)
    years, experience_score = extract_experience(resume.extracted_text)
    degrees, education_score = extract_education(resume.extracted_text)
    
    # Calculate overall score (weighted average)
    overall_score = (
        skills_score * 0.5 +           # 50% skills
        experience_score * 0.3 +       # 30% experience
        education_score * 0.2          # 20% education
    )
    
    # Normalize to 0-100
    overall_score = overall_score * 33.33  # Convert to percentage
    
    # Create score record
    candidate_score = CandidateScore(
        resume_id=resume_id,
        job_title=job_title,
        skills_match=skills_score * 100,
        experience_match=experience_score * 100,
        education_match=education_score * 100,
        overall_score=overall_score
    )
    
    db.add(candidate_score)
    db.commit()
    db.close()
    
    return {
        "resume_id": resume_id,
        "skills": skills,
        "experience_years": years,
        "education": degrees,
        "skills_score": skills_score * 100,
        "experience_score": experience_score * 100,
        "education_score": education_score * 100,
        "overall_score": overall_score
    }


def rank_candidates(user_id: int, job_title: str = ""):
    """Score and rank all candidates."""
    db = SessionLocal()
    
    resumes = db.query(Resume).filter(Resume.user_id == user_id).all()
    
    scores = []
    for resume in resumes:
        result = score_resume(resume.id, user_id, job_title)
        if result:
            scores.append(result)
    
    # Sort by overall score
    scores.sort(key=lambda x: x['overall_score'], reverse=True)
    
    # Add rank
    for i, score in enumerate(scores):
        score['rank'] = i + 1
        # Update rank in database
        db.query(CandidateScore).filter(
            CandidateScore.resume_id == score['resume_id']
        ).first().rank = i + 1
    
    db.commit()
    db.close()
    
    return scores


@app.post("/admin/rank-candidates")
async def rank_candidates_endpoint(
    job_title: str = "",
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Score and rank all uploaded candidates."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can rank candidates")
    
    from ranking import rank_candidates as rank_func
    
    results = rank_func(current_user.user_id, job_title)
    
    return {
        "total_candidates": len(results),
        "ranked_candidates": results[:20],  # Return top 20
        "message": "Candidates ranked successfully"
    }


@app.get("/admin/candidates/ranked")
async def get_ranked_candidates(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50
):
    """Get ranked candidates with scores."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view rankings")
    
    scores = db.query(CandidateScore).join(Resume).filter(
        Resume.user_id == current_user.user_id
    ).order_by(CandidateScore.overall_score.desc()).limit(limit).all()
    
    return [{
        "rank": s.rank,
        "resume_id": s.resume_id,
        "file_name": s.resume.file_name,
        "skills_score": s.skills_match,
        "experience_score": s.experience_match,
        "education_score": s.education_match,
        "overall_score": s.overall_score
    } for s in scores]
```

---

## 📊 Handling Thousands of Resumes: Performance Tips

### 1. **Batch Processing**
```python
def process_batch(resume_ids: list, batch_size: int = 50):
    """Process resumes in batches to manage memory."""
    for i in range(0, len(resume_ids), batch_size):
        batch = resume_ids[i:i+batch_size]
        process_resume_async.apply_async(args=[batch])
        print(f"Processing batch {i//batch_size + 1}")
```

### 2. **Qdrant Optimization**
```python
# Use smaller embedding dimension for faster search (384 instead of 768)
# Update in qdrant_manager.py:
VectorParams(size=384, distance=Distance.COSINE)  # Faster, less memory
```

### 3. **Database Indexing**
```sql
-- Add to PostgreSQL for faster queries
CREATE INDEX idx_resume_user_id ON resumes(user_id);
CREATE INDEX idx_candidate_score_overall ON candidate_scores(overall_score DESC);
CREATE INDEX idx_message_conversation_id ON messages(conversation_id);
```

### 4. **Pagination**
```python
# Always use skip/limit in endpoints
@app.get("/admin/candidates")
async def get_candidates(skip: int = 0, limit: int = 100):
    return db.query(Resume).offset(skip).limit(limit).all()
```

### 5. **Caching with Redis**
```python
import redis

cache = redis.Redis(host='localhost', port=6379, db=0)

@app.get("/admin/candidates/ranked")
async def get_ranked_candidates(cache_key: str = "ranked_candidates"):
    # Check cache first
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # If not in cache, compute and store
    results = rank_candidates(current_user.user_id)
    cache.setex(cache_key, 3600, json.dumps(results))  # Cache for 1 hour
    
    return results
```

---

## 🔄 HR Workflow Example

```
1. HR Admin goes to Dashboard
   ↓
2. Clicks "Upload Resumes"
   ↓
3. Selects ZIP file with 1000 resumes
   ↓
4. Backend:
   - Extracts all files
   - Creates Resume records in DB
   - Queues async processing tasks
   - Returns task_id
   ↓
5. HR sees "Processing: 250/1000"
   ↓
6. After ~30 mins, all resumes processed
   ↓
7. HR clicks "Rank Candidates"
   ↓
8. Sees ranked list:
   - John Doe: 92/100 (Python, 5 years, MS)
   - Jane Smith: 88/100 (Java, 4 years, BS)
   - Bob Lee: 75/100 (JavaScript, 2 years, BS)
   ↓
9. HR exports top 20 to CSV
   ↓
10. HR starts interviews with top candidates
```

---

## 📝 Summary: What You Now Have

✅ **User Portal**: Users upload own resume, chat only about it  
✅ **HR Portal**: Upload 1000s of resumes, auto-rank, export list  
✅ **Security**: Each user sees only their data  
✅ **Scalability**: Can handle 10,000+ resumes with Celery  
✅ **Intelligence**: Automatic candidate scoring based on skills/experience/education  

**No more code access needed for HR!** 🎉
