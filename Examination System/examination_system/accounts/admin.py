from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, TeacherNotificationSettings

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'full_name', 'role', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Extra Info', {'fields': ('role', 'full_name', 'teacher_email_notifications', 'teacher_app_notifications', 'supervisor_email_notifications', 'supervisor_app_notifications')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Extra Info', {'fields': ('role', 'full_name')}),
    )

@admin.register(TeacherNotificationSettings)
class TeacherNotificationSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'exam_submissions_email', 'student_messages_email')
