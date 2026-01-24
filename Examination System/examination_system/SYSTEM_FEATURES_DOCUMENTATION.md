# 📚 دليل مميزات نظام الاختبارات الإلكترونية

## 🎯 نظرة عامة

نظام الاختبارات الإلكترونية هو منصة متكاملة لإدارة الاختبارات عبر الإنترنت، مبني باستخدام Django وTailwind CSS. يدعم النظام ثلاثة أنواع من المستخدمين: المدير، المدرس، والطالب.

---

## 🔐 1. نظام المصادقة والأمان المتقدم

### المميزات:
- **مصادقة ثنائية (2FA)** باستخدام TOTP
- **إعادة تعيين كلمة المرور** عبر البريد الإلكتروني
- **أدوار مستخدمين متعددة** (Admin, Teacher, Student)
- **حماية الصفحات** بناءً على الأدوار

### كيفية البرمجة:

#### 1.1 المصادقة الثنائية (2FA)
```python
# في accounts/models.py
class User(AbstractUser):
    two_factor_secret = models.CharField(max_length=32, blank=True)
    two_factor_enabled = models.BooleanField(default=False)
```

**الآلية:**
- استخدام مكتبة `pyotp` لتوليد أكواد TOTP
- تخزين المفتاح السري في قاعدة البيانات
- التحقق من الكود عند كل تسجيل دخول

```python
# في accounts/views.py
def verify_2fa(request):
    secret = request.user.two_factor_secret
    totp = pyotp.TOTP(secret)
    if totp.verify(code, valid_window=1):
        # تسجيل دخول ناجح
```

#### 1.2 إعادة تعيين كلمة المرور
```python
# في accounts/urls.py
path('password-reset/', auth_views.PasswordResetView.as_view(
    template_name='accounts/password_reset.html',
    email_template_name='accounts/password_reset_email.txt',
))
```

**الآلية:**
- استخدام Django's built-in password reset views
- إرسال رابط آمن عبر البريد الإلكتروني
- Token يستخدم مرة واحدة فقط

#### 1.3 حماية الصفحات
```python
# في core/views.py
@login_required
@user_passes_test(is_teacher)
def teacher_dashboard(request):
    # الكود هنا
```

**الآلية:**
- `@login_required`: التأكد من تسجيل الدخول
- `@user_passes_test`: التحقق من صلاحيات المستخدم
- إعادة توجيه تلقائية للصفحة المناسبة

---

## 📝 2. إدارة الاختبارات الذكية

### المميزات:
- **حالات ديناميكية** للاختبارات (Draft, Scheduled, Ongoing, Finished, Archived)
- **تحديث تلقائي** للحالات بناءً على الوقت
- **جدولة مرنة** مع إمكانية التأخير في الانضمام
- **خلط الأسئلة** لكل طالب

### كيفية البرمجة:

#### 2.1 نظام الحالات الديناميكية
```python
# في core/models.py
class Exam(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        ONGOING = "ongoing", "Ongoing"
        FINISHED = "finished", "Finished"
        ARCHIVED = "archived", "Archived"
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
```

#### 2.2 التحديث التلقائي للحالات
```python
# في core/views.py
def _sync_exam_statuses(exams_queryset):
    """
    تحديث حالات الاختبارات تلقائياً بناءً على الوقت الحالي
    """
    now = timezone.now()
    for exam in exams_queryset:
        # التحقق من وجود أسئلة وطلاب
        has_questions = exam.questions_count > 0
        has_students = exam.allowed_students_count > 0
        
        if not has_questions or not has_students:
            desired_status = Exam.Status.DRAFT
        else:
            computed_end = exam.end_time or (
                exam.start_time + timedelta(minutes=exam.duration_minutes)
            )
            if now < exam.start_time:
                desired_status = Exam.Status.SCHEDULED
            elif exam.start_time <= now <= computed_end:
                desired_status = Exam.Status.ONGOING
            else:
                desired_status = Exam.Status.FINISHED
        
        if exam.status != desired_status:
            exam.status = desired_status
            exam.save(update_fields=["status"])
```

**الآلية:**
- يتم استدعاء `_sync_exam_statuses` عند عرض قائمة الاختبارات
- مقارنة الوقت الحالي مع وقت البداية والنهاية
- تحديث الحالة تلقائياً في قاعدة البيانات

#### 2.3 خلط الأسئلة
```python
# في core/views.py - student_exam_take
if exam.shuffle_questions:
    import random
    questions_list = list(questions)
    random.shuffle(questions_list)
    questions = questions_list
```

**الآلية:**
- استخدام `random.shuffle()` لخلط ترتيب الأسئلة
- يتم الخلط لكل طالب على حدة
- الحفاظ على نفس الترتيب خلال محاولة الطالب

---

## 🎓 3. نظام الأسئلة المتقدم

### المميزات:
- **أنواع متعددة** من الأسئلة (MCQ, True/False, Essay)
- **بنك أسئلة** لكل مادة
- **إجابات نموذجية** للأسئلة المقالية
- **علامات مخصصة** لكل سؤال

### كيفية البرمجة:

#### 3.1 نموذج الأسئلة
```python
# في core/models.py
class Question(models.Model):
    class QuestionType(models.TextChoices):
        MCQ = "mcq", "Multiple Choice"
        TRUE_FALSE = "true_false", "True/False"
        ESSAY = "essay", "Essay"
    
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    text = models.TextField()
    model_answer = models.TextField(blank=True)  # للأسئلة المقالية
```

#### 3.2 خيارات الأسئلة
```python
class QuestionChoice(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="choices"
    )
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
```

**الآلية:**
- علاقة One-to-Many بين السؤال والخيارات
- حقل `is_correct` لتحديد الإجابة الصحيحة
- يمكن أن يكون هناك خيار صحيح واحد أو أكثر

#### 3.3 ربط الأسئلة بالاختبارات
```python
class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
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
```

**الآلية:**
- جدول وسيط بين الاختبار والأسئلة
- `order`: ترتيب السؤال في الاختبار
- `mark`: العلامة المخصصة لهذا السؤال في هذا الاختبار
- Unique constraint لمنع تكرار السؤال في نفس الاختبار

---

## 🔍 4. نظام المراقبة والحماية من الغش

### المميزات:
- **مراقبة في الوقت الفعلي** لنشاط الطلاب
- **كشف تبديل التبويبات** (Tab Switching)
- **كشف استخدام الحافظة** (Clipboard)
- **تتبع آخر نشاط** للطالب
- **إنهاء تلقائي** عند الغش (اختياري)

### كيفية البرمجة:

#### 4.1 تتبع أحداث الغش
```python
# في core/models.py
class ExamEvent(models.Model):
    class EventType(models.TextChoices):
        JOIN = "join", "Join"
        SUBMIT = "submit", "Submit"
        PROGRESS = "progress", "Progress"
        CHEATING_VISIBILITY = "cheating_visibility", "Cheating visibility"
        CHEATING_CLIPBOARD = "cheating_clipboard", "Cheating clipboard"
    
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

#### 4.2 كشف تبديل التبويبات (Frontend)
```javascript
// في student_exam_take.html
document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
        // الطالب غادر التبويب
        fetch("{% url 'student_exam_event' exam.id %}", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify({
                event_type: "cheating_visibility",
                message: "غادر الطالب نافذة الاختبار",
            }),
        });
    }
});
```

#### 4.3 كشف استخدام الحافظة (Frontend)
```javascript
// في student_exam_take.html
document.addEventListener("copy", function (e) {
    e.preventDefault();
    fetch("{% url 'student_exam_event' exam.id %}", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({
            event_type: "cheating_clipboard",
            message: "محاولة نسخ محتوى",
        }),
    });
});

document.addEventListener("paste", function (e) {
    e.preventDefault();
    // نفس الآلية
});
```

#### 4.4 معالجة الأحداث (Backend)
```python
# في core/views.py
@login_required
@user_passes_test(is_student)
def student_exam_event(request, exam_id):
    if request.method != "POST":
        return HttpResponseBadRequest()
    
    data = json.loads(request.body)
    event_type = data.get("event_type")
    message = data.get("message", "")
    
    # حفظ الحدث
    ExamEvent.objects.create(
        exam=exam,
        student=request.user,
        event_type=event_type,
        message=message,
    )
    
    # إنهاء تلقائي إذا كان مفعلاً
    if exam.auto_fail_on_cheating and event_type in [
        ExamEvent.EventType.CHEATING_VISIBILITY,
        ExamEvent.EventType.CHEATING_CLIPBOARD,
    ]:
        attempt.status = StudentExam.Status.FAILED_CHEATING
        attempt.save()
    
    return JsonResponse({"status": "ok"})
```

#### 4.5 المراقبة في الوقت الفعلي
```python
# في core/views.py
@login_required
@user_passes_test(is_teacher)
def teacher_exam_monitor(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    
    # جلب محاولات الطلاب
    attempts_qs = StudentExam.objects.filter(exam=exam).select_related("student")
    
    # حساب الطلاب النشطين
    now = timezone.now()
    stale_seconds = 45
    active_students = attempts_qs.filter(
        status=StudentExam.Status.IN_PROGRESS,
        last_activity_at__gte=now - timedelta(seconds=stale_seconds)
    ).count()
    
    # جلب أحداث الغش
    suspicions = ExamEvent.objects.filter(
        exam=exam,
        event_type__in=[
            ExamEvent.EventType.CHEATING_VISIBILITY,
            ExamEvent.EventType.CHEATING_CLIPBOARD,
        ],
    ).count()
    
    # ... المزيد من الإحصائيات
```

**الآلية:**
- **Frontend:** JavaScript يراقب أحداث المتصفح
- **Backend:** API endpoint يستقبل ويحفظ الأحداث
- **Real-time:** تحديث كل 5 ثوانٍ باستخدام AJAX
- **Auto-fail:** إنهاء المحاولة تلقائياً عند الغش (اختياري)

---

## ⏱️ 5. نظام المؤقت الذكي

### المميزات:
- **مؤقت تنازلي** لكل طالب
- **إنهاء تلقائي** عند انتهاء الوقت
- **تنبيهات** عند 5 دقائق ودقيقة واحدة
- **حساب دقيق** للوقت المتبقي

### كيفية البرمجة:

#### 5.1 حساب الوقت المتبقي (Backend)
```python
# في core/views.py - student_exam_take
end_time = exam.end_time or (
    exam.start_time + timedelta(minutes=exam.duration_minutes)
)

if attempt.started_at:
    personal_end = attempt.started_at + timedelta(minutes=exam.duration_minutes)
    end_time = min(end_time, personal_end)

remaining_seconds = int((end_time - timezone.now()).total_seconds())
if remaining_seconds < 0:
    remaining_seconds = 0
```

#### 5.2 المؤقت التنازلي (Frontend)
```javascript
// في student_exam_take.html
var remaining = {{ remaining_seconds }};

if (!isNaN(remaining) && remaining > 0) {
    var timerDisplay = document.getElementById("exam-timer");
    var interval = setInterval(function () {
        remaining -= 1;
        
        // تنبيه عند 5 دقائق
        if (remaining === 300) {
            alert("تبقى 5 دقائق على انتهاء الاختبار!");
        }
        
        // تنبيه عند دقيقة واحدة
        if (remaining === 60) {
            alert("تبقى دقيقة واحدة على انتهاء الاختبار!");
        }
        
        // إنهاء تلقائي
        if (remaining < 0) {
            remaining = 0;
            clearInterval(interval);
            document.getElementById("examForm").submit();
        }
        
        // تحديث العرض
        var hours = Math.floor(remaining / 3600);
        var minutes = Math.floor((remaining % 3600) / 60);
        var seconds = remaining % 60;
        
        timerDisplay.textContent = 
            hours.toString().padStart(2, "0") + ":" +
            minutes.toString().padStart(2, "0") + ":" +
            seconds.toString().padStart(2, "0");
    }, 1000);
}
```

**الآلية:**
- حساب الوقت المتبقي في الـ Backend
- تمرير القيمة إلى الـ Frontend
- JavaScript countdown timer
- Auto-submit عند انتهاء الوقت

---

## 📊 6. نظام التصحيح والنتائج

### المميزات:
- **تصحيح تلقائي** للأسئلة الموضوعية
- **تصحيح يدوي** للأسئلة المقالية
- **إحصائيات تفصيلية** للنتائج
- **توزيع الدرجات** (Grade Distribution)
- **معدل النجاح** (Pass Rate)

### كيفية البرمجة:

#### 6.1 التصحيح التلقائي
```python
# في core/views.py - student_exam_take (POST)
for question in questions:
    if question.question_type == Question.QuestionType.MCQ:
        selected_choice_id = request.POST.get(f"question_{question.id}")
        if selected_choice_id:
            selected_choice = QuestionChoice.objects.get(id=selected_choice_id)
            
            # حساب العلامة
            if selected_choice.is_correct:
                mark_obtained = exam_question.mark
            else:
                mark_obtained = 0
            
            # حفظ الإجابة
            StudentAnswer.objects.create(
                attempt=attempt,
                question=question,
                selected_choice=selected_choice,
                mark_obtained=mark_obtained,
            )
```

#### 6.2 التصحيح اليدوي
```python
# في core/views.py - teacher_exam_student_correction
@login_required
@user_passes_test(is_teacher)
def teacher_exam_student_correction(request, exam_id, attempt_id):
    if request.method == "POST":
        for answer in answers:
            if answer.question.question_type == Question.QuestionType.ESSAY:
                mark_key = f"mark_{answer.id}"
                if mark_key in request.POST:
                    mark = Decimal(request.POST[mark_key])
                    answer.mark_obtained = mark
                    answer.save(update_fields=["mark_obtained"])
        
        # تحديث المجموع الكلي
        attempt.score = StudentAnswer.objects.filter(
            attempt=attempt
        ).aggregate(total=Sum("mark_obtained"))["total"] or 0
        attempt.save(update_fields=["score"])
```

#### 6.3 حساب الإحصائيات
```python
# في core/views.py - teacher_exam_results
# حساب المجموع الكلي للاختبار
total_mark = (
    ExamQuestion.objects.filter(exam=exam)
    .aggregate(total=Sum("mark"))["total"] or 0
)

# حساب نسبة النجاح
students_data = []
for attempt in attempts:
    score_percent = (
        (float(attempt.score) / float(total_mark)) * 100
        if total_mark > 0 else 0
    )
    
    # تحديد حالة النجاح
    if score_percent >= 50:
        status = "pass"
    else:
        status = "fail"
    
    students_data.append({
        "student": attempt.student,
        "score": attempt.score,
        "score_percent": score_percent,
        "status": status,
    })

# حساب المعدل
average_score = sum(s["score_percent"] for s in students_data) / len(students_data)
pass_count = sum(1 for s in students_data if s["status"] == "pass")
pass_rate = (pass_count / len(students_data)) * 100
```

#### 6.4 توزيع الدرجات
```python
# في core/views.py - teacher_exam_results
buckets_def = [
    {"label": "0-50", "min": 0, "max": 50, "bg_class": "bg-red-500"},
    {"label": "50-75", "min": 50, "max": 75, "bg_class": "bg-amber-500"},
    {"label": "75-90", "min": 75, "max": 90, "bg_class": "bg-blue-500"},
    {"label": ">90", "min": 90, "max": 101, "bg_class": "bg-emerald-500"},
]

grade_distribution = []
for bucket in buckets_def:
    count = sum(
        1 for s in students_data
        if bucket["min"] <= s["score_percent"] < bucket["max"]
    )
    percentage = (count / len(students_data)) * 100 if students_data else 0
    
    grade_distribution.append({
        "label": bucket["label"],
        "count": count,
        "percentage": percentage,
        "bg_class": bucket["bg_class"],
    })
```

**الآلية:**
- **Auto-grading:** مقارنة الإجابة المختارة مع الإجابة الصحيحة
- **Manual grading:** واجهة للمدرس لإدخال العلامات
- **Statistics:** حسابات معقدة باستخدام Django ORM aggregations
- **Visualization:** عرض البيانات في charts و graphs

---

## 👥 7. نظام إدارة المواد والمجموعات

### المميزات:
- **مواد دراسية** مع صور وأوصاف
- **مجموعات طلابية** لكل مادة
- **طلبات انضمام** (Join Requests)
- **دعوات من المدرس** (Invitations)
- **محادثات جماعية** داخل المجموعات

### كيفية البرمجة:

#### 7.1 نموذج المواد
```python
# في core/models.py
class Subject(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="subject_images/", blank=True)
    students = models.ManyToManyField(
        User,
        related_name="enrolled_subjects",
        blank=True
    )
```

#### 7.2 نموذج المجموعات
```python
class Group(models.Model):
    name = models.CharField(max_length=255)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="groups"
    )
    teacher = models.ForeignKey(User, on_delete=models.CASCADE)
    students = models.ManyToManyField(
        User,
        related_name="student_groups",
        blank=True
    )
```

#### 7.3 نظام طلبات الانضمام
```python
class StudentJoinRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
    
    class Source(models.TextChoices):
        FROM_STUDENT = "from_student", "From student"
        FROM_TEACHER = "from_teacher", "From teacher"
    
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Status.choices)
    source = models.CharField(max_length=20, choices=Source.choices)
```

#### 7.4 قبول/رفض الطلبات
```python
# في core/views.py
@login_required
@user_passes_test(is_teacher)
def teacher_subject_request_action(request, subject_id, request_id, action):
    join_request = get_object_or_404(
        StudentJoinRequest,
        id=request_id,
        subject_id=subject_id
    )
    
    if action == "accept":
        join_request.status = StudentJoinRequest.Status.ACCEPTED
        join_request.save()
        
        # إضافة الطالب للمادة
        subject.students.add(join_request.student)
        
        messages.success(request, "تم قبول الطلب بنجاح")
    
    elif action == "reject":
        join_request.status = StudentJoinRequest.Status.REJECTED
        join_request.save()
        
        messages.info(request, "تم رفض الطلب")
```

#### 7.5 المحادثات الجماعية
```python
class GroupMessage(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["created_at"]
```

**الآلية:**
- **Many-to-Many:** علاقة بين المواد والطلاب
- **Join Requests:** نظام موافقة/رفض
- **Real-time Chat:** تحديث تلقائي للرسائل
- **Permissions:** التحقق من الصلاحيات قبل كل عملية

---

## 🎨 8. واجهة المستخدم المتقدمة

### المميزات:
- **تصميم عصري** باستخدام Tailwind CSS
- **وضع مظلم** (Dark Mode)
- **تصميم متجاوب** (Responsive)
- **رسوم متحركة** (Animations)
- **أيقونات Material Symbols**

### كيفية البرمجة:

#### 8.1 إعداد Tailwind CSS
```html
<!-- في base.html -->
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {
    darkMode: "class",
    theme: {
      extend: {
        colors: {
          primary: "#1d72eb",
          secondary: "#101827",
          "background-light": "#ffffff",
          "background-dark": "#0f172a",
          "surface-light": "#f3f4f6",
          "surface-dark": "#1e293b",
        },
        fontFamily: {
          display: ["Cairo", "sans-serif"],
          body: ["Cairo", "sans-serif"],
        },
      },
    },
  };
</script>
```

#### 8.2 الوضع المظلم
```javascript
// Toggle dark mode
document.querySelector('[aria-label="Toggle theme"]').addEventListener('click', function() {
    document.documentElement.classList.toggle('dark');
    
    // حفظ التفضيل
    localStorage.setItem('theme', 
        document.documentElement.classList.contains('dark') ? 'dark' : 'light'
    );
});

// تحميل التفضيل
if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.classList.add('dark');
}
```

#### 8.3 التصميم المتجاوب
```html
<!-- مثال من teacher_exams.html -->
<div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
    <!-- محتوى يتغير حسب حجم الشاشة -->
</div>

<!-- Sidebar يختفي على الشاشات الصغيرة -->
<aside class="hidden lg:flex w-64 bg-white dark:bg-surface-dark">
    <!-- ... -->
</aside>

<!-- زر القائمة يظهر على الشاشات الصغيرة -->
<button class="lg:hidden p-2" data-sidebar-toggle>
    <span class="material-symbols-rounded">menu</span>
</button>
```

#### 8.4 الرسوم المتحركة
```html
<!-- Transitions -->
<button class="transition-all duration-300 hover:scale-105">
    انقر هنا
</button>

<!-- Hover effects -->
<div class="hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
    <!-- ... -->
</div>

<!-- Loading states -->
<div class="animate-pulse">
    <div class="h-4 bg-slate-200 rounded w-3/4"></div>
</div>
```

**الآلية:**
- **Tailwind CDN:** تحميل سريع وسهل
- **Utility Classes:** بناء سريع للواجهات
- **Dark Mode:** باستخدام `class` strategy
- **Responsive:** breakpoints (sm, md, lg, xl)

---

## 📈 9. نظام التقارير والإحصائيات

### المميزات:
- **تقارير شاملة** للمدرسين
- **إحصائيات متقدمة** للمديرين
- **رسوم بيانية** تفاعلية
- **تصدير البيانات** (قابل للتطوير)

### كيفية البرمجة:

#### 9.1 إحصائيات المدرس
```python
# في core/views.py - teacher_reports
@login_required
@user_passes_test(is_teacher)
def teacher_reports(request):
    user = request.user
    
    # إجمالي الاختبارات
    total_exams = Exam.objects.filter(teacher=user).count()
    
    # الاختبارات النشطة
    active_exams = Exam.objects.filter(
        teacher=user,
        status=Exam.Status.ONGOING
    ).count()
    
    # إجمالي الطلاب
    subjects = Subject.objects.filter(teacher=user)
    total_students = User.objects.filter(
        enrolled_subjects__in=subjects
    ).distinct().count()
    
    # متوسط الدرجات
    all_attempts = StudentExam.objects.filter(
        exam__teacher=user,
        status=StudentExam.Status.FINISHED
    )
    
    if all_attempts.exists():
        avg_score = all_attempts.aggregate(
            avg=Avg('score')
        )['avg'] or 0
    else:
        avg_score = 0
    
    # أداء الطلاب بمرور الوقت
    monthly_performance = []
    for month in range(1, 13):
        attempts = all_attempts.filter(
            finished_at__month=month
        )
        if attempts.exists():
            avg = attempts.aggregate(avg=Avg('score'))['avg']
            monthly_performance.append({
                'month': month,
                'average': float(avg)
            })
```

#### 9.2 إحصائيات المدير
```python
# في core/views.py - admin_analytics
@login_required
@user_passes_test(is_admin)
def admin_analytics(request):
    # إحصائيات عامة
    total_users = User.objects.count()
    total_teachers = User.objects.filter(role='teacher').count()
    total_students = User.objects.filter(role='student').count()
    total_exams = Exam.objects.count()
    
    # نمو المستخدمين
    user_growth = []
    for month in range(1, 13):
        count = User.objects.filter(
            date_joined__month=month
        ).count()
        user_growth.append({
            'month': month,
            'count': count
        })
    
    # الاختبارات حسب الحالة
    exams_by_status = []
    for status in Exam.Status:
        count = Exam.objects.filter(status=status.value).count()
        exams_by_status.append({
            'status': status.label,
            'count': count
        })
```

**الآلية:**
- **Django ORM:** استخدام aggregations (Count, Avg, Sum)
- **Filtering:** تصفية البيانات حسب التاريخ والحالة
- **Annotations:** إضافة حقول محسوبة
- **Visualization:** تمرير البيانات إلى JavaScript charts

---

## 🔄 10. نظام التحديث في الوقت الفعلي

### المميزات:
- **تحديث تلقائي** لصفحة المراقبة
- **حالة الطلاب** (Active, Offline, Submitted)
- **سجل الأحداث** المباشر
- **الوقت المتبقي** الديناميكي

### كيفية البرمجة:

#### 10.1 API Endpoint للبيانات
```python
# في core/views.py
@login_required
@user_passes_test(is_teacher)
def teacher_exam_monitor_data(request, exam_id):
    """
    API endpoint يرجع بيانات المراقبة بصيغة JSON
    """
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    
    # جمع البيانات
    attempts = StudentExam.objects.filter(exam=exam)
    
    students_data = []
    for attempt in attempts:
        students_data.append({
            'student_id': attempt.student.id,
            'name': attempt.student.full_name,
            'status': get_student_status(attempt),
            'progress': calculate_progress(attempt),
        })
    
    return JsonResponse({
        'students': students_data,
        'stats': calculate_stats(exam),
        'activity_log': get_recent_events(exam),
    })
```

#### 10.2 التحديث التلقائي (Frontend)
```javascript
// في teacher_exam_monitor.html
function refreshData() {
    fetch("{% url 'teacher_exam_monitor_data' exam.id %}")
        .then(response => response.json())
        .then(data => {
            // تحديث إحصائيات
            document.getElementById('active-count').textContent = 
                data.stats.active_students;
            document.getElementById('submitted-count').textContent = 
                data.stats.submitted;
            
            // تحديث قائمة الطلاب
            updateStudentsList(data.students);
            
            // تحديث سجل الأحداث
            updateActivityLog(data.activity_log);
        });
}

// تحديث كل 5 ثوانٍ
setInterval(refreshData, 5000);
```

#### 10.3 تحديد حالة الطالب
```python
def get_student_status(attempt):
    """
    تحديد حالة الطالب (نشط، غير متصل، سلّم)
    """
    now = timezone.now()
    stale_seconds = 45
    
    if attempt.status == StudentExam.Status.FINISHED:
        return "submitted"
    
    if attempt.status == StudentExam.Status.IN_PROGRESS:
        last_activity = attempt.last_activity_at or attempt.started_at
        if last_activity:
            time_diff = (now - last_activity).total_seconds()
            if time_diff <= stale_seconds:
                return "active"
    
    return "offline"
```

**الآلية:**
- **AJAX Polling:** طلب البيانات كل 5 ثوانٍ
- **JSON API:** endpoint يرجع بيانات بصيغة JSON
- **DOM Updates:** تحديث العناصر بدون إعادة تحميل الصفحة
- **Activity Tracking:** تحديث `last_activity_at` عند كل إجراء

---

## 🛡️ 11. نظام الصلاحيات والأمان

### المميزات:
- **فصل الأدوار** (Role-based Access Control)
- **حماية CSRF**
- **SQL Injection Prevention**
- **XSS Protection**

### كيفية البرمجة:

#### 11.1 نموذج المستخدم
```python
# في accounts/models.py
class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]
    
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='student'
    )
    full_name = models.CharField(max_length=255, blank=True)
```

#### 11.2 دوال التحقق من الصلاحيات
```python
# في core/views.py
def is_admin(user):
    return user.is_staff

def is_teacher(user):
    return getattr(user, "role", None) == "teacher"

def is_student(user):
    return getattr(user, "role", None) == "student"
```

#### 11.3 حماية الصفحات
```python
@login_required
@user_passes_test(is_teacher)
def teacher_dashboard(request):
    # فقط المدرسون يمكنهم الوصول
    pass

@login_required
@user_passes_test(is_student)
def student_dashboard(request):
    # فقط الطلاب يمكنهم الوصول
    pass
```

#### 11.4 حماية CSRF
```html
<!-- في كل نموذج -->
<form method="post">
    {% csrf_token %}
    <!-- ... -->
</form>
```

```javascript
// في AJAX requests
fetch(url, {
    method: 'POST',
    headers: {
        'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify(data)
})
```

#### 11.5 منع SQL Injection
```python
# ✅ صحيح - استخدام Django ORM
exams = Exam.objects.filter(teacher=user, status='ongoing')

# ❌ خطأ - استخدام SQL مباشر
# exams = Exam.objects.raw(f"SELECT * FROM exam WHERE teacher_id = {user.id}")
```

#### 11.6 منع XSS
```html
<!-- Django يقوم بـ auto-escape تلقائياً -->
<p>{{ user_input }}</p>  <!-- آمن -->

<!-- استخدام |safe فقط للمحتوى الموثوق -->
<div>{{ trusted_html|safe }}</div>
```

**الآلية:**
- **Decorators:** `@login_required`, `@user_passes_test`
- **Django ORM:** يمنع SQL injection تلقائياً
- **Template Auto-escape:** يمنع XSS تلقائياً
- **CSRF Tokens:** حماية من CSRF attacks

---

## 📱 12. التصميم المتجاوب (Responsive Design)

### المميزات:
- **يعمل على جميع الأجهزة** (Desktop, Tablet, Mobile)
- **قوائم متكيفة** (Adaptive Menus)
- **جداول متجاوبة** (Responsive Tables)
- **نماذج محسّنة** للموبايل

### كيفية البرمجة:

#### 12.1 Breakpoints في Tailwind
```html
<!-- مثال: Sidebar -->
<aside class="
    hidden          <!-- مخفي على الموبايل -->
    lg:flex         <!-- يظهر على الشاشات الكبيرة -->
    w-64 
    bg-white
">
    <!-- محتوى الـ sidebar -->
</aside>

<!-- زر القائمة للموبايل -->
<button class="
    lg:hidden       <!-- يختفي على الشاشات الكبيرة -->
    p-2
" data-sidebar-toggle>
    <span class="material-symbols-rounded">menu</span>
</button>
```

#### 12.2 الجداول المتجاوبة
```html
<div class="overflow-x-auto">
    <table class="w-full text-right text-sm">
        <thead>
            <tr>
                <th class="px-6 py-4 min-w-[200px]">تفاصيل الاختبار</th>
                <th class="px-6 py-4">المادة</th>
                <!-- ... -->
            </tr>
        </thead>
        <tbody>
            <!-- ... -->
        </tbody>
    </table>
</div>
```

#### 12.3 النماذج المتجاوبة
```html
<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <!-- عمود واحد على الموبايل، عمودين على الشاشات المتوسطة -->
    <div>
        <label>اسم الاختبار</label>
        <input type="text" class="w-full">
    </div>
    <div>
        <label>المادة</label>
        <select class="w-full">
            <!-- ... -->
        </select>
    </div>
</div>
```

#### 12.4 JavaScript للقائمة المتجاوبة
```javascript
// في teacher_exams.html
document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.querySelector("[data-sidebar-toggle]");
    var sidebar = document.querySelector("[data-admin-sidebar]");
    
    if (!toggle || !sidebar) return;
    
    toggle.addEventListener("click", function () {
        // فقط على الشاشات الصغيرة
        if (window.innerWidth >= 1024) return;
        
        sidebar.classList.toggle("hidden");
    });
});
```

**الآلية:**
- **Mobile-first:** البداية من الموبايل ثم التوسع
- **Breakpoints:** sm (640px), md (768px), lg (1024px), xl (1280px)
- **Flexbox & Grid:** لتخطيط مرن
- **JavaScript:** لإظهار/إخفاء القوائم

---

## 🎯 الخلاصة

### أهم التقنيات المستخدمة:

1. **Backend:**
   - Django 4.x
   - Django ORM
   - Django Authentication
   - Django Messages Framework

2. **Frontend:**
   - Tailwind CSS
   - Vanilla JavaScript
   - AJAX/Fetch API
   - Material Symbols Icons

3. **Security:**
   - CSRF Protection
   - SQL Injection Prevention
   - XSS Protection
   - 2FA Authentication

4. **Database:**
   - SQLite (Development)
   - PostgreSQL (Production - قابل للتطوير)

### أبرز المميزات:

✅ **نظام مصادقة متقدم** مع 2FA
✅ **مراقبة في الوقت الفعلي** للاختبارات
✅ **كشف الغش** التلقائي
✅ **تصحيح ذكي** (تلقائي + يدوي)
✅ **واجهة عصرية** مع وضع مظلم
✅ **تصميم متجاوب** لجميع الأجهزة
✅ **إحصائيات وتقارير** شاملة
✅ **نظام مواد ومجموعات** متكامل

### نقاط القوة:

1. **الأمان:** حماية متعددة الطبقات
2. **الأداء:** استخدام فعال للـ ORM
3. **التوسع:** بنية قابلة للتطوير
4. **التجربة:** واجهة سهلة وجذابة
5. **الموثوقية:** معالجة شاملة للأخطاء

---

## 📝 ملاحظات للتطوير المستقبلي

### مميزات مقترحة:

1. **WebSockets** للتحديث الفوري بدلاً من polling
2. **تصدير النتائج** إلى Excel/PDF
3. **إشعارات Push** للطلاب والمدرسين
4. **تحليلات AI** لأداء الطلاب
5. **مراقبة الكاميرا** للحماية من الغش
6. **بنك أسئلة ذكي** مع توليد اختبارات تلقائي
7. **دعم اللغات المتعددة** (i18n)
8. **API RESTful** للتكامل مع أنظمة أخرى

---

**تم إنشاء هذا المستند في:** 2026-01-10
**الإصدار:** 1.0
**المطور:** Examination System Team



