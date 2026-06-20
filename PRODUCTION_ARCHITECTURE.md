# Resume Chatbot - Production Architecture

## 🎯 Project Goals

### For Individual Users:
1. Upload their own resume
2. Chat only about THEIR resume (not others)
3. Get insights from their resume via AI

### For HR Admins:
1. Bulk upload thousands of resumes
2. No code access needed - web interface only
3. Automatically rank and compare candidates
4. Select best candidates based on criteria

---

## 🗂️ Current Issues (To Fix)

❌ **Issue 1**: Pre-loaded resumes in `parsed_resumes.json`  
→ **Solution**: Delete this file, load resumes dynamically per user

❌ **Issue 2**: Single shared Qdrant collection for all resumes  
→ **Solution**: Use Qdrant namespaces per user

❌ **Issue 3**: Users can access any resume in system  
→ **Solution**: Add JWT authentication & filter queries by user_id

❌ **Issue 4**: HR must manually add files to backend folders  
→ **Solution**: Create web-based resume upload interface

❌ **Issue 5**: No ranking/comparison system for candidates  
→ **Solution**: Add scoring algorithm to rank resumes

---

## 🏗️ New Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (React/Vue)                     │
├──────────────────────────────────────────────────────────────┤
│  User Portal          │         HR Admin Dashboard           │
│  - Upload Resume      │  - Bulk Upload                       │
│  - Ask Questions      │  - View Candidates                   │
│  - Chat History       │  - Compare Candidates                │
│                       │  - Export Rankings                   │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/WebSocket
┌──────────────────────▼──────────────────────────────────────┐
│              FastAPI Backend + Middleware                    │
├──────────────────────────────────────────────────────────────┤
│  1. JWT Authentication   - validate user identity            │
│  2. User Isolation       - filter by user_id                 │
│  3. Rate Limiting        - prevent abuse                     │
│  4. Resume Parsing       - extract text from PDFs            │
│  5. Embedding Generation - create vectors via Ollama         │
│  6. Vector Search        - query Qdrant within namespace     │
│  7. AI Chat              - Qwen3 responses                   │
│  8. Ranking Algorithm    - score candidates                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
    ┌───▼────┐   ┌────▼────┐   ┌───▼──────────┐
    │Qdrant  │   │PostgreSQL   │  S3/MinIO    │
    │(Vectors)   │(Metadata)   │  (PDF Files) │
    └────────┘   └───────────┘   └────────────┘
```

---

## 📋 Implementation Roadmap

### Phase 1: Remove Pre-Stored Data ✅ (First)
- [ ] Delete `parsed_resumes.json`
- [ ] Clear Qdrant collection
- [ ] Clear `ShortlistedDS/` and `RejectedDS/` folders

### Phase 2: Add Authentication (High Priority)
- [ ] Setup PostgreSQL database
- [ ] Add User table (id, email, password_hash, role)
- [ ] Implement JWT token generation
- [ ] Create `/auth/register` endpoint
- [ ] Create `/auth/login` endpoint
- [ ] Add auth middleware to FastAPI

### Phase 3: Per-User Vector Storage (High Priority)
- [ ] Use Qdrant namespaces: `user_{user_id}`
- [ ] Modify embedding pipeline to include user_id
- [ ] Update search to query only user's namespace
- [ ] Add cleanup for deleted users

### Phase 4: Resume Upload & Processing (High Priority)
- [ ] Create `/upload/resume` endpoint for users
- [ ] Create `/admin/upload/bulk` endpoint for HR
- [ ] Add file validation (PDF, DOCX, etc.)
- [ ] Process resume asynchronously (Celery/RQ)
- [ ] Extract text, create embeddings, store in Qdrant

### Phase 5: User Isolation in Chat (High Priority)
- [ ] Modify chat endpoint to require user_id (from JWT)
- [ ] Filter Qdrant search to user's namespace only
- [ ] Prevent users from seeing other people's resumes

### Phase 6: HR Admin Features (Medium Priority)
- [ ] Create `/admin/candidates` endpoint - list all uploaded resumes
- [ ] Add resume ranking algorithm (skills match, experience, etc.)
- [ ] Create `/admin/compare` endpoint - compare multiple resumes
- [ ] Export candidates to CSV/JSON

### Phase 7: Frontend Updates (Medium Priority)
- [ ] Add login/signup pages
- [ ] Create user portal (upload resume, chat)
- [ ] Create HR dashboard (bulk upload, rankings)
- [ ] Add file upload UI with progress bar

### Phase 8: Optimizations (Low Priority)
- [ ] Caching layer (Redis)
- [ ] Rate limiting per user
- [ ] Audit logs (who viewed what)
- [ ] Notification system

---

## 🔐 Security Considerations

1. **JWT Tokens**: Use short-lived tokens (15 min) + refresh tokens (7 days)
2. **API Keys**: For admin operations, use API keys instead of JWT
3. **Input Validation**: Sanitize all file uploads, prevent code injection
4. **Data Privacy**: Encrypt resume data, ensure users can only access their own
5. **CORS**: Restrict to your domain only (not `["*"]`)
6. **Rate Limiting**: Prevent brute force attacks

---

## 📊 Database Schema (PostgreSQL)

```sql
-- Users Table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',  -- 'user' or 'admin'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Resumes Table
CREATE TABLE resumes (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    file_name VARCHAR(255),
    file_path VARCHAR(255),
    file_size INT,
    extracted_text TEXT,
    summary TEXT,
    embedding_generated BOOLEAN DEFAULT FALSE,
    qdrant_namespace VARCHAR(50),  -- user_{user_id}
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Conversations Table
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    resume_id INT REFERENCES resumes(id) ON DELETE CASCADE,
    title VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Messages Table
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    conversation_id INT REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(50),  -- 'user' or 'assistant'
    content TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Candidate Scores (for HR ranking)
CREATE TABLE candidate_scores (
    id SERIAL PRIMARY KEY,
    resume_id INT REFERENCES resumes(id) ON DELETE CASCADE,
    job_title VARCHAR(255),
    skills_match FLOAT,
    experience_match FLOAT,
    education_match FLOAT,
    overall_score FLOAT,
    rank INT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🚀 Deployment Considerations

### For Thousands of Resumes:
1. **Async Processing**: Use Celery/RQ for background embedding generation
2. **Batch Uploads**: Process 100s of resumes in parallel
3. **Vector DB Scaling**: Qdrant can handle millions of vectors
4. **File Storage**: Use S3/MinIO instead of local filesystem
5. **Load Balancing**: Multiple FastAPI instances behind Nginx
6. **Caching**: Redis for frequently accessed resumes

### Cost Optimization:
- Local Ollama (self-hosted) vs API calls - **use local** for cost savings
- Qdrant file-based (local) vs Qdrant Cloud - **use local** initially
- PostgreSQL (local) vs managed DB - **use managed DB** for production

---

## 📝 Next Steps

1. **Start with Phase 1**: Delete pre-stored resumes
2. **Move to Phase 2**: Add authentication (PostgreSQL + JWT)
3. **Then Phase 3**: Implement per-user vector storage
4. **Test each phase** before moving to next
5. **Deploy to production** once Phase 5 is complete

---

## 📚 Resources & Tools

- **FastAPI Auth**: https://fastapi.tiangolo.com/advanced/security/
- **JWT in Python**: PyJWT library
- **Qdrant Namespaces**: https://qdrant.tech/documentation/concepts/namespaces/
- **Async Tasks**: Celery (complex) or APScheduler (simple)
- **PDF Parsing**: PyPDF2, pdfplumber, or textract
- **File Upload**: python-multipart

---

Generated: 2025 | Resume AI Chatbot Production Architecture
