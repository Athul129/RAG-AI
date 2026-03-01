import logging
import os
import random
import time
from pathlib import Path

from django.conf import settings

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate

from django.utils import timezone

from documents.models import ApiUsage

logger = logging.getLogger(__name__)

def increment_usage(usage_type: str, amount: int = 1):
    """Increment the API usage counter for today."""
    try:
        usage, _ = ApiUsage.objects.get_or_create(date=timezone.now().date())
        if usage_type == "embeddings":
            usage.embeddings_count += amount
        elif usage_type == "chat":
            usage.chat_count += amount
        usage.save()
    except Exception as e:
        logger.error("Failed to increment API usage: %s", e)

CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "3000"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "300"))
EMBEDDING_MODEL = "models/gemini-embedding-001"
CHAT_MODEL = os.getenv("RAG_CHAT_MODEL", "gemini-1.5-flash")
RETRIEVAL_K = int(os.getenv("RAG_RETRIEVAL_K", "3"))
BATCH_SIZE = int(os.getenv("RAG_EMBED_BATCH_SIZE", "50"))
DELAY_BETWEEN_BATCHES = float(os.getenv("RAG_BATCH_DELAY_SECONDS", "0"))
MAX_RETRIES = int(os.getenv("RAG_MAX_RETRIES", "3"))
RETRY_BASE_SECONDS = float(os.getenv("RAG_RETRY_BASE_SECONDS", "2"))
RETRY_JITTER_SECONDS = float(os.getenv("RAG_RETRY_JITTER_SECONDS", "0.5"))
RETRY_MAX_SECONDS = float(os.getenv("RAG_RETRY_MAX_SECONDS", "20"))
CHAT_MAX_TOKENS = int(os.getenv("RAG_CHAT_MAX_TOKENS", "700"))

QA_PROMPT_TEMPLATE = """You are a helpful AI assistant. Answer ONLY using the context below. Be concise and use Markdown formatting (bold, lists, backticks for code).

Context:
{context}

Question: {question}

Answer:"""


def _collection_name(document_id: int) -> str:
    return f"document_{document_id}"


def _chroma_dir() -> str:
    persist_dir = getattr(settings, "CHROMA_PERSIST_DIR", "/tmp/chroma_db")
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    return persist_dir


# ── Module-level singletons (created once, reused on every request) ───────────
_embedding_client = None
_llm_client = None
_vector_store_cache: dict = {}  # {document_id: Chroma instance}


def _embeddings():
    """Return a cached GoogleGenerativeAIEmbeddings instance."""
    global _embedding_client
    if _embedding_client is None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")
        _embedding_client = GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )
        logger.info("Embedding client initialised (cached).")
    return _embedding_client


def _llm():
    """Return a cached ChatGoogleGenerativeAI instance."""
    global _llm_client
    if _llm_client is None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")
        _llm_client = ChatGoogleGenerativeAI(
            model=CHAT_MODEL,
            temperature=0,
            max_output_tokens=CHAT_MAX_TOKENS,
            google_api_key=settings.GEMINI_API_KEY,
        )
        logger.info("LLM client initialised (cached).")
    return _llm_client


def _get_vector_store(document_id: int) -> Chroma:
    """Return a cached Chroma instance for the given document_id."""
    if document_id not in _vector_store_cache:
        _vector_store_cache[document_id] = Chroma(
            collection_name=_collection_name(document_id),
            embedding_function=_embeddings(),
            persist_directory=_chroma_dir(),
        )
        logger.info("Vector store for document %s opened (cached).", document_id)
    return _vector_store_cache[document_id]


def ingest_document(document_id: int, pdf_path: str) -> int:
    logger.info("Ingesting document %s from %s", document_id, pdf_path)

    loader = PyPDFLoader(pdf_path)
    pages = loader.load()
    logger.info("Loaded %d pages", len(pages))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    chunks = splitter.split_documents(pages)
    num_chunks = len(chunks)
    logger.info("Split into %d chunks", num_chunks)

    persist_dir = _chroma_dir()
    collection_name = _collection_name(document_id)
    embedding_fn = _embeddings()

    # Create/Get vector store
    vector_store = Chroma(
        collection_name=collection_name,
        embedding_function=embedding_fn,
        persist_directory=persist_dir,
    )

    for i in range(0, num_chunks, BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        logger.info("Processing batch %d/%d (%d chunks)", 
                    (i // BATCH_SIZE) + 1, (num_chunks + BATCH_SIZE - 1) // BATCH_SIZE, len(batch))
        
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                vector_store.add_documents(batch)
                increment_usage("embeddings", 1) # Each batch is one request
                break  # Success
            except Exception as e:
                # Check if it's a rate limit error (429)
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    retry_count += 1
                    # Exponential backoff with jitter
                    wait_time = min(
                        RETRY_MAX_SECONDS,
                        (RETRY_BASE_SECONDS * (2 ** (retry_count - 1))) + random.uniform(0, RETRY_JITTER_SECONDS),
                    )
                    logger.warning("Rate limit hit. Retrying batch in %.2f seconds (Attempt %d/%d)...", 
                                   wait_time, retry_count, MAX_RETRIES)
                    time.sleep(wait_time)
                else:
                    logger.error("Failed to add batch to vector store: %s", e)
                    raise e
        else:
            raise Exception(f"Failed to ingest batch after {MAX_RETRIES} retries due to rate limits.")

        if i + BATCH_SIZE < num_chunks:
            logger.info("Waiting %d seconds before next batch...", DELAY_BETWEEN_BATCHES)
            time.sleep(DELAY_BETWEEN_BATCHES)

    logger.info("Document %s ingested successfully", document_id)
    return num_chunks


def answer_question(document_id: int, question: str) -> dict:
    # Reuse cached vector store, embeddings, and LLM — no cold-start overhead
    retriever = _get_vector_store(document_id).as_retriever(
        search_type="similarity",
        search_kwargs={"k": RETRIEVAL_K},
    )

    prompt = PromptTemplate(
        template=QA_PROMPT_TEMPLATE,
        input_variables=["context", "question"],
    )

    qa_chain = RetrievalQA.from_chain_type(
        llm=_llm(),
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    result = qa_chain.invoke({"query": question})
    increment_usage("chat", 1)

    sources = [
        {
            "page": doc.metadata.get("page", "?"),
            "snippet": doc.page_content[:200].strip(),
        }
        for doc in result.get("source_documents", [])
    ]

    return {
        "answer": result["result"],
        "sources": sources,
    }


def stream_answer(document_id: int, question: str):
    """
    Generator that yields text chunks as the LLM produces them, then yields
    a final JSON-encoded sources line prefixed with 'SOURCES:'.
    """
    import json
    from langchain_core.messages import HumanMessage

    # 1. Retrieve relevant chunks (one embedding API call — unavoidable)
    retriever = _get_vector_store(document_id).as_retriever(
        search_type="similarity",
        search_kwargs={"k": RETRIEVAL_K},
    )
    docs = retriever.invoke(question)

    # 2. Build the prompt manually
    context = "\n\n".join(doc.page_content for doc in docs)
    filled_prompt = QA_PROMPT_TEMPLATE.replace("{context}", context).replace("{question}", question)

    # 3. Stream tokens from the LLM
    streaming_llm = ChatGoogleGenerativeAI(
        model=CHAT_MODEL,
        temperature=0,
        max_output_tokens=CHAT_MAX_TOKENS,
        google_api_key=settings.GEMINI_API_KEY,
        streaming=True,
    )

    full_answer = []
    for chunk in streaming_llm.stream([HumanMessage(content=filled_prompt)]):
        token = chunk.content
        if token:
            full_answer.append(token)
            yield token

    increment_usage("chat", 1)

    # 4. Send sources as the final line
    sources = [
        {
            "page": doc.metadata.get("page", "?"),
            "snippet": doc.page_content[:200].strip(),
        }
        for doc in docs
    ]
    yield f"\nSOURCES:{json.dumps(sources)}"


def delete_document_data(document_id: int):
    """Delete document collection from vector store and clear its cache entry."""
    logger.info("Deleting vector store data for document %s", document_id)
    try:
        # Use cached instance if available, otherwise open fresh
        vector_store = _vector_store_cache.pop(document_id, None) or Chroma(
            collection_name=_collection_name(document_id),
            embedding_function=_embeddings(),
            persist_directory=_chroma_dir(),
        )
        vector_store.delete_collection()
        logger.info("Collection document_%s deleted", document_id)
    except Exception as e:
        logger.error("Failed to delete collection for document %s: %s", document_id, e)
