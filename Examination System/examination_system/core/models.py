from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings


User = get_user_model()


class Group(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    subject = models.ForeignKey(
        "Subject",
        on_delete=models.CASCADE,
        related_name="groups",
        blank=True,
        null=True,
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="teaching_groups",
    )
    students = models.ManyToManyField(
        User,
        related_name="student_groups",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Exam(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        ONGOING = "ongoing", "Ongoing"
        FINISHED = "finished", "Finished"

    title = models.CharField(max_length=255)
    subject = models.ForeignKey(
        "Subject",
        on_delete=models.CASCADE,
        related_name="exams",
        blank=True,
        null=True,
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exams",
    )
    start_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    total_mark = models.PositiveIntegerField(default=100)
    pass_mark = models.PositiveIntegerField(default=50, help_text="Passing percentage (0-100)")
    end_time = models.DateTimeField(blank=True, null=True)
    late_join_minutes = models.PositiveIntegerField(default=0)
    shuffle_questions = models.BooleanField(default=False)
    auto_proctoring = models.BooleanField(default=True)
    auto_fail_on_cheating = models.BooleanField(default=False)
    marking_type = models.CharField(
        max_length=20,
        default="per_question",
        choices=[("equal", "Equal"), ("per_question", "Per question")],
    )
    total_participants = models.PositiveIntegerField(default=0)
    submitted_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    allowed_students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="allowed_exams",
        blank=True,
    )

    class Meta:
        ordering = ["-start_time"]

    def __str__(self):
        return self.title


class Subject(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to="subject_images/", blank=True, null=True)
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    description = models.TextField(blank=True)
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="subject_enrollments",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Question(models.Model):
    class QuestionType(models.TextChoices):
        MCQ = "mcq", "MCQ"
        ESSAY = "essay", "Essay"

    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    text = models.TextField()
    question_type = models.CharField(
        max_length=10,
        choices=QuestionType.choices,
        default=QuestionType.MCQ,
    )
    difficulty = models.CharField(
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.MEDIUM,
    )
    mark = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    model_answer = models.TextField(blank=True, null=True, verbose_name="الإجابة النموذجية (للأسئلة المقالية)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.text[:100]


class QuestionChoice(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="choices",
    )
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]


class ExamQuestion(models.Model):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="exam_questions",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="exam_questions",
    )
    order = models.PositiveIntegerField(default=0)
    mark = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "question"],
                name="unique_exam_question",
            )
        ]


class StudentExam(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        FINISHED = "finished", "Finished"
        FAILED_CHEATING = "failed_cheating", "Failed due to cheating"

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exam_attempts",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student"],
                name="unique_exam_student_attempt",
            )
        ]


class StudentAnswer(models.Model):
    attempt = models.ForeignKey(
        StudentExam,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    exam_question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    selected_choice = models.ForeignKey(
        QuestionChoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_answers",
    )
    essay_text = models.TextField(blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    mark_obtained = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-answered_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "exam_question"],
                name="unique_attempt_exam_question",
            )
        ]


class ExamEvent(models.Model):
    class EventType(models.TextChoices):
        JOIN = "join", "Join"
        SUBMIT = "submit", "Submit"
        PROGRESS = "progress", "Progress"
        CHEATING_VISIBILITY = "cheating_visibility", "Cheating visibility"
        CHEATING_CLIPBOARD = "cheating_clipboard", "Cheating clipboard"
        CAMERA_ALLOWED = "camera_allowed", "Camera allowed"
        CAMERA_DENIED = "camera_denied", "Camera denied"

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="events",
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exam_events",
    )
    event_type = models.CharField(
        max_length=32,
        choices=EventType.choices,
    )
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]


class ExamNotification(models.Model):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_exam_notifications",
    )
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_exam_notifications",
        null=True,
        blank=True,
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]

class GroupMessage(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="group_messages",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class StudentJoinRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    class Source(models.TextChoices):
        FROM_STUDENT = "from_student", "From student"
        FROM_TEACHER = "from_teacher", "From teacher"

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="join_requests",
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_join_requests",
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="join_requests",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.FROM_STUDENT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Message(models.Model):
    class Direction(models.TextChoices):
        TEACHER_TO_SUPERVISOR = "teacher_to_supervisor", "Teacher to supervisor"
        SUPERVISOR_TO_TEACHER = "supervisor_to_teacher", "Supervisor to teacher"
        TEACHER_TO_STUDENT = "teacher_to_student", "Teacher to student"
        STUDENT_TO_TEACHER = "student_to_teacher", "Student to teacher"
        SUPERVISOR_TO_SUPERVISOR = "supervisor_to_supervisor", "Supervisor to supervisor"

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_messages",
    )
    direction = models.CharField(
        max_length=32,
        choices=Direction.choices,
    )
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    category = models.CharField(max_length=50, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    in_reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )

    class Meta:
        ordering = ["-created_at"]

class SystemSettings(models.Model):
    platform_name = models.CharField(max_length=255, default="منصة الاختبارات الذكية")
    two_factor_email = models.EmailField(blank=True)
    two_factor_app_password = models.CharField(max_length=255, blank=True)
    system_icon = models.ImageField(upload_to="system_icons/", blank=True, null=True)

    def __str__(self):
        return "إعدادات النظام"

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        if created and not obj.two_factor_email:
            obj.two_factor_email = getattr(settings, "EMAIL_HOST_USER", "")
            obj.save()
        return obj


class ProctorSession(models.Model):
    """
    جلسة مراقبة الطالب أثناء الاختبار:
    - تخزين Snapshots (صور) من كاميرا الطالب
    - إدارة اتصالات WebRTC للصوت
    - تتبع حالة المراقبة
    """
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="proctor_sessions",
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="proctor_sessions",
    )
    student_exam = models.ForeignKey(
        StudentExam,
        on_delete=models.CASCADE,
        related_name="proctor_sessions",
        null=True,
        blank=True,
    )
    
    # حالة الجلسة
    is_active = models.BooleanField(default=True)
    camera_enabled = models.BooleanField(default=False)
    microphone_enabled = models.BooleanField(default=False)
    
    # آخر snapshot
    last_snapshot = models.ImageField(
        upload_to="proctor_snapshots/%Y/%m/%d/",
        null=True,
        blank=True,
    )
    last_snapshot_at = models.DateTimeField(null=True, blank=True)
    
    # إحصائيات
    snapshots_count = models.IntegerField(default=0)
    warnings_count = models.IntegerField(default=0)
    
    # WebRTC peer connection data (JSON)
    peer_connection_data = models.JSONField(default=dict, blank=True)
    
    # التوقيتات
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
        unique_together = [["exam", "student"]]
    
    def __str__(self):
        return f"Proctor: {self.student.username} - {self.exam.title}"


class ProctorSnapshot(models.Model):
    """
    صورة التقطت من كاميرا الطالب أثناء الاختبار
    """
    session = models.ForeignKey(
        ProctorSession,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    image = models.ImageField(upload_to="proctor_snapshots/%Y/%m/%d/")
    
    # تحليل تلقائي (اختياري - يمكن إضافة AI لاحقاً)
    faces_detected = models.IntegerField(default=0)
    suspicious = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"Snapshot: {self.session.student.username} at {self.created_at}"


class ProctorAudioStream(models.Model):
    """
    تتبع حالة البث الصوتي المستمر من الطالب
    """
    class StreamStatus(models.TextChoices):
        WAITING = "waiting", "Waiting"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        ENDED = "ended", "Ended"
    
    session = models.OneToOneField(
        ProctorSession,
        on_delete=models.CASCADE,
        related_name="audio_stream",
    )
    
    status = models.CharField(
        max_length=20,
        choices=StreamStatus.choices,
        default=StreamStatus.WAITING,
    )
    
    # WebRTC signaling data
    offer_sdp = models.TextField(blank=True)
    answer_sdp = models.TextField(blank=True)
    ice_candidates = models.JSONField(default=list, blank=True)
    
    # إحصائيات
    bytes_received = models.BigIntegerField(default=0)
    packets_lost = models.IntegerField(default=0)
    
    started_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-started_at"]
    
    def __str__(self):
        return f"Audio: {self.session.student.username} - {self.status}"
