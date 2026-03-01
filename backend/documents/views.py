import logging
import threading

from django.db import close_old_connections
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document, ChatMessage, ApiUsage
from .serializers import DocumentUploadSerializer, ChatQuerySerializer, ChatMessageSerializer
from ai.rag_engine import ingest_document, answer_question, delete_document_data, stream_answer

logger = logging.getLogger(__name__)


def _process_document(document_id: int, pdf_path: str):
    close_old_connections()
    try:
        ingest_document(document_id, pdf_path)
        Document.objects.filter(pk=document_id).update(is_processed=True)
        logger.info("Document %s processed successfully", document_id)
    except Exception as exc:
        logger.exception("Failed to ingest document %s: %s", document_id, exc)
        Document.objects.filter(pk=document_id).delete()
    finally:
        close_old_connections()


class DocumentUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = DocumentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        document = serializer.save()

        worker = threading.Thread(
            target=_process_document,
            args=(document.id, document.file.path),
            daemon=True,
        )
        worker.start()

        return Response(
            DocumentUploadSerializer(document).data,
            status=status.HTTP_202_ACCEPTED,
        )

    def get(self, request):
        documents = Document.objects.all()
        serializer = DocumentUploadSerializer(documents, many=True)
        return Response(serializer.data)


class ChatQueryView(APIView):

    def post(self, request):
        serializer = ChatQuerySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        document_id = serializer.validated_data["document_id"]
        question = serializer.validated_data["question"]

        try:
            document = Document.objects.get(pk=document_id)
        except Document.DoesNotExist:
            return Response(
                {"error": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not document.is_processed:
            return Response(
                {"error": "Document is still being processed. Please try again shortly."},
                status=status.HTTP_202_ACCEPTED,
            )

        try:
            result = answer_question(document_id, question)
            # Save chat message
            ChatMessage.objects.create(
                document=document, question=question, answer=result["answer"]
            )
        except Exception as exc:
            logger.exception("RAG query failed: %s", exc)
            return Response(
                {"error": f"Failed to answer question: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "document_id": document_id,
            "question": question,
            "answer": result["answer"],
            "sources": result["sources"],
        })


class ChatStreamView(APIView):
    """Stream the AI answer token-by-token using Server-Sent Events."""

    def post(self, request):
        serializer = ChatQuerySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        document_id = serializer.validated_data["document_id"]
        question = serializer.validated_data["question"]

        try:
            document = Document.objects.get(pk=document_id)
        except Document.DoesNotExist:
            return Response({"error": "Document not found."}, status=status.HTTP_404_NOT_FOUND)

        if not document.is_processed:
            return Response(
                {"error": "Document is still being processed."},
                status=status.HTTP_202_ACCEPTED,
            )

        def _event_stream():
            full_answer_parts = []
            sources = []
            try:
                for chunk in stream_answer(document_id, question):
                    if chunk.startswith("\nSOURCES:"):
                        import json
                        sources = json.loads(chunk[len("\nSOURCES:"):])
                    else:
                        full_answer_parts.append(chunk)
                        # SSE format: "data: <chunk>\n\n"
                        yield f"data: {chunk}\n\n"

                # Save complete message to DB
                full_answer = "".join(full_answer_parts)
                ChatMessage.objects.create(
                    document=document, question=question, answer=full_answer
                )

                # Send sources as final SSE event
                import json
                yield f"event: sources\ndata: {json.dumps(sources)}\n\n"
                yield "event: done\ndata: [DONE]\n\n"

            except Exception as exc:
                logger.exception("Streaming RAG query failed: %s", exc)
                yield f"event: error\ndata: {str(exc)}\n\n"

        response = StreamingHttpResponse(_event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class ChatHistoryView(APIView):
    """Retrieve or delete chat history for a document."""

    def get(self, request, document_id):
        try:
            document = Document.objects.get(pk=document_id)
        except Document.DoesNotExist:
            return Response(
                {"error": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        messages = document.chat_messages.all()
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)

    def delete(self, request, document_id):
        try:
            document = Document.objects.get(pk=document_id)
        except Document.DoesNotExist:
            return Response(
                {"error": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        document.chat_messages.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
class DocumentDetailView(APIView):
    """Retrieve or delete a specific document."""

    def delete(self, request, pk):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return Response(
                {"error": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 1. Delete vector store data
        delete_document_data(document.id)

        # 2. Delete physical PDF file
        if document.file:
            document.file.delete(save=False)

        # 3. Delete DB record (cascades to chat messages)
        document.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

class QuotaStatusView(APIView):
    """Retrieve today's API usage status."""

    def get(self, request):
        from django.utils import timezone
        usage, _ = ApiUsage.objects.get_or_create(date=timezone.now().date())
        
        return Response({
            "date": usage.date,
            "embeddings": usage.embeddings_count,
            "chat": usage.chat_count,
            "total": usage.total_requests,
            "limit": 1500,
            "remaining": max(0, 1500 - usage.total_requests),
            "percent": round((usage.total_requests / 1500) * 100, 1)
        })
