# Phase 1-3 Implementation Guide

## ✅ PHASE 1: Remove Pre-Stored Resumes

### Step 1.1: Delete Pre-Loaded Data Files

```bash
# In backend folder, run these commands:
rm parsed_resumes.json  # Delete pre-parsed resumes
rm -rf ShortlistedDS/*   # Clear these folders (optional, or keep as archive)
rm -rf RejectedDS/*
rm -rf qdrant_storage/  # Clear Qdrant database to start fresh
```

### Step 1.2: Update `main.py` - Remove Auto-Loading

In your `main.py`, find the `@app.on_event("startup")` section and replace it with:

```python
@app.on_event("startup")
def on_startup():
    database.init_db()
    print("✅ Backend started. Qdrant collections will be created per-user on demand.")
    # NO MORE AUTO-LOADING OF RESUMES!
```

---

## 🔐 PHASE 2: Add Authentication

### Step 2.1: Install Required Packages

Add these to `requirements.txt`:

```
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0  # PostgreSQL adapter
pydantic>=2.0.0
pyjwt>=2.8.0
python-jose>=3.3.0
passlib>=1.7.4
bcrypt>=4.0.0
python-multipart>=0.0.6
```

Run: `pip install -r requirements.txt`

### Step 2.2: Create User Authentication Module

Create `backend/auth.py`:

```python
import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredential

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production-!!!!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# ============ MODELS ============
class UserSignup(BaseModel):
    email: str
    password: str
    role: str = "user"  # "user" or "admin"

class UserLogin(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: int
    email: str
    role: str

# ============ UTILITY FUNCTIONS ============
def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(user_id: int, email: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(user_id: int) -> str:
    """Create JWT refresh token."""
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "user_id": user_id,
        "exp": expire,
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthCredential = Depends(security)) -> TokenData:
    """Extract and validate JWT token from request headers."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        email: str = payload.get("email")
        role: str = payload.get("role")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        return TokenData(user_id=user_id, email=email, role=role)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
```

### Step 2.3: Create Database Models (SQLAlchemy)

Create `backend/models.py`:

```python
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# PostgreSQL connection string
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
# For production: "postgresql://user:password@localhost/resume_db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============ DATABASE MODELS ============

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="user")  # "user" or "admin"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String)  # S3 path or local path
    file_size = Column(Integer)
    extracted_text = Column(Text)
    summary = Column(Text)
    embedding_generated = Column(Boolean, default=False)
    qdrant_namespace = Column(String)  # Format: "user_{user_id}"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="resumes")
    conversations = relationship("Conversation", back_populates="resume")
    scores = relationship("CandidateScore", back_populates="resume", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=True)  # Can be NULL for general chat
    title = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    resume = relationship("Resume", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String)  # "user" or "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")


class CandidateScore(Base):
    __tablename__ = "candidate_scores"
    
    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    job_title = Column(String)
    skills_match = Column(Float)
    experience_match = Column(Float)
    education_match = Column(Float)
    overall_score = Column(Float)
    rank = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    resume = relationship("Resume", back_populates="scores")


# Create all tables
def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Step 2.4: Add Authentication Endpoints to `main.py`

Add these endpoints to your FastAPI app:

```python
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from auth import (
    UserSignup, UserLogin, TokenResponse, get_current_user, TokenData,
    hash_password, verify_password, create_access_token, create_refresh_token
)
from models import User, get_db, init_db

@app.on_event("startup")
def on_startup():
    init_db()  # Initialize SQLAlchemy models
    print("✅ Backend started. User authentication enabled.")

# ============ AUTH ENDPOINTS ============

@app.post("/auth/signup", response_model=TokenResponse)
async def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    """Register a new user."""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    new_user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        role=user_data.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Generate tokens
    access_token = create_access_token(new_user.id, new_user.email, new_user.role)
    refresh_token = create_refresh_token(new_user.id)
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")

@app.post("/auth/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login user and return tokens."""
    # Find user
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate tokens
    access_token = create_access_token(user.id, user.email, user.role)
    refresh_token = create_refresh_token(user.id)
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")

@app.get("/auth/me")
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    """Get current user info."""
    return current_user
```

---

## 📦 PHASE 3: Per-User Vector Storage (Qdrant Namespaces)

### Step 3.1: Update Qdrant Usage for Namespaces

Create `backend/qdrant_manager.py`:

```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
import ollama

EMBEDDING_MODEL = "nomic-embed-text"
qdrant = QdrantClient(path="./qdrant_storage")

def get_or_create_user_collection(user_id: int):
    """Create a Qdrant namespace for each user."""
    namespace = f"user_{user_id}"
    
    try:
        # Check if collection exists
        qdrant.collection_exists(namespace)
    except:
        # Create collection if it doesn't exist
        qdrant.recreate_collection(
            collection_name=namespace,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        print(f"✅ Created Qdrant collection for user {user_id}")
    
    return namespace

def embed_and_store_resume(user_id: int, resume_id: int, text: str):
    """Generate embedding for resume and store in user's collection."""
    namespace = get_or_create_user_collection(user_id)
    
    # Generate embedding using Ollama
    try:
        response = ollama.embeddings(model=EMBEDDING_MODEL, prompt=text)
        vector = response['embedding']
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return False
    
    # Store in Qdrant
    point = PointStruct(
        id=resume_id,
        vector=vector,
        payload={
            "resume_id": resume_id,
            "text": text[:1000],  # Store first 1000 chars
            "full_text": text  # Store full text for retrieval
        }
    )
    
    qdrant.upsert(
        collection_name=namespace,
        points=[point]
    )
    print(f"✅ Resume {resume_id} stored in user {user_id}'s collection")
    return True

def search_user_resumes(user_id: int, query: str, limit: int = 5):
    """Search only within user's resume collection."""
    namespace = f"user_{user_id}"
    
    # Generate query embedding
    try:
        response = ollama.embeddings(model=EMBEDDING_MODEL, prompt=query)
        query_vector = response['embedding']
    except Exception as e:
        print(f"Error generating query embedding: {e}")
        return []
    
    # Search only in user's namespace
    try:
        results = qdrant.search(
            collection_name=namespace,
            query_vector=query_vector,
            limit=limit,
            score_threshold=0.5
        )
        return results
    except Exception as e:
        print(f"Error searching: {e}")
        return []

def delete_user_collection(user_id: int):
    """Delete user's entire collection when account is deleted."""
    namespace = f"user_{user_id}"
    try:
        qdrant.delete_collection(namespace)
        print(f"✅ Deleted collection for user {user_id}")
    except Exception as e:
        print(f"Error deleting collection: {e}")
```

### Step 3.2: Update Chat Endpoint - User Isolation

Update the chat endpoint in `main.py`:

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
        "sources": search_results
    }
```

### Step 3.3: Add Resume Upload Endpoint

```python
from fastapi import File, UploadFile
from resume_summary_generator import extract_text_from_file
from qdrant_manager import embed_and_store_resume

@app.post("/upload/resume")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User uploads their own resume."""
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

---

## 🧪 Testing the Implementation

### Test 1: User Signup
```bash
curl -X POST "http://localhost:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user1@example.com",
    "password": "secure123",
    "role": "user"
  }'
```

### Test 2: Upload Resume
```bash
curl -X POST "http://localhost:8000/upload/resume" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@resume.pdf"
```

### Test 3: Chat with Resume
```bash
curl -X POST "http://localhost:8000/chat/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "What are my key skills?"}'
```

---

## 📋 Checklist

- [ ] Phase 1: Removed pre-stored resumes
- [ ] Phase 2: PostgreSQL + SQLAlchemy + Authentication working
- [ ] Phase 3: Per-user Qdrant namespaces + User isolation working
- [ ] Test signup/login flow
- [ ] Test resume upload
- [ ] Test chat with only user's resumes visible
- [ ] Verify users cannot access other users' data

Next: Phase 4-5 (HR features) and Phase 6+ (advanced features)
