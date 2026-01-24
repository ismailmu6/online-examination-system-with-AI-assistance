from django.contrib import admin
from .models import (
    Group, Exam, Subject, Question, QuestionChoice, ExamQuestion,
    StudentExam, StudentAnswer, ExamEvent, ExamNotification,
    GroupMessage, StudentJoinRequest, Message, SystemSettings,
    ProctorSession, ProctorSnapshot, ProctorAudioStream
)


@admin.register(ProctorSession)
class ProctorSessionAdmin(admin.ModelAdmin):
    list_display = [
        "id", "student", "exam", "is_active",
        "camera_enabled", "microphone_enabled",
        "snapshots_count", "warnings_count", "created_at"
    ]
    list_filter = ["is_active", "camera_enabled", "microphone_enabled", "created_at"]
    search_fields = ["student__username", "student__email", "exam__title"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(ProctorSnapshot)
class ProctorSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "id", "session", "faces_detected", "suspicious", "created_at"
    ]
    list_filter = ["suspicious", "faces_detected", "created_at"]
    search_fields = ["session__student__username", "notes"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"


@admin.register(ProctorAudioStream)
class ProctorAudioStreamAdmin(admin.ModelAdmin):
    list_display = [
        "id", "session", "status", "started_at", "last_activity_at"
    ]
    list_filter = ["status", "started_at"]
    search_fields = ["session__student__username"]
    readonly_fields = ["last_activity_at"]
    date_hierarchy = "started_at"
