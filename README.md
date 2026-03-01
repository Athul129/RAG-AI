# DocChat AI (RAG_)

DocChat AI is a full-stack Retrieval-Augmented Generation (RAG) application that lets users upload PDF documents and ask grounded questions against document content.

The stack includes:
- Django + Django REST Framework (backend API)
- PostgreSQL (application database)
- ChromaDB (vector store)
- Google Gemini (embeddings + chat model)
- React + Vite (frontend)

## Features

- Upload PDF files and index them for semantic search
- Ask questions about a selected document
- Receive answers with source snippets and page references
- Persist per-document chat history
- Delete documents and associated vector data
- Track daily API usage quota (embeddings + chat)

## Project Structure

```text
RAG_/
  backend/
    ai/
      rag_engine.py
    documents/
      models.py
      serializers.py
      urls.py
      views.py
      migrations/
    rag_project/
      settings.py
      urls.py
      wsgi.py
    manage.py
    requirements.txt
    .env
    .env.example
  frontend/
    src/
      components/
        DocumentUpload.jsx
        ChatWindow.jsx
      App.jsx
      config.js
      main.jsx
      App.css
    index.html
    package.json
    vite.config.js
```

## Architecture Overview

1. User uploads a PDF from frontend.
2. Backend stores metadata in PostgreSQL and file in `backend/media/pdfs/`.
3. A background thread starts ingestion:
   - Load PDF pages
   - Chunk text
   - Generate embeddings (Gemini)
   - Store vectors in Chroma collection `document_<id>`
4. User asks questions for a processed document.
5. Backend retrieves relevant chunks, runs QA chain, returns answer + sources.
6. Q/A pairs are stored in `ChatMessage`.

## Backend API

Base path: `/api/`

- `POST /documents/upload/` - Upload a PDF
- `GET /documents/upload/` - List documents
- `POST /documents/chat/` - Ask question for a document
- `GET /documents/history/<document_id>/` - Get chat history
- `DELETE /documents/history/<document_id>/` - Clear history
- `DELETE /documents/<id>/` - Delete document + vectors + chats
- `GET /quota/` - Get daily usage summary

## Data Model

### Document
- `id`
- `title`
- `file`
- `uploaded_at`
- `is_processed`

### ChatMessage
- `id`
- `document` (FK)
- `question`
- `answer`
- `created_at`

### ApiUsage
- `id`
- `date`
- `embeddings_count`
- `chat_count`
- `total_requests` (computed)

## Environment Variables

Create/update `backend/.env`:

```env
DJANGO_SECRET_KEY=your-secret-key
DEBUG=True
GEMINI_API_KEY=your-gemini-key

DB_NAME=rag_db
DB_USER=postgres
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432

ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# RAG performance tuning (optional)
RAG_CHUNK_SIZE=3000
RAG_CHUNK_OVERLAP=300
RAG_EMBED_BATCH_SIZE=50
RAG_BATCH_DELAY_SECONDS=0
RAG_MAX_RETRIES=3
RAG_RETRY_BASE_SECONDS=2
RAG_RETRY_JITTER_SECONDS=0.5
RAG_RETRY_MAX_SECONDS=20
RAG_RETRIEVAL_K=3
RAG_CHAT_MAX_TOKENS=700
```

Frontend env (optional):

```env
VITE_API_BASE=http://localhost:8000/api
```

If not provided, frontend falls back to `http://localhost:8000/api`.

## Local Development Setup

## 1) Backend

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 8000
```

## 2) Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend default dev server runs on Vite.

## Build for Production

Frontend:

```powershell
cd frontend
npm run build
```

Output: `frontend/dist/`

Backend production baseline:
- Set `DEBUG=False`
- Configure `ALLOWED_HOSTS`
- Use secure cookies and security middleware
- Serve with a production WSGI server (for example Gunicorn/Waitress)

## Deployment Notes

Current code runs locally but needs hardening before public hosting:

- Add/enable Django security middleware:
  - `django.middleware.security.SecurityMiddleware`
  - `django.middleware.csrf.CsrfViewMiddleware`
  - `django.middleware.clickjacking.XFrameOptionsMiddleware`
- Set secure settings in production:
  - `SESSION_COOKIE_SECURE=True`
  - `CSRF_COOKIE_SECURE=True`
  - `SECURE_SSL_REDIRECT=True` (behind HTTPS)
- Replace in-process background thread ingestion with a worker queue (Celery/RQ) for reliability on hosted environments.
- Fill `backend/.env.example` with required keys.

## Important Files

- Backend settings: `backend/rag_project/settings.py`
- Backend routes: `backend/rag_project/urls.py`, `backend/documents/urls.py`
- RAG logic: `backend/ai/rag_engine.py`
- Frontend API config: `frontend/src/config.js`

## Troubleshooting

- `ModuleNotFoundError`:
  - Ensure backend is run with project venv: `backend/.venv`.
- Database errors:
  - Verify PostgreSQL is running and env credentials are correct.
- CORS errors:
  - Confirm frontend origin is listed in `CORS_ALLOWED_ORIGINS` when `DEBUG=False`.
- Gemini errors/rate limits:
  - Verify `GEMINI_API_KEY` and monitor quota via `/api/quota/`.

## License

Add your preferred license here.
