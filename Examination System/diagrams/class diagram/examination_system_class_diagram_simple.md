# Examination System - Class Diagram (Simple Text Format)

## نظرة عامة
هذا الملف يحتوي على وصف نصي مبسط لجميع النماذج والعلاقات في النظام. يمكن استخدامه كمرجع سريع أو كبديل للمخطط المرئي.

---

## 1. User (المستخدم)

**الموقع**: `accounts/models.py`

**يمتد من**: `AbstractUser` (Django)

**الحقول الأساسية** (من AbstractUser):
- `id`, `username`, `email`, `password`, `first_name`, `last_name`
- `is_active`, `is_staff`, `is_superuser`
- `date_joined`, `last_login`

**الحقول المخصصة**:
- `role`: CharField(10) - [STUDENT, TEACHER]
- `full_name`: CharField(255)
- `teacher_email_notifications`: BooleanField
- `teacher_app_notifications`: BooleanField
- `supervisor_email_notifications`: BooleanField
- `supervisor_app_notifications`: BooleanField

**العلاقات**:
- OneToOne → TeacherNotificationSettings
- OneToMany → Subject (as teacher)
- OneToMany → Group (as teacher)
- OneToMany → Exam (as teacher)
- OneToMany → Question (as teacher)
- OneToMany → StudentExam (as student)
- OneToMany → ExamEvent (as student)
- OneToMany → ExamNotification (as sender/recipient)
- OneToMany → Message (as sender/recipient)
- OneToMany → GroupMessage (as sender)
- OneToMany → StudentJoinRequest (as student/teacher)
- OneToMany → ProctorSession (as student)
- ManyToMany → Subject (as enrolled_students)
- ManyToMany → Group (as students)
- ManyToMany → Exam (as allowed_students)

---

## 2. TeacherNotificationSettings (إعدادات إشعارات المدرس)

**الموقع**: `accounts/models.py`

**الحقول**:
- `user_id`: OneToOne → User
- `exam_submissions_email`: BooleanField
- `exam_submissions_app`: BooleanField
- `student_messages_email`: BooleanField
- `student_messages_app`: BooleanField
- `cheating_attempts_email`: BooleanField
- `cheating_attempts_app`: BooleanField
- `supervisor_messages_email`: BooleanField
- `supervisor_messages_app`: BooleanField

---

## 3. Subject (المادة الدراسية)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `name`: CharField(255)
- `image`: ImageField
- `description`: TextField
- `teacher_id`: ForeignKey → User
- `created_at`: DateTimeField
- `updated_at`: DateTimeField

**العلاقات**:
- ManyToOne → User (teacher)
- OneToMany → Group
- OneToMany → Exam
- OneToMany → Question
- ManyToMany → User (students)

---

## 4. Group (المجموعة الدراسية)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `name`: CharField(255)
- `code`: CharField(50) [unique]
- `subject_id`: ForeignKey → Subject [nullable]
- `teacher_id`: ForeignKey → User
- `created_at`: DateTimeField

**العلاقات**:
- ManyToOne → Subject
- ManyToOne → User (teacher)
- ManyToMany → User (students)
- OneToMany → GroupMessage
- OneToMany → StudentJoinRequest

---

## 5. Question (السؤال)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `subject_id`: ForeignKey → Subject
- `teacher_id`: ForeignKey → User
- `text`: TextField
- `question_type`: CharField(10) [MCQ, ESSAY]
- `difficulty`: CharField(10) [EASY, MEDIUM, HARD]
- `mark`: DecimalField(5,2)
- `model_answer`: TextField [nullable] - للإجابات المقالية
- `created_at`: DateTimeField
- `updated_at`: DateTimeField

**العلاقات**:
- ManyToOne → Subject
- ManyToOne → User (teacher)
- OneToMany → QuestionChoice
- OneToMany → ExamQuestion

---

## 6. QuestionChoice (خيار السؤال)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `question_id`: ForeignKey → Question
- `text`: CharField(500)
- `is_correct`: BooleanField
- `order`: PositiveIntegerField

**العلاقات**:
- ManyToOne → Question
- OneToMany → StudentAnswer

---

## 7. Exam (الاختبار)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `title`: CharField(255)
- `subject_id`: ForeignKey → Subject [nullable]
- `teacher_id`: ForeignKey → User
- `start_time`: DateTimeField
- `duration_minutes`: PositiveIntegerField
- `status`: CharField(20) [DRAFT, SCHEDULED, ONGOING, FINISHED]
- `total_mark`: PositiveIntegerField
- `pass_mark`: PositiveIntegerField (0-100)
- `end_time`: DateTimeField [nullable]
- `late_join_minutes`: PositiveIntegerField
- `shuffle_questions`: BooleanField
- `auto_proctoring`: BooleanField
- `auto_fail_on_cheating`: BooleanField
- `marking_type`: CharField(20) [equal, per_question]
- `total_participants`: PositiveIntegerField
- `submitted_count`: PositiveIntegerField
- `created_at`: DateTimeField
- `updated_at`: DateTimeField

**العلاقات**:
- ManyToOne → Subject
- ManyToOne → User (teacher)
- ManyToMany → User (allowed_students)
- OneToMany → ExamQuestion
- OneToMany → StudentExam
- OneToMany → ExamEvent
- OneToMany → ExamNotification
- OneToMany → ProctorSession

---

## 8. ExamQuestion (سؤال في الاختبار)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `exam_id`: ForeignKey → Exam
- `question_id`: ForeignKey → Question
- `order`: PositiveIntegerField
- `mark`: DecimalField(5,2)

**القيود**:
- UniqueConstraint: (exam, question) - سؤال واحد لا يمكن أن يكون في نفس الاختبار مرتين

**العلاقات**:
- ManyToOne → Exam
- ManyToOne → Question
- OneToMany → StudentAnswer

---

## 9. StudentExam (محاولة الطالب)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `exam_id`: ForeignKey → Exam
- `student_id`: ForeignKey → User
- `status`: CharField(20) [IN_PROGRESS, FINISHED, FAILED_CHEATING]
- `started_at`: DateTimeField [nullable]
- `finished_at`: DateTimeField [nullable]
- `last_activity_at`: DateTimeField [nullable]
- `score`: DecimalField(7,2)
- `created_at`: DateTimeField

**القيود**:
- UniqueConstraint: (exam, student) - طالب واحد لا يمكن أن يحاول نفس الاختبار مرتين

**العلاقات**:
- ManyToOne → Exam
- ManyToOne → User (student)
- OneToMany → StudentAnswer
- OneToMany → ProctorSession

---

## 10. StudentAnswer (إجابة الطالب)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `attempt_id`: ForeignKey → StudentExam
- `exam_question_id`: ForeignKey → ExamQuestion
- `selected_choice_id`: ForeignKey → QuestionChoice [nullable] - للأسئلة MCQ
- `essay_text`: TextField - للأسئلة المقالية
- `is_correct`: BooleanField [nullable]
- `mark_obtained`: DecimalField(5,2)
- `answered_at`: DateTimeField

**القيود**:
- UniqueConstraint: (attempt, exam_question) - إجابة واحدة لكل سؤال في كل محاولة

**العلاقات**:
- ManyToOne → StudentExam
- ManyToOne → ExamQuestion
- ManyToOne → QuestionChoice [nullable]

---

## 11. ExamEvent (حدث الاختبار)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `exam_id`: ForeignKey → Exam
- `student_id`: ForeignKey → User
- `event_type`: CharField(32) [JOIN, SUBMIT, PROGRESS, CHEATING_VISIBILITY, CHEATING_CLIPBOARD, CAMERA_ALLOWED, CAMERA_DENIED]
- `message`: TextField
- `created_at`: DateTimeField

**العلاقات**:
- ManyToOne → Exam
- ManyToOne → User (student)

---

## 12. ExamNotification (إشعار الاختبار)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `exam_id`: ForeignKey → Exam
- `sender_id`: ForeignKey → User
- `recipient_id`: ForeignKey → User [nullable] - null يعني لجميع الطلاب
- `message`: TextField
- `created_at`: DateTimeField

**العلاقات**:
- ManyToOne → Exam
- ManyToOne → User (sender)
- ManyToOne → User (recipient)

---

## 13. Message (الرسالة)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `sender_id`: ForeignKey → User
- `recipient_id`: ForeignKey → User
- `direction`: CharField(32) [TEACHER_TO_SUPERVISOR, SUPERVISOR_TO_TEACHER, TEACHER_TO_STUDENT, STUDENT_TO_TEACHER, SUPERVISOR_TO_SUPERVISOR]
- `title`: CharField(255)
- `body`: TextField
- `category`: CharField(50)
- `is_read`: BooleanField
- `in_reply_to_id`: ForeignKey → Message [nullable] - للردود
- `created_at`: DateTimeField

**العلاقات**:
- ManyToOne → User (sender)
- ManyToOne → User (recipient)
- ManyToOne → Message (self-reference for replies)

---

## 14. GroupMessage (رسالة المجموعة)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `group_id`: ForeignKey → Group
- `sender_id`: ForeignKey → User
- `content`: TextField
- `created_at`: DateTimeField

**العلاقات**:
- ManyToOne → Group
- ManyToOne → User (sender)

---

## 15. StudentJoinRequest (طلب الانضمام)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `student_id`: ForeignKey → User
- `teacher_id`: ForeignKey → User
- `group_id`: ForeignKey → Group [nullable]
- `status`: CharField(20) [PENDING, ACCEPTED, REJECTED]
- `source`: CharField(20) [FROM_STUDENT, FROM_TEACHER]
- `created_at`: DateTimeField

**العلاقات**:
- ManyToOne → User (student)
- ManyToOne → User (teacher)
- ManyToOne → Group

---

## 16. SystemSettings (إعدادات النظام)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `platform_name`: CharField(255)
- `two_factor_email`: EmailField
- `two_factor_app_password`: CharField(255)
- `system_icon`: ImageField [nullable]

**الطرق**:
- `__str__()`: String
- `load()`: @classmethod → SystemSettings (Singleton pattern)

---

## 17. ProctorSession (جلسة المراقبة)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `exam_id`: ForeignKey → Exam
- `student_id`: ForeignKey → User
- `student_exam_id`: ForeignKey → StudentExam [nullable]
- `is_active`: BooleanField
- `camera_enabled`: BooleanField
- `microphone_enabled`: BooleanField
- `last_snapshot`: ImageField [nullable]
- `last_snapshot_at`: DateTimeField [nullable]
- `snapshots_count`: IntegerField
- `warnings_count`: IntegerField
- `peer_connection_data`: JSONField (WebRTC data)
- `created_at`: DateTimeField
- `updated_at`: DateTimeField
- `ended_at`: DateTimeField [nullable]

**القيود**:
- UniqueConstraint: (exam, student) - جلسة واحدة لكل طالب في كل اختبار

**العلاقات**:
- ManyToOne → Exam
- ManyToOne → User (student)
- ManyToOne → StudentExam
- OneToMany → ProctorSnapshot
- OneToOne → ProctorAudioStream

---

## 18. ProctorSnapshot (صورة المراقبة)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `session_id`: ForeignKey → ProctorSession
- `image`: ImageField
- `faces_detected`: IntegerField
- `suspicious`: BooleanField
- `notes`: TextField
- `created_at`: DateTimeField

**العلاقات**:
- ManyToOne → ProctorSession

---

## 19. ProctorAudioStream (البث الصوتي)

**الموقع**: `core/models.py`

**الحقول**:
- `id`: PK
- `session_id`: OneToOne → ProctorSession
- `status`: CharField(20) [WAITING, ACTIVE, PAUSED, ENDED]
- `offer_sdp`: TextField (WebRTC offer)
- `answer_sdp`: TextField (WebRTC answer)
- `ice_candidates`: JSONField (WebRTC ICE candidates)
- `bytes_received`: BigIntegerField
- `packets_lost`: IntegerField
- `started_at`: DateTimeField [nullable]
- `last_activity_at`: DateTimeField
- `ended_at`: DateTimeField [nullable]

**العلاقات**:
- OneToOne → ProctorSession

---

## ملخص العلاقات

### One-to-Many (1:N)
- User → Subject (teacher)
- User → Group (teacher)
- User → Exam (teacher)
- User → Question (teacher)
- User → StudentExam (student)
- User → ExamEvent (student)
- User → ExamNotification (sender/recipient)
- User → Message (sender/recipient)
- User → GroupMessage (sender)
- User → StudentJoinRequest (student/teacher)
- User → ProctorSession (student)
- Subject → Group
- Subject → Exam
- Subject → Question
- Group → GroupMessage
- Group → StudentJoinRequest
- Question → QuestionChoice
- Question → ExamQuestion
- Exam → ExamQuestion
- Exam → StudentExam
- Exam → ExamEvent
- Exam → ExamNotification
- Exam → ProctorSession
- ExamQuestion → StudentAnswer
- StudentExam → StudentAnswer
- StudentExam → ProctorSession
- ProctorSession → ProctorSnapshot

### Many-to-Many (N:M)
- User ↔ Subject (students enrollment)
- User ↔ Group (students)
- User ↔ Exam (allowed_students)

### One-to-One (1:1)
- User ↔ TeacherNotificationSettings
- ProctorSession ↔ ProctorAudioStream

### Self-Reference
- Message → Message (replies)

---

## ملاحظات مهمة

1. **Admin Role**: المشرف (Admin) ليس له enum منفصل، بل يتم تحديده من خلال `is_superuser=True` في نموذج User.

2. **Unique Constraints**:
   - ExamQuestion: (exam, question)
   - StudentExam: (exam, student)
   - StudentAnswer: (attempt, exam_question)
   - ProctorSession: (exam, student)

3. **Proctoring**: يستخدم WebRTC للبث الصوتي المباشر، ويقوم بتخزين snapshots من الكاميرا بشكل دوري.

4. **Notification Settings**: هناك نوعان:
   - في User: للإشعارات العامة
   - في TeacherNotificationSettings: إعدادات مفصلة للمدرسين
