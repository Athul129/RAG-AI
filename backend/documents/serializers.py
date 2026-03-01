from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "title", "uploaded_at", "is_processed"]
        read_only_fields = ["id", "uploaded_at", "is_processed"]


class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "title", "file", "uploaded_at", "is_processed"]
        read_only_fields = ["id", "uploaded_at", "is_processed"]


class ChatQuerySerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000)
    document_id = serializers.IntegerField()


from .models import ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "question", "answer", "created_at"]
        read_only_fields = ["id", "created_at"]