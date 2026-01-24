from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = 'student', _('Student')
        TEACHER = 'teacher', _('Teacher')

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STUDENT,
        verbose_name=_('Role')
    )
    full_name = models.CharField(_('Full Name'), max_length=255, blank=True)
    teacher_email_notifications = models.BooleanField(
        default=True,
        verbose_name=_('Teacher email notifications')
    )
    teacher_app_notifications = models.BooleanField(
        default=True,
        verbose_name=_('Teacher app notifications')
    )
    supervisor_email_notifications = models.BooleanField(
        default=True,
        verbose_name=_('Supervisor email notifications')
    )
    supervisor_app_notifications = models.BooleanField(
        default=True,
        verbose_name=_('Supervisor app notifications')
    )

    def __str__(self):
        return self.username


class TeacherNotificationSettings(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="notification_settings",
    )
    exam_submissions_email = models.BooleanField(default=True)
    exam_submissions_app = models.BooleanField(default=True)
    student_messages_email = models.BooleanField(default=True)
    student_messages_app = models.BooleanField(default=True)
    cheating_attempts_email = models.BooleanField(default=True)
    cheating_attempts_app = models.BooleanField(default=True)
    supervisor_messages_email = models.BooleanField(default=True)
    supervisor_messages_app = models.BooleanField(default=True)
