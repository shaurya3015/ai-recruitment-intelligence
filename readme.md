# Resume AI Chatbot
A locally-running RAG-based resume screening system for HR workflows.
Upload resumes, ask natural language questions, and get ranked candidates.

## Features
- PDF/DOCX/TXT resume upload with per-user isolation
- Semantic search via Qdrant vector store
- Chat interface powered by Ollama (neural-chat:7b) — runs fully local
- JWT authentication (signup/login/refresh)
- Candidate ranking with skill extraction scoring
- Bulk upload support
- Clean HTML/JS frontend — no framework required

## Tech Stack
FastAPI · SQLite (SQLAlchemy) · Qdrant · Ollama (neural-chat:7b) · JWT · Python 3.11+

## Architecture

┌─────────────────────────────────────────────────────────┐

│         RESUME AI CHATBOT - SYSTEM ARCHITECTURE         │

└─────────────────────────────────────────────────────────┘
CLIENT LAYER:

┌──────────────────────┐

│   Frontend (HTML/JS) │

│   - Resume Upload UI │

│   - Chat Interface   │

│   - Results Display  │

└──────────┬───────────┘

│ REST API

▼

BACKEND LAYER:

┌──────────────────────────────────────────────┐

│         FastAPI Backend (main.py)            │

├──────────────────────────────────────────────┤

│  • Authentication (JWT tokens)               │

│  • Resume Upload & Storage                   │

│  • Chat Message Processing                   │

│  • Search & Ranking Logic                    │

└──────────┬──────────────┬──────────┬─────────┘

│              │          │

┌──────▼──┐    ┌──────▼──┐   ┌──▼───────┐

│ Database │    │ Qdrant  │   │  Ollama  │

│ (SQLite) │    │ Vector  │   │neural-   │

│          │    │  Store  │   │chat:7b   │

└──────────┘    └─────────┘   └──────────┘
DATA FLOW:

1.User uploads resume → Saved to database
2.Text extracted → Converted to embeddings
3.Embeddings stored in Qdrant vector DB
4.User asks question → Semantic search in Qdrant
5.Results sent to Ollama → Generated response
6.Response returned to user

## Setup
1. Install and start Qdrant locally (Docker recommended):
```bash
   docker run -p 6333:6333 qdrant/qdrant
```
2. Install and start Ollama, then pull the model:
```bash
   ollama pull neural-chat:7b
```
3. Install dependencies:
```bash
   pip install -r backend/requirements.txt
```
4. Start the backend:
```bash
   uvicorn backend.main:app --reload
```
5. Open `frontend/index.html` with Live Server (VS Code) or any static file server

## Project Structure

resume-ai-chatbot/

├── backend/

│   ├── main.py                  # FastAPI app, all routes

│   ├── auth.py                  # JWT auth logic

│   ├── models.py                # SQLAlchemy models

│   ├── chatbot.py               # Ollama chat integration

│   ├── qdrant_manager.py        # Vector store operations

│   ├── ranking.py               # Candidate scoring

│   ├── resume_summary_generator.py

│   └── requirements.txt

└── frontend/

├── index.html

└── app.js

## Notes
- All data stays local — no cloud APIs, no external calls
- Resumes stored per-user under `uploaded_resumes/user_{id}/`
- Qdrant collections are scoped per user for isolation