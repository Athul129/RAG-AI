from django.db import models


class Document(models.Model):
    """Represents an uploaded PDF document."""

    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="pdfs/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


class ChatMessage(models.Model):
    """Represents a single question and answer in a chat session."""

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="chat_messages"
    )
    question = models.TextField()
    answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Q: {self.question[:50]}..."


class ApiUsage(models.Model):
    """Tracks daily API usage to stay within free tier limits."""

    date = models.DateField(auto_now_add=True, unique=True)
    embeddings_count = models.IntegerField(default=0)
    chat_count = models.IntegerField(default=0)

    @property
    def total_requests(self):
        return self.embeddings_count + self.chat_count

    class Meta:
        verbose_name_plural = "API Usage"

    def __str__(self):
        return f"{self.date}: {self.total_requests} requests"