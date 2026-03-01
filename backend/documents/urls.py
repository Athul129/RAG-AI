from django.urls import path
from .views import DocumentUploadView, ChatQueryView, ChatHistoryView, DocumentDetailView, QuotaStatusView, ChatStreamView

urlpatterns = [
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("documents/chat/", ChatQueryView.as_view(), name="document-chat"),
    path("documents/stream/", ChatStreamView.as_view(), name="document-stream"),
    path("documents/history/<int:document_id>/", ChatHistoryView.as_view(), name="chat-history"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("quota/", QuotaStatusView.as_view(), name="quota-status"),
]