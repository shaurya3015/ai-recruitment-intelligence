## Architecture

``````
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
    │ Database │    │ Qdrant  │   │ Gemini   │
    │ (SQLite) │    │ Vector  │   │ API      │
    │          │    │  Store  │   │(Chat LLM)│
    └──────────┘    └─────────┘   └──────────┘
    
DATA FLOW:
1. User uploads resume → Saved to database
2. Text extracted → Converted to embeddings
3. Embeddings stored in Qdrant vector DB
4. User asks question → Semantic search in Qdrant
5. Results sent to Gemini → Generated response
6. Response returned to user