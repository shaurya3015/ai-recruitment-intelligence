import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from auth import (
    TokenData,
    TokenResponse,
    UserLogin,
    UserSignup,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)
from chatbot import get_ai_response
from models import CandidateScore, Conversation, Message, Resume, User, get_db, init_db
from qdrant_manager import embed_and_store_resume, search_user_resumes
from resume_summary_generator import extract_text_from_file

BACKEND_ROOT_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BACKEND_ROOT_DIR / "uploaded_resumes"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

app = FastAPI(title="Resume Chatbot API", version="4.0.0")

allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500,null").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print("Backend started. User-scoped resumes and Qdrant collections are enabled.")


def _safe_filename(filename: str) -> str:
    name = Path(filename or "resume").name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip()
    return cleaned or "resume"


def _validate_resume_filename(filename: str) -> None:
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files are allowed")


async def _save_upload(file: UploadFile, owner_id: int) -> tuple[Path, int]:
    safe_name = _safe_filename(file.filename)
    _validate_resume_filename(safe_name)

    user_dir = UPLOAD_DIR / f"user_{owner_id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    destination = user_dir / safe_name

    suffix = destination.suffix
    stem = destination.stem
    counter = 1
    while destination.exists():
        destination = user_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    size = 0
    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            output.write(chunk)

    return destination, size


def _create_resume_record(db: Session, current_user: TokenData, file_path: Path, file_size: int) -> Resume:
    text = extract_text_from_file(str(file_path))
    if not text.strip():
        raise HTTPException(status_code=400, detail=f"Could not extract text from {file_path.name}")

    resume = Resume(
        user_id=current_user.user_id,
        file_name=file_path.name,
        file_path=str(file_path),
        file_size=file_size,
        extracted_text=text,
        qdrant_namespace=f"user_{current_user.user_id}",
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    point_id = embed_and_store_resume(current_user.user_id, resume.id, text, file_path.name)
    resume.embedding_generated = point_id is not None
    resume.qdrant_point_id = point_id
    db.commit()
    db.refresh(resume)
    return resume


def _serialize_message(message: Message) -> Dict:
    return {
        "role": message.role,
        "content": message.content,
        "sources": json.loads(message.sources or "[]"),
    }


def _require_admin(current_user: TokenData) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can perform this action")


def _tokenize_search_text(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9+#.]{2,}", text.lower())
        if token not in {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "are",
            "was",
            "were",
            "you",
            "your",
            "about",
            "me",
            "my",
            "of",
            "to",
        }
    }


IDENTITY_STOPWORDS = {
    "about",
    "candidate",
    "compare",
    "experience",
    "improve",
    "interview",
    "mention",
    "questions",
    "rate",
    "resume",
    "score",
    "skill",
    "skills",
    "tell",
}


RESUME_INTENT_WORDS = {
    "candidate",
    "candidates",
    "cv",
    "education",
    "experience",
    "hire",
    "internship",
    "interview",
    "jd",
    "job",
    "project",
    "projects",
    "rank",
    "rate",
    "resume",
    "resumes",
    "score",
    "shortlist",
    "skill",
    "skills",
}


def _needs_resume_context(message: str) -> bool:
    tokens = _tokenize_search_text(message)
    if not tokens:
        return False
    return bool(tokens & RESUME_INTENT_WORDS)


def _resume_candidate_key(resume: Resume) -> str:
    text = (resume.extracted_text or "").strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    name_match = re.match(r"^[A-Za-z][A-Za-z .'-]{2,80}$", first_line)
    if name_match:
        return f"name:{re.sub(r'[^a-z0-9]+', ' ', first_line.lower()).strip()}"

    normalized_text = re.sub(r"\s+", " ", text.lower()).strip()
    if normalized_text:
        return f"text:{hashlib.sha1(normalized_text[:2000].encode('utf-8')).hexdigest()}"

    normalized_file = re.sub(r"(_\d+)?\.(pdf|docx|txt)$", "", resume.file_name.lower())
    normalized_file = re.sub(r"[^a-z0-9]+", " ", normalized_file).strip()
    return f"file:{normalized_file}"


def _dedupe_resumes_by_candidate(resumes: list[Resume]) -> list[Resume]:
    seen_keys = set()
    unique = []
    for resume in resumes:
        key = _resume_candidate_key(resume)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append(resume)
    return unique


def _find_resume_identity_matches(db: Session, user_id: int, query: str, limit: int = 5) -> list[Resume]:
    query_tokens = _tokenize_search_text(query) - IDENTITY_STOPWORDS
    if not query_tokens:
        return []

    matches = []
    resumes = db.query(Resume).filter(Resume.user_id == user_id).order_by(Resume.created_at.desc()).all()
    for resume in resumes:
        identity_text = f"{resume.file_name}\n{(resume.extracted_text or '')[:250]}"
        identity_tokens = _tokenize_search_text(identity_text)
        if query_tokens & identity_tokens:
            matches.append(resume)

    return _dedupe_resumes_by_candidate(matches)[:limit]


def _search_resumes_from_db(db: Session, user_id: int, query: str, limit: int = 5) -> list[Resume]:
    """Fallback search used when embeddings/vector search are unavailable."""
    query_tokens = _tokenize_search_text(query)
    identity_query_tokens = query_tokens - IDENTITY_STOPWORDS
    resumes = db.query(Resume).filter(Resume.user_id == user_id).all()
    if not query_tokens:
        return resumes[:limit]

    name_matches = []
    scored = []
    for resume in resumes:
        text = f"{resume.file_name}\n{resume.extracted_text or ''}"
        resume_tokens = _tokenize_search_text(text)
        identity_tokens = _tokenize_search_text(f"{resume.file_name}\n{(resume.extracted_text or '')[:250]}")
        if identity_query_tokens and identity_query_tokens & identity_tokens:
            name_matches.append(resume)
            continue

        overlap = len(query_tokens & resume_tokens)
        if overlap:
            scored.append((overlap, resume.created_at, resume))

    if name_matches:
        return _dedupe_resumes_by_candidate(name_matches)[:limit]

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return _dedupe_resumes_by_candidate([resume for _, _, resume in scored])[:limit]


def _add_resume_context(
    resume: Resume,
    sources: list[Dict],
    context_chunks: list[str],
    seen_resume_ids: set[int],
    seen_candidate_keys: set[str],
    source_kind: str,
) -> None:
    if resume.id in seen_resume_ids:
        return
    candidate_key = _resume_candidate_key(resume)
    if candidate_key in seen_candidate_keys:
        return
    seen_resume_ids.add(resume.id)
    seen_candidate_keys.add(candidate_key)
    sources.append(
        {
            "resume_id": resume.id,
            "file_name": resume.file_name,
            "folder": f"user_{resume.user_id}",
            "source": source_kind,
        }
    )
    context_chunks.append(f"[CANDIDATE {len(context_chunks) + 1}: {resume.file_name}]\n{resume.extracted_text or ''}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/auth/signup", response_model=TokenResponse)
async def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    role = user_data.role.lower().strip()
    if role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="Role must be either user or admin")

    existing_user = db.query(User).filter(User.email == user_data.email.lower()).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=user_data.email.lower(),
        password_hash=hash_password(user_data.password),
        role=role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return TokenResponse(
        access_token=create_access_token(new_user.id, new_user.email, new_user.role),
        refresh_token=create_refresh_token(new_user.id),
        token_type="bearer",
    )


@app.post("/auth/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email.lower()).first()
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return TokenResponse(
        access_token=create_access_token(user.id, user.email, user.role),
        refresh_token=create_refresh_token(user.id),
        token_type="bearer",
    )


@app.get("/auth/me")
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    return current_user


@app.get("/conversations", response_model=List[Dict])
async def get_all_conversations(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.user_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [{"id": c.id, "title": c.title or "New Conversation"} for c in conversations]


@app.post("/conversations", response_model=Dict)
async def create_new_conversation(
    resume_id: Optional[int] = Body(default=None, embed=True),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if resume_id is not None:
        resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.user_id).first()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

    conversation = Conversation(user_id=current_user.user_id, resume_id=resume_id, title="New Conversation")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {"id": conversation.id, "title": conversation.title}


@app.get("/conversations/{conversation_id}", response_model=List[Dict])
async def get_conversation_messages(
    conversation_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.user_id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return [_serialize_message(message) for message in conversation.messages]


@app.put("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: int,
    new_title: str = Body(embed=True),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not new_title.strip():
        return Response(status_code=400, content="New title cannot be empty.")

    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.user_id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.title = new_title.strip()[:255]
    db.commit()
    return {"message": "Conversation renamed successfully."}


@app.delete("/conversations/{conversation_id}")
async def remove_conversation(
    conversation_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.user_id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conversation)
    db.commit()
    return {"message": "Conversation deleted successfully."}


@app.post("/chat/{conversation_id}")
async def chat(
    conversation_id: int,
    payload: Dict = Body(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = (payload.get("message") or payload.get("content") or "").strip()
    if not message:
        return JSONResponse({"error": "Message cannot be empty"}, status_code=400)

    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.user_id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.add(Message(conversation_id=conversation_id, role="user", content=message, sources="[]"))
    if conversation.title == "New Conversation":
        conversation.title = (message[:40] + "...") if len(message) > 40 else message
    db.commit()

    sources = []
    context_chunks = []
    seen_resume_ids = set()
    seen_candidate_keys = set()
    identity_matches = _find_resume_identity_matches(db, current_user.user_id, message)
    use_resume_context = _needs_resume_context(message) or bool(identity_matches)

    if use_resume_context:
        db_matches = identity_matches or _search_resumes_from_db(db, current_user.user_id, message)
        for resume in db_matches:
            _add_resume_context(resume, sources, context_chunks, seen_resume_ids, seen_candidate_keys, "database_text")

        if not identity_matches:
            search_results = search_user_resumes(current_user.user_id, message)
            for hit in search_results:
                payload = hit.payload or {}
                resume_id = payload.get("resume_id")
                resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.user_id).first()
                if not resume:
                    continue
                if resume.id in seen_resume_ids:
                    continue
                candidate_key = _resume_candidate_key(resume)
                if candidate_key in seen_candidate_keys:
                    continue
                seen_resume_ids.add(resume.id)
                seen_candidate_keys.add(candidate_key)
                sources.append(
                    {
                        "resume_id": resume.id,
                        "file_name": resume.file_name,
                        "folder": f"user_{current_user.user_id}",
                        "source": "vector",
                    }
                )
                context_chunks.append(
                    f"[CANDIDATE {len(context_chunks) + 1}: {resume.file_name}]\n"
                    f"{payload.get('full_text') or payload.get('text') or resume.extracted_text or ''}"
                )

    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    history_str = "\n".join([f"{msg.role.capitalize()}: {msg.content}" for msg in history[-10:]])
    context = "\n\n---\n\n".join(context_chunks)
    if use_resume_context:
        prompt = f"""You are ResumeAI, a practical resume-screening assistant.

Conversation History:
{history_str}

Relevant resume context from this user's private collection:
{context}

User's latest question: "{message}"

Answer the latest question using the retrieved resume context. Give specific, useful analysis.
If the resume context is empty, say that no matching uploaded resume was found and ask for the right resume.
Do not claim a candidate is missing if their details appear in the retrieved context.
Format the answer in clear Markdown.
"""
    else:
        prompt = f"""You are ResumeAI, a helpful chatbot inside a resume-screening app.

Conversation History:
{history_str}

User's latest message: "{message}"

Respond naturally and briefly. Do not summarize resumes, mention uploaded files, or show source material unless the user asks about a resume, candidate, job description, skills, experience, education, ranking, comparison, or interview questions.
"""

    answer = get_ai_response(prompt)
    db.add(Message(conversation_id=conversation_id, role="assistant", content=answer, sources=json.dumps(sources)))
    db.commit()
    return JSONResponse(content={"answer": answer, "sources": sources})


@app.post("/upload/resume")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_path, file_size = await _save_upload(file, current_user.user_id)
    try:
        resume = _create_resume_record(db, current_user, file_path, file_size)
    except Exception:
        if file_path.exists():
            file_path.unlink()
        raise

    return {
        "resume_id": resume.id,
        "file_name": resume.file_name,
        "embedding_generated": resume.embedding_generated,
        "message": "Resume uploaded and processed successfully",
    }


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await upload_resume(file, current_user, db)


@app.get("/resumes")
async def list_resumes(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    resumes = (
        db.query(Resume)
        .filter(Resume.user_id == current_user.user_id)
        .order_by(Resume.created_at.desc())
        .offset(skip)
        .limit(min(limit, 500))
        .all()
    )
    return [
        {
            "id": resume.id,
            "file_name": resume.file_name,
            "file_size": resume.file_size,
            "created_at": resume.created_at,
            "embedding_generated": resume.embedding_generated,
        }
        for resume in resumes
    ]


@app.get("/resumes/{resume_id}/file")
async def get_resume_file(
    resume_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.user_id).first()
    if not resume or not resume.file_path:
        raise HTTPException(status_code=404, detail="Resume not found")

    path = Path(resume.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file not found")
    return FileResponse(path, filename=resume.file_name)


@app.post("/admin/upload/bulk")
async def bulk_upload_resumes(
    files: List[UploadFile] = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    created = []
    failed = []

    for file in files:
        safe_name = _safe_filename(file.filename)
        if Path(safe_name).suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory() as tmp_dir:
                zip_path = Path(tmp_dir) / safe_name
                with zip_path.open("wb") as output:
                    while chunk := await file.read(1024 * 1024):
                        output.write(chunk)

                with zipfile.ZipFile(zip_path) as archive:
                    for member in archive.infolist():
                        member_name = _safe_filename(member.filename)
                        if member.is_dir() or Path(member_name).suffix.lower() not in ALLOWED_EXTENSIONS:
                            continue
                        user_dir = UPLOAD_DIR / f"user_{current_user.user_id}"
                        user_dir.mkdir(parents=True, exist_ok=True)
                        target = user_dir / member_name
                        with archive.open(member) as source, target.open("wb") as output:
                            shutil.copyfileobj(source, output)
                        try:
                            resume = _create_resume_record(db, current_user, target, target.stat().st_size)
                            created.append({"resume_id": resume.id, "file_name": resume.file_name})
                        except Exception as exc:
                            failed.append({"file_name": member_name, "error": str(exc)})
            continue

        try:
            file_path, file_size = await _save_upload(file, current_user.user_id)
            resume = _create_resume_record(db, current_user, file_path, file_size)
            created.append({"resume_id": resume.id, "file_name": resume.file_name})
        except Exception as exc:
            failed.append({"file_name": safe_name, "error": str(exc)})

    return {
        "total_resumes": len(created),
        "created": created,
        "failed": failed,
        "message": f"Processed {len(created)} resumes",
    }


@app.get("/admin/candidates")
async def get_all_candidates(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    return await list_resumes(current_user, db, skip, limit)


@app.post("/admin/rank-candidates")
async def rank_candidates_endpoint(
    job_title: str = "",
    current_user: TokenData = Depends(get_current_user),
):
    from ranking import rank_candidates

    results = rank_candidates(current_user.user_id, job_title)
    return {
        "total_candidates": len(results),
        "ranked_candidates": results[:20],
        "message": "Candidates ranked successfully",
    }


@app.get("/admin/candidates/ranked")
async def get_ranked_candidates(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    scores = (
        db.query(CandidateScore)
        .join(Resume)
        .filter(Resume.user_id == current_user.user_id)
        .order_by(CandidateScore.overall_score.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [
        {
            "rank": score.rank,
            "resume_id": score.resume_id,
            "file_name": score.resume.file_name,
            "skills_score": score.skills_match,
            "experience_score": score.experience_match,
            "education_score": score.education_match,
            "overall_score": score.overall_score,
        }
        for score in scores
    ]


@app.get("/admin/candidates/export")
async def export_ranked_candidates(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = await get_ranked_candidates(current_user, db, limit=1000)

    def iter_csv():
        output = tempfile.SpooledTemporaryFile(mode="w+", newline="", encoding="utf-8")
        writer = csv.DictWriter(
            output,
            fieldnames=["rank", "resume_id", "file_name", "skills_score", "experience_score", "education_score", "overall_score"],
        )
        writer.writeheader()
        writer.writerows(rows)
        output.seek(0)
        yield output.read()
        output.close()

    return StreamingResponse(
        iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=candidate_rankings.csv"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
