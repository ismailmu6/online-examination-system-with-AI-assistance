from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Sum
from .models import (
    Group,
    Exam,
    SystemSettings,
    Subject,
    Question,
    QuestionChoice,
    ExamQuestion,
    StudentExam,
    StudentAnswer,
    ExamEvent,
    ExamNotification,
    GroupMessage,
    StudentJoinRequest,
    Message,
)
from accounts.models import TeacherNotificationSettings
from django.conf import settings
import json
import urllib.request
import urllib.error
import socket
import logging

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    import docx
except ImportError:
    docx = None

User = get_user_model()
logger = logging.getLogger(__name__)


# --- وظائف مساعدة (Utility Functions) ---

def _sync_exam_statuses(exams_queryset):
    """
    تحديث حالات الاختبارات تلقائياً بناءً على الوقت الحالي.
    تنتقل الحالة من 'مجدول' إلى 'جارٍ' ثم 'منتهٍ' حسب وقت البداية والنهاية.
    الاختبار يبقى في حالة مسودة إذا لم يكن له طلاب أو أسئلة.
    """
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.now()
    updated_count = 0
    
    for exam in exams_queryset:
        # Check if exam is complete (has questions and students)
        has_questions = hasattr(exam, 'questions_count') and exam.questions_count > 0
        has_students = (
            (hasattr(exam, 'allowed_students_count') and exam.allowed_students_count > 0) or
            (hasattr(exam, 'total_participants_display') and exam.total_participants_display > 0) or
            exam.allowed_students.exists()
        )
        
        # Keep as DRAFT if exam is not complete
            
        if not exam.start_time or not exam.duration_minutes:
            desired_status = Exam.Status.DRAFT
        elif not has_questions or not has_students:
            # Keep as DRAFT if no questions or students
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
            updated_count += 1
    
    return updated_count


# --- واجهات التحكم في الوصول (Access Control) ---

def home(request):
    """توجيه المستخدم إلى صفحة تسجيل الدخول عند الدخول للرابط الرئيسي."""
    return redirect("login")


def is_admin(user):
    """التحقق مما إذا كان المستخدم مديراً للنظام."""
    return user.is_staff


def is_teacher(user):
    """التحقق مما إذا كان المستخدم يمتلك صلاحية مدرس."""
    return getattr(user, "role", None) == "teacher"


def is_student(user):
    """التحقق مما إذا كان المستخدم طالباً."""
    return getattr(user, "role", None) == "student"


# --- قسم مدير النظام (Admin Section) ---

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    """
    لوحة تحكم مدير النظام: تعرض إحصائيات عامة حول المستخدمين والاختبارات النشطة.
    """
    total_users = User.objects.count()
    blocked_users = User.objects.filter(is_active=False).count()
    students_count = User.objects.filter(role="student").count()
    teachers_count = User.objects.filter(role="teacher").count()
    latest_exams_qs = Exam.objects.select_related("teacher").annotate(
        questions_count=Count("exam_questions", distinct=True),
        allowed_students_count=Count("allowed_students", distinct=True)
    ).order_by("-start_time")[:5]
    _sync_exam_statuses(latest_exams_qs)
    active_tests = Exam.objects.filter(
        status__in=[Exam.Status.SCHEDULED, Exam.Status.ONGOING]
    ).count()
    latest_exams = latest_exams_qs
    context = {
        "total_users": total_users,
        "blocked_users": blocked_users,
        "students_count": students_count,
        "teachers_count": teachers_count,
        "active_tests": active_tests,
        "latest_exams": latest_exams,
    }
    return render(request, "core/admin_dashboard.html", context)


class TeacherCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "full_name", "email")


class AdminUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "full_name", "email", "role")


@login_required
@user_passes_test(is_admin)
def admin_users(request):
    if request.method == "POST":
        user_id = request.POST.get("user_id")
        action = request.POST.get("action")
        try:
            target = User.objects.get(id=user_id)
            if target.is_superuser:
                messages.error(request, "لا يمكن تعديل حالة المشرف الرئيسي.", extra_tags="user:admin")
            elif target == request.user and action in ["toggle_block", "delete"]:
                messages.error(request, "لا يمكنك حظر أو حذف حسابك الحالي.", extra_tags="user:admin")
            elif action == "toggle_block":
                target.is_active = not target.is_active
                target.save()
                if target.is_active:
                    messages.success(request, "تم إلغاء حظر المستخدم بنجاح.", extra_tags="user:admin")
                else:
                    messages.success(request, "تم حظر المستخدم بنجاح.", extra_tags="user:admin")
            elif action == "delete":
                try:
                    target.delete()
                    messages.success(request, "تم حذف المستخدم بنجاح.", extra_tags="user:admin")
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error deleting user {user_id}: {str(e)}")
                    messages.error(request, f"فشل حذف المستخدم: {str(e)}", extra_tags="user:admin")
        except User.DoesNotExist:
            messages.error(request, "المستخدم غير موجود.", extra_tags="user:admin")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error in admin_users POST: {str(e)}")
            messages.error(request, f"حدث خطأ غير متوقع: {str(e)}", extra_tags="user:admin")
        return redirect("admin_users")

    users = User.objects.all()

    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(
            Q(full_name__icontains=query)
            | Q(username__icontains=query)
            | Q(email__icontains=query)
        )

    selected_role = request.GET.get("role", "").strip()
    if selected_role == "admin":
        users = users.filter(is_superuser=True)
    elif selected_role:
        users = users.filter(role=selected_role)

    users = users.order_by("-date_joined")

    total_users = User.objects.count()
    blocked_users = User.objects.filter(is_active=False).count()
    active_users = User.objects.filter(is_active=True).count()

    context = {
        "users": users,
        "total_users": total_users,
        "blocked_users": blocked_users,
        "active_users": active_users,
        "query": query,
        "selected_role": selected_role,
    }
    return render(request, "core/admin_users.html", context)


@login_required
@user_passes_test(is_admin)
def admin_user_create(request):
    if request.method == "POST":
        form = AdminUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = True
            user.save()
            messages.success(request, "تم إنشاء حساب المستخدم بنجاح.", extra_tags="user:admin")
            return redirect("admin_users")
    else:
        form = AdminUserCreationForm()

    return render(request, "core/admin_user_create.html", {"form": form})


@login_required
@user_passes_test(is_admin)
def admin_teachers(request):
    teachers = (
        User.objects.filter(role="teacher")
        .annotate(
            groups_count=Count("teaching_groups", distinct=True),
            subjects_count=Count("subjects", distinct=True),
            exams_count=Count("exams", distinct=True),
            questions_count=Count("questions", distinct=True),
        )
        .order_by("-date_joined")
    )

    total_teachers = teachers.count()
    active_teachers = teachers.filter(is_active=True).count()
    blocked_teachers = teachers.filter(is_active=False).count()

    context = {
        "teachers": teachers,
        "total_teachers": total_teachers,
        "active_teachers": active_teachers,
        "blocked_teachers": blocked_teachers,
    }
    return render(request, "core/admin_teachers.html", context)


@login_required
@user_passes_test(is_admin)
def admin_teacher_create(request):
    if request.method == "POST":
        form = TeacherCreationForm(request.POST)
        if form.is_valid():
            teacher = form.save(commit=False)
            teacher.role = "teacher"  # تعيين دور المدرس مباشرة
            teacher.is_active = True
            teacher.save()
            messages.success(request, "تم إنشاء حساب المدرس بنجاح.", extra_tags="user:admin")
            return redirect("admin_teachers")
    else:
        form = TeacherCreationForm()

    return render(request, "core/admin_teacher_create.html", {"form": form})


@login_required
@user_passes_test(is_admin)
def admin_groups(request):
    query = request.GET.get("q", "").strip()
    selected_teacher = request.GET.get("teacher", "").strip()

    groups = Group.objects.select_related("teacher").annotate(
        student_count=Count("students")
    )

    if query:
        groups = groups.filter(Q(name__icontains=query) | Q(code__icontains=query))

    if selected_teacher:
        groups = groups.filter(teacher__id=selected_teacher)

    total_groups = Group.objects.count()
    total_students_in_groups = (
        User.objects.filter(student_groups__isnull=False).distinct().count()
    )

    teachers = User.objects.filter(role="teacher").order_by("full_name", "username")

    context = {
        "groups": groups,
        "total_groups": total_groups,
        "total_students_in_groups": total_students_in_groups,
        "teachers": teachers,
        "query": query,
        "selected_teacher": selected_teacher,
    }
    return render(request, "core/admin_groups.html", context)


@login_required
@user_passes_test(is_admin)
def admin_exams(request):
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_teacher = request.GET.get("teacher", "").strip()

    exams = (
        Exam.objects.select_related("teacher")
        .annotate(
            questions_count=Count("exam_questions", distinct=True),
            submitted_attempts_count=Count(
                "attempts",
                filter=Q(attempts__status__in=[StudentExam.Status.FINISHED, StudentExam.Status.FAILED_CHEATING]),
                distinct=True
            ),
            allowed_students_count=Count("allowed_students", distinct=True)
        )
        .order_by("-created_at")
    )

    if query:
        exams = exams.filter(title__icontains=query)

    if selected_status:
        exams = exams.filter(status=selected_status)

    if selected_teacher:
        exams = exams.filter(teacher__id=selected_teacher)

    # Calculate total_participants_display for each exam
    for exam in exams:
        if exam.allowed_students_count > 0:
            exam.total_participants_display = exam.allowed_students_count
        else:
            exam.total_participants_display = exam.total_participants or 0

    total_exams = Exam.objects.count()
    scheduled_exams = Exam.objects.filter(status=Exam.Status.SCHEDULED).count()
    finished_exams = Exam.objects.filter(status=Exam.Status.FINISHED).count()

    teachers = User.objects.filter(role="teacher").order_by("full_name", "username")

    context = {
        "exams": exams,
        "total_exams": total_exams,
        "scheduled_exams": scheduled_exams,
        "finished_exams": finished_exams,
        "teachers": teachers,
        "query": query,
        "selected_status": selected_status,
        "selected_teacher": selected_teacher,
    }
    return render(request, "core/admin_exams.html", context)


@login_required
@user_passes_test(is_admin)
def admin_exam_monitor(request, exam_id):
    """
    صفحة مراقبة الاختبار للأدمن (قراءة فقط)
    """
    user = request.user
    exam = get_object_or_404(Exam, id=exam_id)
    
    attempts_qs = StudentExam.objects.filter(exam=exam).select_related("student")
    
    total_students = exam.allowed_students.count() if exam.allowed_students.exists() else (exam.total_participants or attempts_qs.count())
    
    submitted = attempts_qs.filter(
        status__in=[StudentExam.Status.FINISHED, StudentExam.Status.FAILED_CHEATING]
    ).count()
    
    from django.utils import timezone as _tz_mon
    now = _tz_mon.now()
    stale_seconds = 45
    from datetime import timedelta
    in_progress_qs = attempts_qs.filter(status=StudentExam.Status.IN_PROGRESS)
    active_students = in_progress_qs.filter(last_activity_at__gte=now - timedelta(seconds=stale_seconds)).count()
    started_students = attempts_qs.values_list("student_id", flat=True).distinct().count()
    absent = max(total_students - started_students, 0)
    suspicions = ExamEvent.objects.filter(
        exam=exam,
        event_type__in=[
            ExamEvent.EventType.CHEATING_VISIBILITY,
            ExamEvent.EventType.CHEATING_CLIPBOARD,
        ],
    ).count()
    
    stats = {
        "total_students": total_students,
        "active_students": active_students,
        "submitted": submitted,
        "absent": absent,
        "suspicions": suspicions,
    }
    
    remaining_time_display = "--:--"
    computed_end_time = exam.end_time
    if computed_end_time is None:
        from datetime import timedelta
        computed_end_time = exam.start_time + timedelta(minutes=exam.duration_minutes)
    remaining = computed_end_time - now
    if remaining.total_seconds() > 0:
        total_seconds = int(remaining.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        remaining_time_display = f"{minutes:02d}:{seconds:02d}"
    else:
        remaining_time_display = "00:00"
    
    # Get student tiles with details
    student_tiles = []
    
    # Create a dictionary of attempts by student_id
    attempts_dict = {attempt.student_id: attempt for attempt in attempts_qs}
    
    # Get all allowed students
    allowed_students = exam.allowed_students.all()
    
    for student in allowed_students:
        attempt = attempts_dict.get(student.id)
        
        if attempt:
            is_active = attempt.status == StudentExam.Status.IN_PROGRESS and attempt.last_activity_at and (now - attempt.last_activity_at).total_seconds() < stale_seconds
            
            # Count cheating events for this student
            cheating_count = ExamEvent.objects.filter(
                exam=exam,
                student=student,
                event_type__in=[
                    ExamEvent.EventType.CHEATING_VISIBILITY,
                    ExamEvent.EventType.CHEATING_CLIPBOARD,
                ],
            ).count()
            
            # Calculate progress
            total_questions = exam.exam_questions.count()
            answered_questions = StudentAnswer.objects.filter(attempt=attempt).exclude(text_answer="", selected_choice=None).count()
            progress = round((answered_questions / total_questions * 100) if total_questions > 0 else 0)
            
            # Last activity
            if attempt.last_activity_at:
                time_diff = (now - attempt.last_activity_at).total_seconds()
                if time_diff < 60:
                    last_activity = "الآن"
                elif time_diff < 3600:
                    last_activity = f"منذ {int(time_diff / 60)} دقيقة"
                else:
                    last_activity = f"منذ {int(time_diff / 3600)} ساعة"
            else:
                last_activity = "-"
            
            status = attempt.status
        else:
            # Student hasn't started yet
            is_active = False
            cheating_count = 0
            progress = 0
            last_activity = "-"
            status = "not_started"
        
        student_tiles.append({
            "student_id": student.id,
            "student_name": student.full_name or student.username,
            "student_code": student.username,
            "status": status,
            "is_active": is_active,
            "progress": progress,
            "last_activity": last_activity,
            "cheating_count": cheating_count,
        })
    
    context = {
        "exam": exam,
        "stats": stats,
        "students": student_tiles,
        "remaining_time_display": remaining_time_display,
    }
    return render(request, "core/admin_exam_monitor.html", context)


@login_required
@user_passes_test(is_admin)
def admin_exam_results(request, exam_id):
    """
    صفحة عرض النتائج للأدمن (قراءة فقط)
    """
    from django.utils import timezone
    from datetime import timedelta
    
    exam = get_object_or_404(Exam.objects.select_related('teacher', 'subject'), id=exam_id)
    
    # Calculate actual total mark from exam questions
    total_mark_sum = (
        ExamQuestion.objects.filter(exam=exam).aggregate(total=Sum("mark"))["total"]
        or 0
    )
    
    # Check if exam time has expired
    now = timezone.now()
    exam_end_time = exam.end_time or (exam.start_time + timedelta(minutes=exam.duration_minutes) if exam.start_time and exam.duration_minutes else None)
    exam_has_expired = exam_end_time and now > exam_end_time

    # Get all allowed students for this exam
    allowed_students = exam.allowed_students.all().select_related()
    
    # Get all attempts for this exam
    attempts_dict = {}
    attempts_qs = StudentExam.objects.filter(exam=exam).select_related("student")
    for attempt in attempts_qs:
        attempts_dict[attempt.student_id] = attempt

    avatar_styles = [
        "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
        "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
        "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
        "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
        "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
    ]

    students = []
    highest_score = 0  # Track highest score
    
    for index, student in enumerate(allowed_students, start=1):
        name = student.full_name or student.username
        parts = [p for p in (name or "").split() if p]
        initials = "".join(p[0] for p in parts[:2]) if parts else (name[:2] if name else "")

        attempt = attempts_dict.get(student.id)
        
        if attempt and attempt.status != StudentExam.Status.IN_PROGRESS:
            score = float(attempt.score or 0)
            if score > highest_score:
                highest_score = score
            if total_mark_sum > 0:
                score_percent = round((score / float(total_mark_sum)) * 100)
            else:
                score_percent = 0
        else:
            score = None
            score_percent = 0

        if score_percent >= 90:
            score_bar_class = "bg-emerald-500"
        elif score_percent >= 50:
            score_bar_class = "bg-blue-500"
        else:
            score_bar_class = "bg-red-500"

        style = avatar_styles[(index - 1) % len(avatar_styles)]
        style_parts = style.split()
        avatar_bg = " ".join(style_parts[:-2])
        avatar_text = " ".join(style_parts[-2:])

        if attempt and attempt.started_at and attempt.finished_at:
            delta = attempt.finished_at - attempt.started_at
            minutes = max(int(delta.total_seconds() // 60), 0)
            hours = minutes // 60
            minutes = minutes % 60
            if hours:
                time_spent_display = f"{hours}س {minutes:02d}د"
            else:
                time_spent_display = f"{minutes} دقيقة"
            finished_time = attempt.finished_at.strftime("%I:%M %p")
        else:
            time_spent_display = "--"
            finished_time = None

        # Determine student status
        pass_mark = exam.pass_mark if hasattr(exam, 'pass_mark') and exam.pass_mark else 50
        if not attempt:
            # If exam has expired and student didn't start, mark as failed
            if exam_has_expired:
                status = "absent_fail"
            else:
                status = "not_started"
        elif attempt.status == StudentExam.Status.IN_PROGRESS:
            status = "pending"
        else:
            status = "pass" if score_percent >= pass_mark else "fail"
        
        # Get cheating count
        cheating_count = 0
        if attempt:
            cheating_count = ExamEvent.objects.filter(
                exam=exam,
                student=student,
                event_type__in=[
                    ExamEvent.EventType.CHEATING_VISIBILITY,
                    ExamEvent.EventType.CHEATING_CLIPBOARD,
                ]
            ).count()

        students.append(
            {
                "id": student.id,
                "name": name,
                "code": student.username,
                "initials": initials,
                "cheating_count": cheating_count,
                "score": score,
                "score_percent": score_percent,
                "score_bar_class": score_bar_class,
                "avatar_bg": avatar_bg,
                "avatar_text": avatar_text,
                "time_spent_display": time_spent_display,
                "finished_time": finished_time,
                "status": status,
            }
        )

    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()

    filtered_students = []
    for s in students:
        if query and query not in s["name"]:
            continue
        if selected_status:
            if selected_status == "pass" and s["status"] != "pass":
                continue
            if selected_status == "fail" and s["status"] != "fail":
                continue
        filtered_students.append(s)

    # عرض جميع الطلاب بدون pagination
    students_page = filtered_students
    total_items = len(filtered_students)

    pagination = {
        "start_index": 1 if total_items > 0 else 0,
        "end_index": total_items,
        "total_items": total_items,
    }

    # Include both students with scores and absent students in calculations
    graded_students = [s for s in students if s["score"] is not None]
    absent_students = [s for s in students if s["status"] == "absent_fail"]
    
    # For statistics, count absent students as failed
    total_evaluated = len(graded_students) + len(absent_students)
    
    if total_evaluated > 0:
        if graded_students:
            average_score_percent = round(
                sum(s["score_percent"] for s in graded_students) / len(graded_students)
            )
        else:
            average_score_percent = 0
        
        pass_count = sum(1 for s in graded_students if s["status"] == "pass")
        # Absent students count as failed
        pass_rate = round((pass_count / total_evaluated) * 100)
    else:
        average_score_percent = 0
        pass_rate = 0

    students_total = total_evaluated
    
    # students_registered is the total number of allowed students
    students_registered = len(students)

    summary = {
        "average_score_percent": average_score_percent,
        "pass_rate": pass_rate,
        "students_total": students_total,
        "students_registered": students_registered,
    }

    buckets_def = [
        {"label": "0-50", "min": 0, "max": 50, "bg_class": "bg-red-500"},
        {"label": "50-75", "min": 50, "max": 75, "bg_class": "bg-amber-500"},
        {"label": "75-90", "min": 75, "max": 90, "bg_class": "bg-blue-500"},
        {"label": ">90", "min": 90, "max": 101, "bg_class": "bg-emerald-500"},
    ]

    grade_distribution = []
    total_graded = len(graded_students)
    for bucket in buckets_def:
        if total_graded:
            count = sum(
                1
                for s in graded_students
                if bucket["min"] <= s["score_percent"] < bucket["max"]
            )
            percent = round((count / total_graded) * 100) if count else 0
        else:
            percent = 0
        height = percent if percent > 0 else 8
        grade_distribution.append(
            {
                "label": bucket["label"],
                "percent": percent,
                "height": height,
                "bg_class": bucket["bg_class"],
            }
        )

    top_wrong_questions = []
    exam_questions = list(
        ExamQuestion.objects.filter(exam=exam).select_related("question")
    )
    # Total attempts that are finished
    finished_attempts_count = StudentExam.objects.filter(
        exam=exam, status=StudentExam.Status.FINISHED
    ).count()

    for eq in exam_questions:
        if finished_attempts_count == 0:
            continue
            
        # Correct answers for this question in finished attempts
        correct_answers_count = StudentAnswer.objects.filter(
            attempt__exam=exam, 
            attempt__status=StudentExam.Status.FINISHED,
            exam_question=eq, 
            is_correct=True
        ).count()
        
        # Wrong answers = Total finished attempts - Correct answers
        wrong_answers = finished_attempts_count - correct_answers_count
        
        if wrong_answers == 0:
            continue
            
        wrong_percent = round((wrong_answers / finished_attempts_count) * 100)
        text = eq.question.text[:100]
        top_wrong_questions.append(
            {
                "index": eq.order or len(top_wrong_questions) + 1,
                "text": text,
                "wrong_percent": wrong_percent,
            }
        )
    top_wrong_questions.sort(key=lambda x: x["wrong_percent"], reverse=True)
    top_wrong_questions = top_wrong_questions[:3]

    # Calculate average time
    times_list = []
    for s in graded_students:
        if s["time_spent_display"] and s["time_spent_display"] != "--":
            # Parse time from string like "45 دقيقة" or "1س 30د"
            time_str = s["time_spent_display"]
            total_minutes = 0
            if "س" in time_str:
                parts = time_str.split()
                hours = int(parts[0].replace("س", ""))
                if len(parts) > 1:
                    minutes = int(parts[1].replace("د", ""))
                else:
                    minutes = 0
                total_minutes = hours * 60 + minutes
            elif "دقيقة" in time_str:
                total_minutes = int(time_str.replace(" دقيقة", ""))
            if total_minutes > 0:
                times_list.append(total_minutes)
    
    if times_list:
        avg_minutes = sum(times_list) // len(times_list)
        average_time_display = f"{avg_minutes} دقيقة"
    else:
        average_time_display = "--"

    context = {
        "exam": exam,
        "total_mark": total_mark_sum,
        "highest_score": highest_score,
        "summary": summary,
        "grade_distribution": grade_distribution,
        "top_wrong_questions": top_wrong_questions,
        "students_page": students_page,
        "pagination": pagination,
        "query": query,
        "selected_status": selected_status,
        "average_time_display": average_time_display,
    }
    return render(request, "core/admin_exam_results.html", context)


@login_required
@user_passes_test(is_admin)
def admin_exam_details(request, exam_id):
    """
    صفحة عرض تفاصيل الاختبار للأدمن (قراءة فقط)
    المشرف لا يستطيع تعديل الاختبار
    """
    # منع أي محاولة تعديل
    if request.method == "POST":
        messages.error(request, "المشرف لا يستطيع تعديل الاختبار.", extra_tags="user:admin")
        return redirect('admin_exam_details', exam_id=exam_id)
    
    exam = get_object_or_404(Exam.objects.select_related('teacher', 'subject'), id=exam_id)
    
    # الحصول على أسئلة الاختبار
    exam_questions = (
        ExamQuestion.objects.filter(exam=exam)
        .select_related("question")
        .order_by("order", "id")
    )
    
    # الحصول على أسئلة المادة (للعرض فقط)
    subject = exam.subject
    base_questions = Question.objects.filter(subject=subject) if subject else Question.objects.none()
    
    # إنشاء قائمة الأسئلة المختارة للعرض فقط
    existing_ids = set(exam_questions.values_list("question_id", flat=True))
    questions = list(base_questions)
    selected_questions = []
    for q in questions:
        selected = q.id in existing_ids
        selected_questions.append({
            "obj": q,
            "selected": selected,
        })
    
    total_selected = exam_questions.count()
    total_marks = exam_questions.aggregate(total=Sum("mark"))["total"] or 0
    
    # عرض الصفحة للمشرف (قراءة فقط)
    context = {
        "exam": exam,
        "exam_questions": exam_questions,
        "subject": subject,
        "base_questions": base_questions,
        "questions": selected_questions,
        "total_selected": total_selected,
        "total_marks": total_marks,
        "is_admin_view": True,  # للتمييز بين عرض المشرف والمدرس
    }
    return render(request, "core/teacher_exam_questions.html", context)


@login_required
@user_passes_test(is_admin)
def admin_analytics(request):
    user = request.user
    total_users = User.objects.count()
    total_students = User.objects.filter(role="student").count()
    total_teachers = User.objects.filter(role="teacher").count()
    blocked_users = User.objects.filter(is_active=False).count()

    total_exams = Exam.objects.count()
    active_exams = Exam.objects.filter(
        status__in=[Exam.Status.SCHEDULED, Exam.Status.ONGOING]
    ).count()
    finished_exams = Exam.objects.filter(status=Exam.Status.FINISHED).count()

    staff_users = User.objects.filter(is_staff=True).count()
    role_total = total_students + total_teachers + staff_users

    if role_total > 0:
        student_percent = round((total_students / role_total) * 100)
        teacher_percent = round((total_teachers / role_total) * 100)
        staff_percent = 100 - student_percent - teacher_percent
    else:
        student_percent = 0
        teacher_percent = 0
        staff_percent = 0

    student_end = student_percent
    teacher_end = student_percent + teacher_percent

    roles_gradient = (
        f"conic-gradient(#3b82f6 0% {student_end}%, "
        f"#a855f7 {student_end}% {teacher_end}%, "
        f"#ef4444 {teacher_end}% 100%)"
    )

    teachers = User.objects.filter(role="teacher").order_by("full_name", "username")
    supervisors = User.objects.filter(is_staff=True).order_by(
        "full_name", "username"
    )

    reply_to_id = request.GET.get("reply_to", "").strip()
    reply_target_type = ""
    reply_to_message = None
    if reply_to_id:
        reply_candidate = (
            Message.objects.filter(id=reply_to_id, recipient=user)
            .select_related("sender")
            .first()
        )
        if reply_candidate:
            reply_to_message = reply_candidate
            if reply_candidate.direction == Message.Direction.TEACHER_TO_SUPERVISOR:
                reply_target_type = "teacher"
            elif reply_candidate.direction == Message.Direction.SUPERVISOR_TO_SUPERVISOR:
                reply_target_type = "supervisor"

    if request.method == "POST":
        form_type = request.POST.get("form_type", "").strip()
        if form_type == "admin_to_teacher":
            teacher_id = request.POST.get("teacher_id", "").strip()
            title = request.POST.get("teacher_title", "").strip()
            body = request.POST.get("teacher_body", "").strip()
            category = request.POST.get("teacher_category", "").strip()
            in_reply_to_id = request.POST.get("in_reply_to", "").strip()
            in_reply_to = None
            if in_reply_to_id:
                in_reply_to = (
                    Message.objects.filter(id=in_reply_to_id, recipient=user)
                    .select_related("sender")
                    .first()
                )
            if teacher_id and body:
                teacher = teachers.filter(id=teacher_id).first()
                if teacher:
                    Message.objects.create(
                        sender=user,
                        recipient=teacher,
                        direction=Message.Direction.SUPERVISOR_TO_TEACHER,
                        title=title,
                        body=body,
                        category=category,
                        in_reply_to=in_reply_to,
                    )
                    messages.success(request, "تم إرسال الرسالة للمعلم بنجاح.")
            return redirect("admin_analytics")
        elif form_type == "admin_to_supervisor":
            supervisor_id = request.POST.get("supervisor_id", "").strip()
            title = request.POST.get("supervisor_title", "").strip()
            body = request.POST.get("supervisor_body", "").strip()
            category = request.POST.get("supervisor_category", "").strip()
            in_reply_to_id = request.POST.get("in_reply_to", "").strip()
            in_reply_to = None
            if in_reply_to_id:
                in_reply_to = (
                    Message.objects.filter(id=in_reply_to_id, recipient=user)
                    .select_related("sender")
                    .first()
                )
            if supervisor_id and body:
                supervisor = supervisors.filter(id=supervisor_id).first()
                if supervisor:
                    Message.objects.create(
                        sender=user,
                        recipient=supervisor,
                        direction=Message.Direction.SUPERVISOR_TO_SUPERVISOR,
                        title=title,
                        body=body,
                        category=category,
                        in_reply_to=in_reply_to,
                    )
                    messages.success(request, "تم إرسال الرسالة للمشرف بنجاح.")
            return redirect("admin_analytics")

    inbox_queryset = Message.objects.filter(recipient=user)
    teacher_messages = (
        inbox_queryset.filter(direction=Message.Direction.TEACHER_TO_SUPERVISOR)
        .select_related("sender")
        .order_by("-created_at")[:20]
    )

    supervisor_messages = (
        inbox_queryset.filter(direction=Message.Direction.SUPERVISOR_TO_SUPERVISOR)
        .select_related("sender")
        .order_by("-created_at")[:20]
    )

    total_messages = inbox_queryset.count()
    unread_messages = inbox_queryset.filter(is_read=False).count()
    replied_count = Message.objects.filter(
        sender=user, in_reply_to__isnull=False
    ).count()

    context = {
        "total_users": total_users,
        "total_students": total_students,
        "total_teachers": total_teachers,
        "blocked_users": blocked_users,
        "total_exams": total_exams,
        "active_exams": active_exams,
        "finished_exams": finished_exams,
        "student_percent": student_percent,
        "teacher_percent": teacher_percent,
        "staff_percent": staff_percent,
        "student_end": student_end,
        "teacher_end": teacher_end,
        "roles_gradient": roles_gradient,
        "teachers": teachers,
        "supervisors": supervisors,
        "teacher_messages": teacher_messages,
        "supervisor_messages": supervisor_messages,
        "total_messages": total_messages,
        "unread_messages": unread_messages,
        "replied_count": replied_count,
        "reply_to_message": reply_to_message,
        "reply_target_type": reply_target_type,
    }
    return render(request, "core/admin_analytics.html", context)


@login_required
@user_passes_test(is_teacher)
# --- قسم المدرس (Teacher Section) ---

@login_required
@user_passes_test(is_teacher)
def teacher_dashboard(request):
    """
    لوحة تحكم المدرس: توفر نظرة شاملة على الاختبارات الجارية، المجموعات،
    والطلاب، بالإضافة إلى التنبيهات الخاصة بالتصحيح اليدوي.
    """
    user = request.user

    teacher_exams = Exam.objects.filter(teacher=user).annotate(
        questions_count=Count("exam_questions", distinct=True),
        allowed_students_count=Count("allowed_students", distinct=True)
    )
    _sync_exam_statuses(teacher_exams)
    active_exams = teacher_exams.filter(
        status__in=[Exam.Status.SCHEDULED, Exam.Status.ONGOING]
    )
    active_exams_count = active_exams.count()

    groups = Group.objects.filter(teacher=user).annotate(
        student_count=Count("students")
    )
    groups_count = groups.count()

    students_count = (
        User.objects.filter(student_groups__teacher=user, role="student")
        .distinct()
        .count()
    )

    # Count exams that have finished attempts requiring correction
    pending_corrections_count = teacher_exams.filter(
        status=Exam.Status.FINISHED
    ).annotate(
        finished_attempts=Count(
            "attempts",
            filter=Q(attempts__status__in=[StudentExam.Status.FINISHED, StudentExam.Status.FAILED_CHEATING])
        )
    ).filter(finished_attempts__gt=0).count()

    ongoing_exams_qs = active_exams.filter(status=Exam.Status.ONGOING).annotate(
        submitted_attempts_count=Count(
            "attempts",
            filter=Q(attempts__status__in=[StudentExam.Status.FINISHED, StudentExam.Status.FAILED_CHEATING]),
            distinct=True
        ),
        allowed_students_count=Count("allowed_students", distinct=True)
    ).order_by("-start_time")[:2]
    
    # Calculate total_participants_display for each ongoing exam
    ongoing_exams = list(ongoing_exams_qs)
    for exam in ongoing_exams:
        if exam.allowed_students_count > 0:
            exam.total_participants_display = exam.allowed_students_count
        else:
            exam.total_participants_display = exam.total_participants or 0

    upcoming_exams = teacher_exams.filter(
        status=Exam.Status.SCHEDULED
    ).order_by("start_time")[:5]

    groups_overview = groups.order_by("name")[:4]

    context = {
        "active_exams_count": active_exams_count,
        "groups_count": groups_count,
        "pending_corrections_count": pending_corrections_count,
        "students_count": students_count,
        "ongoing_exams": ongoing_exams,
        "upcoming_exams": upcoming_exams,
        "groups_overview": groups_overview,
    }
    return render(request, "core/teacher_dashboard.html", context)


def _build_student_dashboard_context(user, request):
    """
    بناء سياق لوحة تحكم الطالب: جلب المدرسين المتاحين، المجموعات المشترك بها،
    وحالة طلبات الانضمام.
    """
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.now()

    groups = Group.objects.filter(students=user).select_related("teacher", "subject")
    groups_count = groups.count()

    current_teachers = (
        User.objects.filter(
            Q(teaching_groups__students=user)
            | Q(
                received_join_requests__student=user,
                received_join_requests__status=StudentJoinRequest.Status.ACCEPTED,
            )
        )
        .distinct()
    )

    teacher_query = request.GET.get("teacher_q", "").strip()
    teacher_selected_subject = request.GET.get("teacher_subject", "").strip()

    teachers = User.objects.filter(role="teacher", is_active=True)
    if teacher_query:
        teachers = teachers.filter(
            Q(full_name__icontains=teacher_query)
            | Q(username__icontains=teacher_query)
        )
    if teacher_selected_subject:
        teachers = teachers.filter(subjects__id=teacher_selected_subject)

    teachers = teachers.order_by("full_name", "username")
    teachers_count = teachers.count()

    teacher_ids = list(teachers.values_list("id", flat=True))
    current_teacher_ids = set(
        current_teachers.filter(id__in=teacher_ids).values_list("id", flat=True)
    )

    teacher_subjects = Subject.objects.filter(teacher_id__in=teacher_ids).values(
        "teacher_id", "name"
    ).order_by("name")

    teacher_groups = Group.objects.filter(
        teacher_id__in=teacher_ids, students=user
    ).values("teacher_id", "name").order_by("name")

    teacher_pending_requests = StudentJoinRequest.objects.filter(
        student=user, status=StudentJoinRequest.Status.PENDING
    ).values("teacher_id")

    teacher_invitations = (
        StudentJoinRequest.objects.filter(
            student=user,
            status=StudentJoinRequest.Status.PENDING,
            source=StudentJoinRequest.Source.FROM_TEACHER,
        )
        .select_related("teacher", "group")
        .order_by("-created_at")
    )

    teacher_subjects_map = {}
    for item in teacher_subjects:
        teacher_subjects_map.setdefault(item["teacher_id"], []).append(item["name"])

    teacher_groups_map = {}
    for item in teacher_groups:
        teacher_groups_map.setdefault(item["teacher_id"], []).append(item["name"])

    teacher_pending_map = set(item["teacher_id"] for item in teacher_pending_requests)

    teacher_subject_choices = (
        Subject.objects.filter(teacher__role="teacher", teacher__is_active=True)
        .order_by("name")
        .values("id", "name")
        .distinct()
    )

    # Get exams where student is explicitly selected by their teacher
    exams_base = (
        Exam.objects.filter(allowed_students=user)
        .select_related("subject", "teacher")
        .annotate(
            questions_count=Count("exam_questions", distinct=True),
            allowed_students_count=Count("allowed_students", distinct=True)
        )
        .distinct()
        .order_by("start_time")
    )
    _sync_exam_statuses(exams_base)

    ongoing_exams = exams_base.filter(status=Exam.Status.ONGOING)
    upcoming_exams = exams_base.filter(
        status=Exam.Status.SCHEDULED, start_time__gte=now
    )
    finished_exams = exams_base.filter(status=Exam.Status.FINISHED)

    completed_exams_count = finished_exams.count()
    upcoming_exams_count = upcoming_exams.count()

    finished_attempts = StudentExam.objects.filter(
        student=user,
        status__in=[StudentExam.Status.FINISHED, StudentExam.Status.FAILED_CHEATING],
    ).select_related("exam", "exam__subject")

    total_finished_exams = finished_attempts.count()
    
    # Calculate pass/fail based on percentage (>= 50% = pass)
    passed_exams = 0
    failed_exams = 0
    total_score_sum = 0
    total_percentage_sum = 0
    
    for attempt in finished_attempts:
        # Calculate total mark for this exam
        total_mark = (
            ExamQuestion.objects.filter(exam=attempt.exam).aggregate(total=Sum("mark"))["total"]
            or 0
        )
        
        # Get pass_mark from exam (default to 50 if not set)
        pass_mark = attempt.exam.pass_mark if hasattr(attempt.exam, 'pass_mark') and attempt.exam.pass_mark else 50
        
        score = float(attempt.score or 0)
        total_score_sum += score
        
        if total_mark > 0:
            score_percent = (score / float(total_mark)) * 100
            total_percentage_sum += score_percent
            
            if score_percent >= pass_mark:
                passed_exams += 1
            else:
                failed_exams += 1
        else:
            # If no total mark, count as failed
            failed_exams += 1
    
    # Include absent students as failed
    now = timezone.now()
    exams_where_student_allowed = (
        Exam.objects.filter(allowed_students=user, status=Exam.Status.FINISHED)
        .select_related("subject", "teacher")
    )
    
    attempt_exam_ids = set(finished_attempts.values_list("exam_id", flat=True))
    
    for exam in exams_where_student_allowed:
        # Check if student didn't take the exam (absent)
        if exam.id not in attempt_exam_ids:
            exam_end_time = exam.end_time or (
                exam.start_time + timedelta(minutes=exam.duration_minutes) 
                if exam.start_time and exam.duration_minutes else None
            )
            if exam_end_time and now > exam_end_time:
                # Student is absent - count as failed
                total_finished_exams += 1
                failed_exams += 1

    average_score = None
    average_percentage = None
    best_exam = None
    worst_exam = None

    if finished_attempts.count() > 0:
        average_score = float(total_score_sum) / float(finished_attempts.count())
        average_percentage = float(total_percentage_sum) / float(finished_attempts.count()) if finished_attempts.count() else None
        best_exam = finished_attempts.order_by("-score", "-finished_at").first()
        worst_exam = finished_attempts.order_by("score", "finished_at").first()

    gpa_percent = None

    ongoing_exam = ongoing_exams.first()
    upcoming_exams_list = list(upcoming_exams[:5])
    recent_results = list(finished_exams.order_by("-start_time")[:5])

    current_teacher_cards = []
    available_teacher_cards = []
    for teacher in teachers:
        subjects_for_teacher = teacher_subjects_map.get(teacher.id, [])
        groups_for_teacher = teacher_groups_map.get(teacher.id, [])
        has_pending_request = teacher.id in teacher_pending_map
        card = {
            "teacher": teacher,
            "subjects": subjects_for_teacher,
            "groups": groups_for_teacher,
            "has_pending_request": has_pending_request,
        }
        if teacher.id in current_teacher_ids:
            current_teacher_cards.append(card)
        else:
            available_teacher_cards.append(card)

    inbox_messages = Message.objects.filter(recipient=user).select_related("sender").order_by("-created_at")[:20]

    teacher_messages = [m for m in inbox_messages if getattr(m.sender, "role", None) == "teacher"]
    supervisor_messages = [m for m in inbox_messages if m.sender.is_staff]

    total_messages = len(inbox_messages)
    unread_messages = sum(1 for m in inbox_messages if not m.is_read)

    report_teachers = current_teachers.order_by("full_name", "username")

    return {
        "groups": groups,
        "groups_count": groups_count,
        "teachers": teachers,
        "teachers_count": teachers_count,
        "current_teacher_cards": current_teacher_cards,
        "available_teacher_cards": available_teacher_cards,
        "teacher_subject_choices": teacher_subject_choices,
        "teacher_query": teacher_query,
        "teacher_selected_subject": teacher_selected_subject,
        "teacher_invitations": teacher_invitations,
        "completed_exams_count": completed_exams_count,
        "upcoming_exams_count": upcoming_exams_count,
        "gpa_percent": gpa_percent,
        "stats_total_finished_exams": total_finished_exams,
        "stats_passed_exams": passed_exams,
        "stats_failed_exams": failed_exams,
        "stats_average_score": average_score,
        "stats_best_exam": best_exam,
        "stats_worst_exam": worst_exam,
        "ongoing_exam": ongoing_exam,
        "upcoming_exams_list": upcoming_exams_list,
        "recent_results": recent_results,
        "report_teachers": report_teachers,
        "student_teacher_messages": teacher_messages,
        "student_supervisor_messages": supervisor_messages,
        "student_total_messages": total_messages,
        "student_unread_messages": unread_messages,
    }


# --- قسم الطالب (Student Section) ---

@login_required
@user_passes_test(is_student)
def student_dashboard(request):
    """
    لوحة تحكم الطالب: تعرض ملخصاً للاختبارات القادمة، المجموعات، والرسائل.
    """
    user = request.user
    account_error = ""
    account_success = ""
    reply_to_id = request.GET.get("reply_to", "").strip()
    reply_to_message = None
    reply_target_teacher = None
    if reply_to_id:
        reply_candidate = (
            Message.objects.filter(id=reply_to_id, recipient=user)
            .select_related("sender")
            .first()
        )
        if reply_candidate and getattr(reply_candidate.sender, "role", None) == "teacher":
            reply_to_message = reply_candidate
            reply_target_teacher = reply_candidate.sender
    if request.method == "POST":
        form_type = request.POST.get("form_type", "").strip()
        if form_type == "student_to_teacher":
            teacher_id = request.POST.get("teacher_id", "").strip()
            title = request.POST.get("title", "").strip()
            body = request.POST.get("body", "").strip()
            in_reply_to_id = request.POST.get("in_reply_to", "").strip()
            in_reply_to = None
            if in_reply_to_id:
                in_reply_to = (
                    Message.objects.filter(id=in_reply_to_id, recipient=user)
                    .select_related("sender")
                    .first()
                )
            if body and teacher_id:
                teacher = User.objects.filter(
                    id=teacher_id,
                    role="teacher",
                ).filter(
                    Q(teaching_groups__students=user)
                    | Q(subject_enrollments__student=user)
                    | Q(
                        received_join_requests__student=user,
                        received_join_requests__status=StudentJoinRequest.Status.ACCEPTED,
                    )
                ).distinct().first()
                if teacher:
                    Message.objects.create(
                        sender=user,
                        recipient=teacher,
                        direction=Message.Direction.STUDENT_TO_TEACHER,
                        title=title,
                        body=body,
                        in_reply_to=in_reply_to,
                    )
                    messages.success(request, "تم إرسال الرسالة للمدرس بنجاح.", extra_tags="user:student")
                    return HttpResponseRedirect(reverse("student_dashboard"))
                else:
                    messages.error(request, "المدرس المحدد غير مرتبط بك أو غير موجود.", extra_tags="user:student")
            elif not body:
                messages.error(request, "يرجى كتابة نص الرسالة.", extra_tags="user:student")
            elif not teacher_id:
                messages.error(request, "يرجى اختيار مدرس.", extra_tags="user:student")
        else:
            settings_form = request.POST.get("settings_form", "").strip()
            if settings_form:
                if "profile_submit" in request.POST:
                    full_name = request.POST.get("full_name", "").strip()
                    email = request.POST.get("email", "").strip()
                    user.full_name = full_name
                    user.email = email
                    user.save(update_fields=["full_name", "email"])
                    account_success = "تم تحديث بيانات الحساب بنجاح."
                elif "password_submit" in request.POST:
                    current_password = request.POST.get("current_password", "")
                    new_password = request.POST.get("new_password", "")
                    if not current_password or not new_password:
                        account_error = "يرجى إدخال كلمة المرور الحالية والجديدة."
                    elif not check_password(current_password, user.password):
                        account_error = "كلمة المرور الحالية غير صحيحة."
                    else:
                        try:
                            validate_password(new_password, user)
                        except ValidationError as e:
                            account_error = " ".join(e.messages)
                        else:
                            user.set_password(new_password)
                            user.save(update_fields=["password"])
                            update_session_auth_hash(request, user)
                            account_success = "تم تحديث كلمة المرور بنجاح."
    context = _build_student_dashboard_context(user, request)
    page = request.GET.get("page", "").strip()
    if page == "reports":
        Message.objects.filter(
            recipient=user,
            sender__role="teacher",
            is_read=False,
        ).update(is_read=True)
        context["active_page"] = "reports"
        context["reply_to_message"] = reply_to_message
        context["reply_target_teacher"] = reply_target_teacher
    elif page == "stats":
        context["active_page"] = "stats"
    elif page == "settings":
        context["active_page"] = "settings"
        context["account_error"] = account_error
        context["account_success"] = account_success
    else:
        context["active_page"] = "dashboard"
    return render(request, "core/student_dashboard.html", context)


@login_required
@user_passes_test(is_student)
def student_teachers(request):
    user = request.user
    context = _build_student_dashboard_context(user, request)
    context["active_page"] = "teachers"
    return render(request, "core/student_dashboard.html", context)


@login_required
@user_passes_test(is_student)
def student_groups(request):
    user = request.user
    context = _build_student_dashboard_context(user, request)
    context["active_page"] = "groups"
    return render(request, "core/student_dashboard.html", context)


@login_required
@user_passes_test(is_student)
def student_group_detail(request, group_id):
    user = request.user
    group = get_object_or_404(Group.objects.select_related("teacher", "subject"), id=group_id, students=user)

    chat_messages = (
        GroupMessage.objects.filter(group=group)
        .select_related("sender")
        .order_by("created_at")
    )

    message_error = ""

    if request.method == "POST":
        content = request.POST.get("message", "").strip()
        if not content:
            message_error = "يرجى كتابة رسالة قبل الإرسال."
        else:
            GroupMessage.objects.create(
                group=group,
                sender=user,
                content=content,
            )
            return HttpResponseRedirect(reverse("student_group_detail", args=[group.id]))

    students = list(group.students.all().order_by("full_name", "username"))
    members = [group.teacher]
    for s in students:
        if s not in members:
            members.append(s)
    members_count = len(members)

    context = {
        "group": group,
        "chat_messages": chat_messages,
        "message_error": message_error,
        "members": members,
        "members_count": members_count,
    }
    return render(request, "core/student_group_detail.html", context)


@login_required
@user_passes_test(is_student)
def student_exam_take(request, exam_id):
    """
    نقطة الدخول الرئيسية لأداء الاختبار من قبل الطالب.
    الوظائف الجوهرية:
    1. التحقق من صلاحية الطالب لدخول الاختبار (المجموعة، الوقت، السماح بالدخول المتأخر).
    2. إنشاء محاولة اختبار (StudentExam) جديدة أو استكمال محاولة قائمة.
    3. عرض الأسئلة واحداً تلو الآخر مع إمكانية التنقل (POST: next/prev).
    4. حفظ الإجابات تلقائياً (الاختيار من متعدد أو المقالي).
    5. معالجة تسليم الاختبار (POST: submit) وحساب الدرجة الأولية.
    6. تسجيل أحداث الاختبار (ExamEvent) مثل الدخول والخروج والتقديم.
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.urls import reverse

    user = request.user

    exam = get_object_or_404(
        Exam.objects.select_related("subject", "teacher"),
        id=exam_id,
    )

    # Check if student is explicitly allowed for this exam
    if not exam.allowed_students.filter(id=user.id).exists():
        messages.error(request, "هذا الاختبار غير مخصص لك.", extra_tags="user:student")
        return HttpResponseRedirect(reverse("student_exams"))

    now = timezone.now()

    end_time = exam.end_time
    if end_time is None:
        end_time = exam.start_time + timedelta(minutes=exam.duration_minutes)

    late_join = exam.late_join_minutes or 0
    allowed_start = exam.start_time
    join_deadline = end_time
    if late_join > 0:
        join_deadline = min(end_time, exam.start_time + timedelta(minutes=late_join))

    attempt = StudentExam.objects.filter(exam=exam, student=user).first()

    if now > end_time:
        if attempt and attempt.status == StudentExam.Status.IN_PROGRESS:
            from django.utils import timezone as _tz2

            attempt.status = StudentExam.Status.FINISHED
            attempt.finished_at = _tz2.now()
            attempt.last_activity_at = _tz2.now()
            attempt.score = (
                StudentAnswer.objects.filter(attempt=attempt).aggregate(
                    total=Sum("mark_obtained")
                )["total"]
                or 0
            )
            attempt.save(update_fields=["status", "finished_at", "score", "last_activity_at"])

            exam.submitted_count = StudentExam.objects.filter(
                exam=exam, status=StudentExam.Status.FINISHED
            ).count()
            exam.save(update_fields=["submitted_count"])

            ExamEvent.objects.create(
                exam=exam,
                student=user,
                event_type=ExamEvent.EventType.SUBMIT,
                message="تم إنهاء الاختبار تلقائياً لانتهاء الوقت.",
            )
            messages.info(request, "انتهى وقت الاختبار وتم إنهاؤه تلقائياً.", extra_tags="user:student")
            return HttpResponseRedirect(reverse("student_exams"))
        messages.error(request, "انتهى وقت هذا الاختبار ولا يمكن الدخول إليه الآن.", extra_tags="user:student")
        return HttpResponseRedirect(reverse("student_exams"))

    if attempt is None:
        if now < allowed_start:
            messages.error(request, "لا يمكنك بدء هذا الاختبار قبل وقت البدء المحدد.", extra_tags="user:student")
            return HttpResponseRedirect(reverse("student_exams"))
        if now > join_deadline:
            messages.error(request, "انتهت فترة السماح بدخول هذا الاختبار.", extra_tags="user:student")
            return HttpResponseRedirect(reverse("student_exams"))

        from django.utils import timezone as _tz

        attempt = StudentExam.objects.create(
            exam=exam,
            student=user,
            status=StudentExam.Status.IN_PROGRESS,
            started_at=_tz.now(),
            last_activity_at=_tz.now(),
        )
        ExamEvent.objects.create(
            exam=exam,
            student=user,
            event_type=ExamEvent.EventType.JOIN,
            message="بدأ الطالب الاختبار.",
        )
    else:
        if attempt.status != StudentExam.Status.IN_PROGRESS:
            messages.info(request, "لقد أنهيت هذا الاختبار بالفعل.", extra_tags="user:student")
            return HttpResponseRedirect(reverse("student_exams"))
        attempt.last_activity_at = timezone.now()
        attempt.save(update_fields=["last_activity_at"])

    total_seconds = int((end_time - now).total_seconds())
    if total_seconds < 0:
        total_seconds = 0

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    remaining_time_display = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    exam_questions_qs = (
        ExamQuestion.objects.filter(exam=exam)
        .select_related("question")
        .order_by("order", "id")
    )
    total_questions = exam_questions_qs.count()

    if not total_questions:
        messages.error(request, "هذا الاختبار لا يحتوي على أسئلة بعد.", extra_tags="user:student")
        return HttpResponseRedirect(reverse("student_exams"))

    answers_qs = StudentAnswer.objects.filter(attempt=attempt).select_related(
        "exam_question", "selected_choice"
    )
    answers_by_eq = {a.exam_question_id: a for a in answers_qs}

    try:
        current_index = int(request.GET.get("q", "1"))
    except ValueError:
        current_index = 1

    try:
        if current_index < 1:
            current_index = 1
        if total_questions and current_index > total_questions:
            current_index = total_questions

        if request.method == "POST" and total_questions:
            action = request.POST.get("action", "").strip()
            current_index_raw = request.POST.get("current_index", "").strip()
            try:
                current_index = int(current_index_raw)
            except ValueError:
                current_index = 1

            if current_index < 1:
                current_index = 1
            if current_index > total_questions:
                current_index = total_questions

            current_exam_question = exam_questions_qs[current_index - 1]
            current_question = current_exam_question.question

            if current_question.question_type == Question.QuestionType.MCQ:
                selected_choice_id = request.POST.get("choice", "").strip()
                if selected_choice_id:
                    choice_obj = (
                        QuestionChoice.objects.filter(
                            id=selected_choice_id, question=current_question
                        )
                        .only("id", "is_correct")
                        .first()
                    )
                    if choice_obj:
                        answer_obj, _ = StudentAnswer.objects.get_or_create(
                            attempt=attempt,
                            exam_question=current_exam_question,
                        )
                        answer_obj.selected_choice = choice_obj
                        if choice_obj.is_correct:
                            answer_obj.is_correct = True
                            answer_obj.mark_obtained = current_exam_question.mark
                        else:
                            answer_obj.is_correct = False
                            answer_obj.mark_obtained = 0
                        answer_obj.save()
            
            elif current_question.question_type == Question.QuestionType.ESSAY:
                essay_answer = request.POST.get("essay_answer", "").strip()
                answer_obj, _ = StudentAnswer.objects.get_or_create(
                    attempt=attempt,
                    exam_question=current_exam_question,
                )
                answer_obj.essay_text = essay_answer
                # Essay answers need manual marking later
                answer_obj.is_correct = None
                answer_obj.mark_obtained = 0
                answer_obj.save()

            attempt.last_activity_at = timezone.now()
            attempt.save(update_fields=["last_activity_at"])

            if action == "next" and current_index < total_questions:
                current_index += 1
            elif action == "prev" and current_index > 1:
                current_index -= 1
            elif action == "submit":
                from django.utils import timezone as _tz2

                attempt.status = StudentExam.Status.FINISHED
                attempt.finished_at = _tz2.now()
                attempt.last_activity_at = _tz2.now()
                attempt.score = (
                    StudentAnswer.objects.filter(attempt=attempt).aggregate(
                        total=Sum("mark_obtained")
                    )["total"]
                    or 0
                )
                attempt.save(update_fields=["status", "finished_at", "score", "last_activity_at"])

                exam.submitted_count = StudentExam.objects.filter(
                    exam=exam, status=StudentExam.Status.FINISHED
                ).count()
                exam.save(update_fields=["submitted_count"])

                ExamEvent.objects.create(
                    exam=exam,
                    student=user,
                    event_type=ExamEvent.EventType.SUBMIT,
                    message="أنهى الطالب الاختبار.",
                )

                messages.success(request, "تم تسليم الاختبار بنجاح.", extra_tags="user:student")
                return HttpResponseRedirect(reverse("student_exams"))

            return redirect(
                f"{reverse('student_exam_take', args=[exam.id])}?q={current_index}"
            )
    except Exception as e:
        logger.error(f"Error in student_exam_take: {str(e)}", exc_info=True)
        messages.error(request, "حدث خطأ غير متوقع أثناء أداء الاختبار.", extra_tags="user:student")
        return HttpResponseRedirect(reverse("student_exams"))

    current_exam_question = exam_questions_qs[current_index - 1]
    current_question = current_exam_question.question
    current_choice_id = None
    current_answer = answers_by_eq.get(current_exam_question.id)
    if current_answer and current_answer.selected_choice_id:
        current_choice_id = current_answer.selected_choice_id

    answered_count = len(answers_by_eq)
    remaining_count = max(total_questions - answered_count, 0)
    progress_percent = 0
    if total_questions:
        progress_percent = int((answered_count / total_questions) * 100)

    question_map = []
    for idx in range(total_questions):
        eq = exam_questions_qs[idx]
        if current_index == idx + 1:
            state = "current"
        elif eq.id in answers_by_eq:
            state = "answered"
        else:
            state = "unanswered"
        question_map.append({"index": idx + 1, "state": state})

    context = {
        "exam": exam,
        "current_question": current_question,
        "current_choice_id": current_choice_id,
        "questions": exam_questions_qs,
        "question_map": question_map,
        "current_index": current_index,
        "total_questions": total_questions,
        "answered_count": answered_count,
        "remaining_count": remaining_count,
        "progress_percent": progress_percent,
        "remaining_time_display": remaining_time_display,
        "total_seconds": total_seconds,
        "auto_proctoring": exam.auto_proctoring,
        "auto_fail_on_cheating": exam.auto_fail_on_cheating,
    }

    return render(request, "core/student_exam_take.html", context)


@login_required
@user_passes_test(is_student)
def student_exams(request):
    """
    عرض قائمة الاختبارات المتاحة للطالب.
    تشمل الاختبارات المجدولة، الجارية، والمنتهية الخاصة بالمواد والمجموعات المشترك بها.
    """
    from django.utils import timezone
    from datetime import timedelta
    
    user = request.user

    # Get exams where student is explicitly selected by their teacher
    exams_qs = (
        Exam.objects.filter(allowed_students=user)
        .select_related("subject", "teacher")
        .annotate(
            questions_count=Count("exam_questions", distinct=True),
            allowed_students_count=Count("allowed_students", distinct=True)
        )
        .distinct()
        .order_by("-start_time")
    )
    _sync_exam_statuses(exams_qs)

    query = request.GET.get("q", "").strip()
    if query:
        exams_qs = exams_qs.filter(
            Q(title__icontains=query)
            | Q(subject__name__icontains=query)
            | Q(teacher__full_name__icontains=query)
            | Q(teacher__username__icontains=query)
        )

    selected_status = request.GET.get("status", "").strip()
    if selected_status:
        exams_qs = exams_qs.filter(status=selected_status)

    # Get all student attempts for these exams
    attempts_dict = {}
    attempts_qs = StudentExam.objects.filter(
        exam__in=exams_qs,
        student=user
    ).select_related("exam")
    for attempt in attempts_qs:
        attempts_dict[attempt.exam_id] = attempt

    # Build enriched exam list with student results
    now = timezone.now()
    enriched_exams = []
    
    for exam in exams_qs:
        # Calculate actual total mark from exam questions
        total_mark = (
            ExamQuestion.objects.filter(exam=exam).aggregate(total=Sum("mark"))["total"]
            or 0
        )
        
        # Get student's attempt for this exam
        attempt = attempts_dict.get(exam.id)
        
        # Calculate exam end time
        exam_end_time = exam.end_time or (
            exam.start_time + timedelta(minutes=exam.duration_minutes) 
            if exam.start_time and exam.duration_minutes else None
        )
        exam_has_expired = exam_end_time and now > exam_end_time
        
        # Calculate score and status
        score = None
        score_percent = 0
        pass_status = None
        
        # Get pass_mark from exam (default to 50 if not set)
        pass_mark = exam.pass_mark if hasattr(exam, 'pass_mark') and exam.pass_mark else 50
        
        if attempt and attempt.status != StudentExam.Status.IN_PROGRESS:
            score = float(attempt.score or 0)
            if total_mark > 0:
                score_percent = round((score / float(total_mark)) * 100)
            else:
                score_percent = 0
            
            # Determine pass/fail status based on exam's pass_mark
            if score_percent >= pass_mark:
                pass_status = "pass"
            else:
                pass_status = "fail"
        elif not attempt and exam_has_expired:
            # Student didn't start exam and it's expired = absent
            pass_status = "absent"
        
        enriched_exams.append({
            "exam": exam,
            "attempt": attempt,
            "score": score,
            "score_percent": score_percent,
            "total_mark": total_mark,
            "pass_status": pass_status,
            "has_result": attempt and attempt.status == StudentExam.Status.FINISHED,
        })

    context = _build_student_dashboard_context(user, request)
    context["active_page"] = "exams"
    context["enriched_exams"] = enriched_exams
    context["student_exams_query"] = query
    context["student_exams_selected_status"] = selected_status

    return render(request, "core/student_dashboard.html", context)


@login_required
@user_passes_test(is_student)
def student_exam_scheduled_detail(request, exam_id):
    from django.utils import timezone
    from datetime import timedelta

    user = request.user

    exam = get_object_or_404(
        Exam.objects.select_related("subject", "teacher"),
        id=exam_id,
    )

    # Check if student is explicitly allowed for this exam
    if not exam.allowed_students.filter(id=user.id).exists():
        raise Http404

    now = timezone.now()

    if exam.end_time:
        computed_end_time = exam.end_time
    else:
        computed_end_time = exam.start_time + timedelta(minutes=exam.duration_minutes)

    late_join = exam.late_join_minutes or 0
    allowed_start = exam.start_time
    last_join_time = computed_end_time
    if late_join > 0:
        last_join_time = min(
            computed_end_time, exam.start_time + timedelta(minutes=late_join)
        )

    remaining_seconds = int((exam.start_time - now).total_seconds())
    if remaining_seconds < 0:
        remaining_seconds = 0

    days = remaining_seconds // 86400
    hours = (remaining_seconds % 86400) // 3600
    minutes = (remaining_seconds % 3600) // 60

    countdown_days = f"{days:02d}"
    countdown_hours = f"{hours:02d}"
    countdown_minutes = f"{minutes:02d}"

    can_start_exam = allowed_start <= now <= last_join_time
    before_allowed_start = now < allowed_start
    after_end_time = now > computed_end_time

    question_count = ExamQuestion.objects.filter(exam=exam).count()

    context = {
        "exam": exam,
        "question_count": question_count,
        "computed_end_time": computed_end_time,
        "countdown_days": countdown_days,
        "countdown_hours": countdown_hours,
        "countdown_minutes": countdown_minutes,
        "can_start_exam": can_start_exam,
        "before_allowed_start": before_allowed_start,
        "after_end_time": after_end_time,
    }

    return render(request, "core/student_exam_scheduled_detail.html", context)


@login_required
@user_passes_test(is_student)
def student_exam_result(request, exam_id):
    user = request.user

    exam = get_object_or_404(
        Exam.objects.select_related("subject", "teacher"),
        id=exam_id,
    )

    attempt = (
        StudentExam.objects.filter(
            exam=exam,
            student=user,
            status__in=[
                StudentExam.Status.FINISHED,
                StudentExam.Status.FAILED_CHEATING,
            ],
        )
        .order_by("-created_at")
        .first()
    )

    if not attempt:
        messages.error(request, "لا توجد نتيجة متاحة لهذا الاختبار.", extra_tags="user:student")
        return HttpResponseRedirect(reverse("student_exams"))

    # Calculate actual total mark from exam questions
    total_mark = (
        ExamQuestion.objects.filter(exam=exam).aggregate(total=Sum("mark"))["total"]
        or 0
    )
    score = float(attempt.score or 0)
    score_percent = 0
    if total_mark > 0:
        score_percent = round((score / float(total_mark)) * 100)

    is_pass = score_percent >= 50

    total_questions = ExamQuestion.objects.filter(exam=exam).count()

    answers_qs = StudentAnswer.objects.filter(attempt=attempt)
    correct_count = answers_qs.filter(is_correct=True).count()
    wrong_count = answers_qs.filter(is_correct=False).count()

    time_spent_minutes = None
    if attempt.started_at and attempt.finished_at:
        delta = attempt.finished_at - attempt.started_at
        total_seconds = int(delta.total_seconds())
        time_spent_minutes = max(total_seconds // 60, 0)

    circle_circumference = 439.8
    circle_dasharray = circle_circumference
    circle_dashoffset = circle_circumference * (100 - score_percent) / 100 if score_percent >= 0 else circle_circumference

    context = {
        "exam": exam,
        "attempt": attempt,
        "total_mark": total_mark,
        "score": score,
        "score_percent": score_percent,
        "is_pass": is_pass,
        "total_questions": total_questions,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "time_spent_minutes": time_spent_minutes,
        "circle_dasharray": circle_dasharray,
        "circle_dashoffset": circle_dashoffset,
    }

    return render(request, "core/student_exam_result.html", context)


@login_required
@user_passes_test(is_student)
def student_exam_event(request, exam_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    user = request.user
    exam = get_object_or_404(
        Exam.objects.select_related("teacher"),
        id=exam_id,
    )

    # Check if student is explicitly allowed for this exam
    if not exam.allowed_students.filter(id=user.id).exists():
        return HttpResponseBadRequest("Not allowed for this exam")

    event_type = request.POST.get("event_type", "").strip()
    message = request.POST.get("message", "").strip()

    valid_types = {choice[0] for choice in ExamEvent.EventType.choices}
    if event_type not in valid_types:
        return HttpResponseBadRequest("Invalid event type")

    ExamEvent.objects.create(
        exam=exam,
        student=user,
        event_type=event_type,
        message=message,
    )

    attempt = StudentExam.objects.filter(
        exam=exam,
        student=user,
        status=StudentExam.Status.IN_PROGRESS,
    ).first()
    if attempt:
        from django.utils import timezone as _tz4

        attempt.last_activity_at = _tz4.now()
        attempt.save(update_fields=["last_activity_at"])

    return JsonResponse({"ok": True})


@login_required
@user_passes_test(is_student)
def student_exam_notifications(request, exam_id):
    user = request.user
    exam = get_object_or_404(
        Exam.objects.select_related("teacher"),
        id=exam_id,
    )

    # Check if student is explicitly allowed for this exam
    if not exam.allowed_students.filter(id=user.id).exists():
        raise Http404

    since_id_raw = request.GET.get("since_id", "").strip()
    since_id = 0
    if since_id_raw.isdigit():
        since_id = int(since_id_raw)

    qs = ExamNotification.objects.filter(exam=exam).filter(
        Q(recipient__isnull=True) | Q(recipient=user)
    )
    if since_id:
        qs = qs.filter(id__gt=since_id)
    qs = qs.select_related("sender").order_by("id")[:50]

    data = [
        {
            "id": n.id,
            "message": n.message,
            "created_at": n.created_at.isoformat(),
            "sender_name": n.sender.full_name or n.sender.username,
        }
        for n in qs
    ]
    return JsonResponse({"ok": True, "items": data})


@login_required
@user_passes_test(is_student)
def student_invitation_action(request, join_request_id):
    user = request.user
    if request.method != "POST":
        return HttpResponseRedirect(reverse("student_teachers"))

    join_request = (
        StudentJoinRequest.objects.filter(
            id=join_request_id,
            student=user,
            status=StudentJoinRequest.Status.PENDING,
        )
        .select_related("group", "teacher")
        .first()
    )

    if not join_request:
        messages.error(request, "هذه الدعوة لم تعد متاحة.", extra_tags="user:student")
        return HttpResponseRedirect(reverse("student_teachers"))

    action = request.POST.get("action", "").strip()

    if action == "accept":
        if join_request.group:
            group = join_request.group
            group.students.add(user)
        join_request.status = StudentJoinRequest.Status.ACCEPTED
        join_request.save(update_fields=["status"])
        messages.success(request, "تم قبول الدعوة بنجاح.", extra_tags="user:student")
    elif action == "reject":
        join_request.status = StudentJoinRequest.Status.REJECTED
        join_request.save(update_fields=["status"])
        messages.info(request, "تم رفض الدعوة.", extra_tags="user:student")

    return HttpResponseRedirect(reverse("student_teachers"))


@login_required
@user_passes_test(is_student)
def student_send_join_request(request, teacher_id):
    user = request.user
    teacher = (
        User.objects.filter(id=teacher_id, role="teacher")
        .distinct()
        .first()
    )
    if not teacher:
        messages.error(request, "لا يمكن إرسال طلب لهذا المدرس.", extra_tags="user:student")
        return HttpResponseRedirect(reverse("student_teachers"))

    existing_pending = StudentJoinRequest.objects.filter(
        student=user,
        teacher=teacher,
        status=StudentJoinRequest.Status.PENDING,
    ).exists()

    if existing_pending:
        messages.info(request, "لديك بالفعل طلب انضمام معلق لهذا المدرس.", extra_tags="user:student")
        return HttpResponseRedirect(reverse("student_teachers"))

    already_linked = (
        StudentJoinRequest.objects.filter(
            student=user,
            teacher=teacher,
            status=StudentJoinRequest.Status.ACCEPTED,
        ).exists()
        or Group.objects.filter(teacher=teacher, students=user).exists()
    )

    if already_linked:
        messages.info(request, "أنت بالفعل ضمن طلاب هذا المدرس.", extra_tags="user:student")
        return HttpResponseRedirect(reverse("student_teachers"))

    StudentJoinRequest.objects.create(
        student=user,
        teacher=teacher,
        group=None,
        status=StudentJoinRequest.Status.PENDING,
        source=StudentJoinRequest.Source.FROM_STUDENT,
    )
    messages.success(request, "تم إرسال طلب الانضمام إلى المدرس بنجاح.", extra_tags="user:student")
    return HttpResponseRedirect(reverse("student_teachers"))


@login_required
@user_passes_test(is_teacher)
def teacher_settings(request):
    user = request.user

    account_error = ""
    account_success = ""

    if request.method == "POST":
        if "profile_submit" in request.POST:
            full_name = request.POST.get("full_name", "").strip()
            email = request.POST.get("email", "").strip()
            user.full_name = full_name
            user.email = email
            user.save(update_fields=["full_name", "email"])
            account_success = "تم تحديث بيانات الحساب بنجاح."
        elif "password_submit" in request.POST:
            current_password = request.POST.get("current_password", "")
            new_password = request.POST.get("new_password", "")
            if not current_password or not new_password:
                account_error = "يرجى إدخال كلمة المرور الحالية والجديدة."
            elif not check_password(current_password, user.password):
                account_error = "كلمة المرور الحالية غير صحيحة."
            else:
                try:
                    validate_password(new_password, user)
                except ValidationError as e:
                    account_error = " ".join(e.messages)
                else:
                    user.set_password(new_password)
                    user.save(update_fields=["password"])
                    update_session_auth_hash(request, user)
                    account_success = "تم تحديث كلمة المرور بنجاح."

    context = {
        "account_error": account_error,
        "account_success": account_success,
    }
    return render(request, "core/teacher_settings.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_groups(request):
    user = request.user
    groups = (
        Group.objects.filter(teacher=user)
        .annotate(student_count=Count("students"))
        .order_by("name")
    )

    query = request.GET.get("q", "").strip()
    if query:
        groups = groups.filter(Q(name__icontains=query) | Q(code__icontains=query))

    selected_subject = request.GET.get("subject", "").strip()
    if selected_subject:
        groups = groups.filter(subject_id=selected_subject)

    subjects = Subject.objects.filter(teacher=user).order_by("name").only("id", "name")

    context = {
        "groups": groups,
        "query": query,
        "selected_subject": selected_subject,
        "subjects": subjects,
    }
    return render(request, "core/teacher_groups.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_students(request):
    user = request.user

    invite_error = ""
    invite_success = ""

    group_join_requests = (
        StudentJoinRequest.objects.filter(
            teacher=user,
            status=StudentJoinRequest.Status.PENDING,
            group__isnull=False,
            source=StudentJoinRequest.Source.FROM_STUDENT,
        )
        .select_related("student", "group")
        .order_by("-created_at")
    )
    general_join_requests = (
        StudentJoinRequest.objects.filter(
            teacher=user,
            status=StudentJoinRequest.Status.PENDING,
            group__isnull=True,
            source=StudentJoinRequest.Source.FROM_STUDENT,
        )
        .select_related("student")
        .order_by("-created_at")
    )

    if request.method == "POST":
        action = request.POST.get("action", "").strip()
        request_id = request.POST.get("request_id", "").strip()
        student_id = request.POST.get("student_id", "").strip()
        invite_email = request.POST.get("invite_email", "").strip()
        invite_group_id = request.POST.get("invite_group", "").strip()

        if action in {"accept_group", "reject_group", "accept_general", "reject_general"} and request_id:
            join_request = (
                StudentJoinRequest.objects.filter(id=request_id, teacher=user)
                .select_related("student", "group")
                .first()
            )
            if join_request:
                if action == "accept_group" and join_request.group:
                    group = join_request.group
                    student = join_request.student
                    group.students.add(student)
                    join_request.status = StudentJoinRequest.Status.ACCEPTED
                    join_request.save(update_fields=["status"])
                    messages.success(request, "تم قبول طلب الانضمام للمجموعة.")
                elif action == "reject_group" and join_request.group:
                    join_request.status = StudentJoinRequest.Status.REJECTED
                    join_request.save(update_fields=["status"])
                    messages.info(request, "تم رفض طلب الانضمام للمجموعة.")
                elif action == "accept_general" and not join_request.group:
                    join_request.status = StudentJoinRequest.Status.ACCEPTED
                    join_request.save(update_fields=["status"])
                    messages.success(request, "تم قبول طلب الانضمام.")
                elif action == "reject_general" and not join_request.group:
                    join_request.status = StudentJoinRequest.Status.REJECTED
                    join_request.save(update_fields=["status"])
                    messages.info(request, "تم رفض طلب الانضمام.")
            return HttpResponseRedirect(reverse("teacher_students"))

        if action == "remove_student" and student_id:
            try:
                from django.db import transaction
                with transaction.atomic():
                    student = (
                        User.objects.filter(id=student_id, role="student")
                        .distinct()
                        .first()
                    )
                    if student:
                        groups = Group.objects.filter(teacher=user, students=student)
                        for group in groups:
                            group.students.remove(student)
                        StudentJoinRequest.objects.filter(
                            student=student,
                            teacher=user,
                            status=StudentJoinRequest.Status.ACCEPTED,
                        ).update(status=StudentJoinRequest.Status.REJECTED)
                        messages.success(request, "تم إزالة الطالب من قوائمك الحالية.")
                    else:
                        messages.error(request, "الطالب غير موجود.")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error removing student {student_id}: {str(e)}")
                messages.error(request, f"فشل إزالة الطالب: {str(e)}")
            return HttpResponseRedirect(reverse("teacher_students"))

        if action == "invite_student":
            if not invite_email:
                invite_error = "يرجى إدخال بريد الطالب الإلكتروني."
            else:
                student = (
                    User.objects.filter(email__iexact=invite_email, role="student")
                    .distinct()
                    .first()
                )
                if not student:
                    invite_error = "لم يتم العثور على طالب بهذا البريد الإلكتروني."
                else:
                    if invite_group_id:
                        group = Group.objects.filter(id=invite_group_id, teacher=user).first()
                        if not group:
                            invite_error = "المجموعة المحددة غير صالحة."
                        else:
                            existing_pending = StudentJoinRequest.objects.filter(
                                student=student,
                                teacher=user,
                                group=group,
                                status=StudentJoinRequest.Status.PENDING,
                            ).exists()
                            if existing_pending:
                                invite_error = "هناك بالفعل دعوة أو طلب معلق لهذا الطالب في هذه المجموعة."
                            else:
                                StudentJoinRequest.objects.create(
                                    student=student,
                                    teacher=user,
                                    group=group,
                                    status=StudentJoinRequest.Status.PENDING,
                                    source=StudentJoinRequest.Source.FROM_TEACHER,
                                )
                                invite_success = "تم إرسال دعوة الانضمام إلى المجموعة، بانتظار قبول الطالب."
                    else:
                        existing_pending_general = StudentJoinRequest.objects.filter(
                            student=student,
                            teacher=user,
                            group__isnull=True,
                            status=StudentJoinRequest.Status.PENDING,
                        ).exists()
                        if existing_pending_general:
                            invite_error = "هناك بالفعل دعوة أو طلب انضمام عام معلق لهذا الطالب."
                        else:
                            existing_accepted = StudentJoinRequest.objects.filter(
                                student=student,
                                teacher=user,
                                status=StudentJoinRequest.Status.ACCEPTED,
                            ).exists()
                            if existing_accepted:
                                invite_error = "هذا الطالب موجود بالفعل ضمن طلابك."
                            else:
                                StudentJoinRequest.objects.create(
                                    student=student,
                                    teacher=user,
                                    group=None,
                                    status=StudentJoinRequest.Status.PENDING,
                                    source=StudentJoinRequest.Source.FROM_TEACHER,
                                )
                                invite_success = "تم إرسال دعوة عامة للطالب، بانتظار قبوله."

    students = (
        User.objects.filter(role="student", is_active=True, is_staff=False)
        .filter(
            Q(student_groups__teacher=user)
            | Q(subject_enrollments__teacher=user)
            | Q(
                join_requests__teacher=user,
                join_requests__status=StudentJoinRequest.Status.ACCEPTED,
            )
        )
        .distinct()
        .order_by("full_name", "username")
    )

    query = request.GET.get("q", "").strip()
    if query:
        students = students.filter(
            Q(full_name__icontains=query)
            | Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(id__icontains=query)
        )

    students_count = students.count()
    pending_join_requests_count = group_join_requests.count() + general_join_requests.count()

    context = {
        "group_join_requests": group_join_requests,
        "general_join_requests": general_join_requests,
        "teacher_groups_for_invite": Group.objects.filter(teacher=user).order_by("name"),
        "pending_join_requests_count": pending_join_requests_count,
        "students": students,
        "students_count": students_count,
        "query": query,
        "invite_error": invite_error,
        "invite_success": invite_success,
    }
    return render(request, "core/teacher_students.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_group_detail(request, group_id):
    user = request.user
    group = get_object_or_404(Group, id=group_id, teacher=user)

    chat_messages = (
        GroupMessage.objects.filter(group=group)
        .select_related("sender")
        .order_by("created_at")
    )

    message_error = ""

    if request.method == "POST":
        content = request.POST.get("message", "").strip()
        if not content:
            message_error = "يرجى كتابة رسالة قبل الإرسال."
        else:
            GroupMessage.objects.create(
                group=group,
                sender=user,
                content=content,
            )
            return redirect("teacher_group_detail", group_id=group.id)

    members = group.students.all().order_by("full_name", "username")

    context = {
        "group": group,
        "chat_messages": chat_messages,
        "message_error": message_error,
        "members": members,
    }
    return render(request, "core/teacher_group_detail.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_group_create(request):
    user = request.user

    errors = {}
    form_data = {
        "name": "",
        "subject": "",
    }

    # Get available students for this teacher
    students = (
        User.objects.filter(role="student", is_active=True, is_staff=False)
        .filter(
            Q(student_groups__teacher=user)
            | Q(subject_enrollments__teacher=user)
            | Q(
                join_requests__teacher=user,
                join_requests__status=StudentJoinRequest.Status.ACCEPTED,
            )
        )
        .distinct()
        .order_by("full_name", "username")
    )

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        subject_id = request.POST.get("subject", "").strip()
        selected_students_raw = request.POST.get("selected_students", "").strip()
        selected_students_ids = [
            s for s in selected_students_raw.split(",") if s.strip()
        ]

        form_data["name"] = name
        form_data["subject"] = subject_id

        if not name:
            errors["name"] = "يرجى إدخال اسم المجموعة."

        subject_obj = None
        if not subject_id:
            errors["subject"] = "يرجى اختيار المادة الدراسية."
        else:
            subject_obj = Subject.objects.filter(id=subject_id, teacher=user).first()
            if not subject_obj:
                errors["subject"] = "المادة المختارة غير صالحة."

        code = ""
        if not errors:
            base_code = name or "group"
            base_code = base_code.replace(" ", "").lower()[:20] or "group"
            suffix = 1
            while True:
                candidate = f"{base_code}{suffix}"
                if not Group.objects.filter(code=candidate).exists():
                    code = candidate
                    break
                suffix += 1

        if not errors:
            group = Group.objects.create(
                name=name,
                code=code,
                subject=subject_obj,
                teacher=user,
            )
            
            # Add selected students to the group
            if selected_students_ids:
                selected_students_qs = students.filter(id__in=selected_students_ids)
                if selected_students_qs.exists():
                    group.students.add(*selected_students_qs)
            
            messages.success(request, "تم إنشاء المجموعة بنجاح.", extra_tags="user:teacher")
            return HttpResponseRedirect(reverse("teacher_groups"))

    selected_students_ids = []
    selected_students_raw = ""
    
    # Convert to integers for template comparison
    selected_students_int = [int(sid) for sid in selected_students_ids if sid.strip().isdigit()]

    context = {
        "errors": errors,
        "form_data": form_data,
        "subjects": Subject.objects.filter(teacher=user).order_by("name").only(
            "id", "name"
        ),
        "students": students,
        "selected_students": selected_students_int,
        "selected_students_raw": selected_students_raw,
        "is_edit": False,
        "group": None,
    }
    return render(request, "core/teacher_group_create.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_group_edit(request, group_id):
    user = request.user
    group = get_object_or_404(Group, id=group_id, teacher=user)

    errors = {}
    form_data = {
        "name": group.name,
        "description": "",
        "subject": group.subject_id or "",
    }

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        subject_id = request.POST.get("subject", "").strip()

        form_data["name"] = name
        form_data["description"] = description
        form_data["subject"] = subject_id

        if not name:
            errors["name"] = "يرجى إدخال اسم المجموعة."

        subject_obj = None
        if not subject_id:
            errors["subject"] = "يرجى اختيار المادة الدراسية."
        else:
            subject_obj = Subject.objects.filter(id=subject_id, teacher=user).first()
            if not subject_obj:
                errors["subject"] = "المادة المختارة غير صالحة."

        if not errors:
            group.name = name
            group.subject = subject_obj
            group.save()
            messages.success(request, "تم تعديل بيانات المجموعة بنجاح.", extra_tags="user:teacher")
            return HttpResponseRedirect(reverse("teacher_groups"))

    context = {
        "errors": errors,
        "form_data": form_data,
        "subjects": Subject.objects.filter(teacher=user).order_by("name").only(
            "id", "name"
        ),
        "group": group,
        "is_edit": True,
    }
    return render(request, "core/teacher_group_create.html", context)


@login_required
@user_passes_test(is_teacher)
@require_POST
def teacher_group_delete(request, group_id):
    """
    حذف مجموعة
    """
    user = request.user
    group = get_object_or_404(Group, id=group_id, teacher=user)
    
    try:
        group_name = group.name
        group.delete()
        messages.success(request, f"تم حذف المجموعة '{group_name}' بنجاح.", extra_tags="user:teacher")
    except Exception as e:
        logger.error(f"Error deleting group {group_id}: {str(e)}")
        messages.error(request, f"فشل حذف المجموعة: {str(e)}", extra_tags="user:teacher")
    
    return HttpResponseRedirect(reverse("teacher_groups"))


@login_required
@user_passes_test(is_teacher)
def teacher_exams(request):
    """
    إدارة اختبارات المدرس: عرض كافة الاختبارات التي قام بإنشائها مع حالاتها المختلفة.
    يسمح بالوصول إلى وظائف الإنشاء، التعديل، المراقبة، وحذف الاختبارات.
    """
    user = request.user

    exams = (
        Exam.objects.filter(teacher=user)
        .select_related("subject")
        .annotate(
            questions_count=Count("exam_questions", distinct=True),
            submitted_attempts_count=Count(
                "attempts",
                filter=Q(attempts__status__in=[StudentExam.Status.FINISHED, StudentExam.Status.FAILED_CHEATING]),
                distinct=True
            ),
            allowed_students_count=Count("allowed_students", distinct=True)
        )
        .order_by("-start_time")
    )
    _sync_exam_statuses(exams)

    query = request.GET.get("q", "").strip()
    if query:
        exams = exams.filter(title__icontains=query)

    selected_status = request.GET.get("status", "").strip()
    selected_subject = request.GET.get("subject", "").strip()
    if selected_status:
        exams = exams.filter(status=selected_status)

    if selected_subject:
        exams = exams.filter(subject_id=selected_subject)

    subjects = Subject.objects.filter(teacher=user).order_by("name").only("id", "name")

    active_subject_name = ""
    if selected_subject:
        active_subject = subjects.filter(id=selected_subject).first()
        if active_subject:
            active_subject_name = active_subject.name

    # Calculate total_participants for each exam dynamically
    exams_list = list(exams)
    for exam in exams_list:
        # Use allowed_students count if available, otherwise use total_participants field
        if exam.allowed_students_count > 0:
            exam.total_participants_display = exam.allowed_students_count
        else:
            exam.total_participants_display = exam.total_participants or 0

    total_exams = len(exams_list)
    scheduled_exams = sum(1 for e in exams_list if e.status == Exam.Status.SCHEDULED)
    finished_exams = sum(1 for e in exams_list if e.status == Exam.Status.FINISHED)

    context = {
        "exams": exams_list,
        "total_exams": total_exams,
        "scheduled_exams": scheduled_exams,
        "finished_exams": finished_exams,
        "query": query,
        "selected_status": selected_status,
        "selected_subject": selected_subject,
        "active_subject_name": active_subject_name,
        "subjects": subjects,
    }
    return render(request, "core/teacher_exams.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_exam_questions(request, exam_id):
    user = request.user
    exam = get_object_or_404(Exam, id=exam_id, teacher=user)

    subject = exam.subject
    base_questions = Question.objects.filter(subject=subject, teacher=user)

    query = request.GET.get("q", "").strip()
    question_type = request.GET.get("question_type", "").strip()
    difficulty = request.GET.get("difficulty", "").strip()

    if query:
        base_questions = base_questions.filter(text__icontains=query)

    valid_types = {choice[0] for choice in Question.QuestionType.choices}
    if question_type and question_type in valid_types:
        base_questions = base_questions.filter(question_type=question_type)

    valid_difficulties = {choice[0] for choice in Question.Difficulty.choices}
    if difficulty and difficulty in valid_difficulties:
        base_questions = base_questions.filter(difficulty=difficulty)

    base_questions = base_questions.order_by("-created_at")

    existing_links = ExamQuestion.objects.filter(exam=exam).select_related("question")
    existing_ids = set(existing_links.values_list("question_id", flat=True))

    if request.method == "POST":
        selected_ids_raw = request.POST.getlist("selected_questions")
        try:
            selected_ids = {int(q_id) for q_id in selected_ids_raw}
        except ValueError:
            selected_ids = set()

        available_ids = set(
            base_questions.filter(id__in=selected_ids).values_list("id", flat=True)
        )
        selected_ids = available_ids

        try:
            ExamQuestion.objects.filter(exam=exam).exclude(question_id__in=selected_ids).delete()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating exam questions for exam {exam.id}: {str(e)}")
            messages.error(request, f"فشل تحديث قائمة الأسئلة: {str(e)}")
            return redirect("teacher_exam_questions", exam_id=exam.id)

        current_links = {
            link.question_id: link for link in ExamQuestion.objects.filter(exam=exam)
        }

        # Calculate equal distribution of marks if marking_type is 'equal'
        if exam.marking_type == 'equal' and exam.total_mark and len(selected_ids) > 0:
            equal_mark = round(exam.total_mark / len(selected_ids), 2)
        else:
            equal_mark = None

        for order_index, question_id in enumerate(selected_ids, start=1):
            if question_id in current_links:
                link = current_links[question_id]
                link.order = order_index
                # Apply equal mark distribution if enabled
                if equal_mark is not None:
                    link.mark = equal_mark
                link.save(update_fields=["order", "mark"])
            else:
                question_obj = Question.objects.filter(
                    id=question_id, subject=subject, teacher=user
                ).first()
                if question_obj:
                    # Use equal mark if enabled, otherwise use question's default mark
                    mark_to_use = equal_mark if equal_mark is not None else question_obj.mark
                    ExamQuestion.objects.create(
                        exam=exam,
                        question=question_obj,
                        order=order_index,
                        mark=mark_to_use,
                    )

        # Show success message with details
        if exam.marking_type == 'equal' and equal_mark is not None:
            messages.success(request, f"تم تحديث قائمة الأسئلة بنجاح! تم توزيع {equal_mark} علامة لكل سؤال من أصل {exam.total_mark} علامة كلية.")
        else:
            messages.success(request, "تم تحديث قائمة أسئلة الاختبار بنجاح.")
        return redirect("teacher_exam_questions", exam_id=exam.id)

    # Check if we need to redistribute marks based on marking_type
    if exam.marking_type == 'equal' and exam.total_mark and existing_links.exists():
        # Redistribute marks equally among all existing questions
        total_questions = existing_links.count()
        equal_mark = round(exam.total_mark / total_questions, 2)
        
        # Update all existing questions with equal mark
        for link in existing_links:
            if link.mark != equal_mark:
                link.mark = equal_mark
                link.save(update_fields=["mark"])
    
    questions = list(base_questions)
    selected_questions = []
    for q in questions:
        selected = q.id in existing_ids
        selected_questions.append(
            {
                "obj": q,
                "selected": selected,
            }
        )

    total_selected = existing_links.count()
    total_marks = existing_links.aggregate(total=Sum("mark"))["total"] or 0

    context = {
        "exam": exam,
        "questions": selected_questions,
        "query": query,
        "question_type": question_type,
        "difficulty": difficulty,
        "total_selected": total_selected,
        "total_marks": total_marks,
    }

    return render(request, "core/teacher_exam_questions.html", context)

@login_required
@user_passes_test(is_teacher)
def teacher_reports(request):
    """
    نظام المراسلات والتقارير للمدرس:
    - التواصل مع الإدارة (Supervisors).
    - إرسال رسائل وتوجيهات للطلاب.
    - عرض صندوق الوارد للرسائل المستلمة.
    """
    user = request.user

    supervisors = User.objects.filter(is_staff=True).order_by("full_name", "username")
    students = (
        User.objects.filter(role="student", is_active=True, is_staff=False)
        .filter(
            Q(student_groups__teacher=user)
            | Q(subject_enrollments__teacher=user)
            | Q(
                join_requests__teacher=user,
                join_requests__status=StudentJoinRequest.Status.ACCEPTED,
            )
        )
        .distinct()
        .order_by("full_name", "username")
    )

    reply_to_id = request.GET.get("reply_to", "").strip()
    reply_to_message = None
    reply_target_type = ""
    if reply_to_id:
        reply_candidate = (
            Message.objects.filter(id=reply_to_id, recipient=user)
            .select_related("sender")
            .first()
        )
        if reply_candidate:
            reply_to_message = reply_candidate
            if reply_candidate.sender.is_staff:
                reply_target_type = "supervisor"
            elif reply_candidate.sender.role == "student":
                reply_target_type = "student"

    if request.method == "POST":
        form_type = request.POST.get("form_type", "").strip()
        if form_type == "to_supervisor":
            title = request.POST.get("title", "").strip()
            body = request.POST.get("body", "").strip()
            category = request.POST.get("category", "").strip()
            in_reply_to_id = request.POST.get("in_reply_to", "").strip()
            in_reply_to = None
            if in_reply_to_id:
                in_reply_to = (
                    Message.objects.filter(id=in_reply_to_id, recipient=user)
                    .select_related("sender")
                    .first()
                )
            if body and supervisors.exists():
                for supervisor in supervisors:
                    Message.objects.create(
                        sender=user,
                        recipient=supervisor,
                        direction=Message.Direction.TEACHER_TO_SUPERVISOR,
                        title=title,
                        body=body,
                        category=category,
                        in_reply_to=in_reply_to,
                    )
                messages.success(request, "تم إرسال الرسالة للمشرفين بنجاح.", extra_tags="user:teacher")
                return HttpResponseRedirect(reverse("teacher_reports"))
            elif not body:
                messages.error(request, "يرجى كتابة نص الرسالة.", extra_tags="user:teacher")
            elif not supervisors.exists():
                messages.error(request, "لا يوجد مشرفون متاحون.", extra_tags="user:teacher")
        elif form_type == "to_student":
            student_id = request.POST.get("student_id", "").strip()
            title = request.POST.get("student_title", "").strip()
            body = request.POST.get("student_body", "").strip()
            in_reply_to_id = request.POST.get("in_reply_to", "").strip()
            in_reply_to = None
            if in_reply_to_id:
                in_reply_to = (
                    Message.objects.filter(id=in_reply_to_id, recipient=user)
                    .select_related("sender")
                    .first()
                )
            if body and student_id:
                student = students.filter(id=student_id).first()
                if student:
                    Message.objects.create(
                        sender=user,
                        recipient=student,
                        direction=Message.Direction.TEACHER_TO_STUDENT,
                        title=title,
                        body=body,
                        in_reply_to=in_reply_to,
                    )
                    messages.success(request, "تم إرسال الرسالة للطالب بنجاح.", extra_tags="user:teacher")
                    return HttpResponseRedirect(reverse("teacher_reports"))
                else:
                    messages.error(request, "الطالب المحدد غير مرتبط بك أو غير موجود.", extra_tags="user:teacher")
            elif not body:
                messages.error(request, "يرجى كتابة نص الرسالة.", extra_tags="user:teacher")
            elif not student_id:
                messages.error(request, "يرجى اختيار طالب.", extra_tags="user:teacher")

    inbox_queryset = Message.objects.filter(recipient=user)
    if request.method != "POST":
        inbox_queryset.filter(is_read=False).update(is_read=True)
    supervisor_messages = (
        inbox_queryset.filter(sender__is_staff=True)
        .select_related("sender")
        .order_by("-created_at")[:10]
    )
    student_messages = (
        inbox_queryset.filter(sender__role="student")
        .select_related("sender")
        .order_by("-created_at")[:20]
    )

    total_messages = inbox_queryset.count()
    unread_messages = inbox_queryset.filter(is_read=False).count()

    replied_count = Message.objects.filter(
        sender=user, in_reply_to__isnull=False
    ).count()

    context = {
        "supervisors": supervisors,
        "students": students,
        "supervisor_messages": supervisor_messages,
        "student_messages": student_messages,
        "total_messages": total_messages,
        "unread_messages": unread_messages,
        "replied_count": replied_count,
        "reply_to_message": reply_to_message,
        "reply_target_type": reply_target_type,
    }
    return render(request, "core/teacher_reports.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_exam_monitor(request, exam_id):
    """
    مراقبة الاختبار في الوقت الفعلي:
    - تتبع محاولات الطلاب (داخل الاختبار، منتهي، متغيب).
    - عرض تنبيهات الغش (تبديل التبويبات، محاولات الخروج).
    - إمكانية إنهاء محاولة طالب يدوياً.
    """
    user = request.user
    exam = get_object_or_404(Exam, id=exam_id, teacher=user)

    attempts_qs = StudentExam.objects.filter(exam=exam).select_related("student")

    total_students = exam.allowed_students.count() if exam.allowed_students.exists() else (exam.total_participants or attempts_qs.count())

    submitted = attempts_qs.filter(
        status__in=[StudentExam.Status.FINISHED, StudentExam.Status.FAILED_CHEATING]
    ).count()

    from django.utils import timezone as _tz_mon
    now = _tz_mon.now()
    stale_seconds = 45
    from datetime import timedelta
    in_progress_qs = attempts_qs.filter(status=StudentExam.Status.IN_PROGRESS)
    active_students = in_progress_qs.filter(last_activity_at__gte=now - timedelta(seconds=stale_seconds)).count()
    started_students = attempts_qs.values_list("student_id", flat=True).distinct().count()
    absent = max(total_students - started_students, 0)
    suspicions = ExamEvent.objects.filter(
        exam=exam,
        event_type__in=[
            ExamEvent.EventType.CHEATING_VISIBILITY,
            ExamEvent.EventType.CHEATING_CLIPBOARD,
        ],
    ).count()

    stats = {
        "total_students": total_students,
        "active_students": active_students,
        "submitted": submitted,
        "absent": absent,
        "suspicions": suspicions,
    }

    remaining_time_display = "--:--"
    computed_end_time = exam.end_time
    if computed_end_time is None:
        from datetime import timedelta

        computed_end_time = exam.start_time + timedelta(minutes=exam.duration_minutes)
    remaining = computed_end_time - now
    if remaining.total_seconds() > 0:
        total_seconds = int(remaining.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        remaining_time_display = f"{minutes:02d}:{seconds:02d}"
    else:
        remaining_time_display = "00:00"

    total_questions = ExamQuestion.objects.filter(exam=exam).count() or 1
    answers_counts = {
        item["attempt_id"]: item["cnt"]
        for item in StudentAnswer.objects.filter(attempt__in=attempts_qs)
        .values("attempt_id")
        .annotate(cnt=Count("id"))
    }

    student_tiles = []
    for attempt in attempts_qs:
        student = attempt.student
        name = student.full_name or student.username
        answers_count = answers_counts.get(attempt.id, 0)
        progress = int((answers_count / total_questions) * 100)
        if attempt.status == StudentExam.Status.IN_PROGRESS:
            last_activity = attempt.last_activity_at or attempt.started_at or attempt.created_at
            if last_activity and (now - last_activity).total_seconds() <= stale_seconds:
                status = "active"
            else:
                status = "offline"
        elif attempt.status in [
            StudentExam.Status.FINISHED,
            StudentExam.Status.FAILED_CHEATING,
        ]:
            status = "submitted"
        else:
            status = "offline"
        mic_muted = False
        student_tiles.append(
            {
                "student_id": student.id,
                "attempt_id": attempt.id,
                "name": name,
                "status": status,
                "progress": progress,
                "mic_muted": mic_muted,
            }
        )

    events_qs = (
        ExamEvent.objects.filter(exam=exam)
        .select_related("student")
        .order_by("-created_at")[:20]
    )

    activity_log = []
    from django.utils import timezone as _tz3

    now = _tz3.now()
    for ev in events_qs:
        student = ev.student
        name = student.full_name or student.username
        parts = [p for p in (name or "").split() if p]
        initials = "".join(p[0] for p in parts[:2]) if parts else (name[:2] if name else "")

        delta = now - ev.created_at
        seconds = int(delta.total_seconds())
        if seconds < 60:
            time_label = "الآن"
        elif seconds < 3600:
            minutes = seconds // 60
            time_label = f"منذ {minutes} دقيقة"
        else:
            hours = seconds // 3600
            time_label = f"منذ {hours} ساعة"

        if ev.event_type in [
            ExamEvent.EventType.CHEATING_VISIBILITY,
            ExamEvent.EventType.CHEATING_CLIPBOARD,
        ]:
            log_type = "alert"
            title = "تنبيه أمني"
            message = ev.message or "تم رصد نشاط قد يشير إلى محاولة غش."
        elif ev.event_type == ExamEvent.EventType.SUBMIT:
            log_type = "submit"
            title = "تسليم اختبار"
            message = ev.message or "قام الطالب بإنهاء الاختبار وتسليم الإجابات."
        elif ev.event_type == ExamEvent.EventType.JOIN:
            log_type = "start"
            title = "بدء الاختبار"
            message = ev.message or "التحق الطالب بالاختبار."
        else:
            log_type = "progress"
            title = "نشاط"
            message = ev.message or "تم تسجيل نشاط جديد للطالب."

        activity_log.append(
            {
                "type": log_type,
                "title": title,
                "time": time_label,
                "message": message,
                "student_name": name,
                "initials": initials,
            }
        )

    context = {
        "exam": exam,
        "stats": stats,
        "students": student_tiles,
        "activity_log": activity_log,
        "remaining_time_display": remaining_time_display,
    }
    return render(request, "core/teacher_exam_monitor.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_exam_monitor_data(request, exam_id):
    user = request.user
    exam = get_object_or_404(Exam, id=exam_id, teacher=user)

    attempts_qs = StudentExam.objects.filter(exam=exam).select_related("student")

    from django.utils import timezone as _tz_mon
    from datetime import timedelta

    now = _tz_mon.now()
    stale_seconds = 45

    total_students = exam.allowed_students.count() if exam.allowed_students.exists() else (exam.total_participants or attempts_qs.count())
    submitted = attempts_qs.filter(
        status__in=[StudentExam.Status.FINISHED, StudentExam.Status.FAILED_CHEATING]
    ).count()
    started_students = attempts_qs.values_list("student_id", flat=True).distinct().count()
    absent = max(total_students - started_students, 0)
    in_progress_qs = attempts_qs.filter(status=StudentExam.Status.IN_PROGRESS)
    active_students = in_progress_qs.filter(
        last_activity_at__gte=now - timedelta(seconds=stale_seconds)
    ).count()

    total_questions = ExamQuestion.objects.filter(exam=exam).count() or 1
    answers_counts = {
        item["attempt_id"]: item["cnt"]
        for item in StudentAnswer.objects.filter(attempt__in=attempts_qs)
        .values("attempt_id")
        .annotate(cnt=Count("id"))
    }

    students = []
    for attempt in attempts_qs:
        student = attempt.student
        answers_count = answers_counts.get(attempt.id, 0)
        progress = int((answers_count / total_questions) * 100)
        if attempt.status == StudentExam.Status.IN_PROGRESS:
            last_activity = attempt.last_activity_at or attempt.started_at or attempt.created_at
            if last_activity and (now - last_activity).total_seconds() <= stale_seconds:
                status = "active"
            else:
                status = "offline"
        elif attempt.status in [
            StudentExam.Status.FINISHED,
            StudentExam.Status.FAILED_CHEATING,
        ]:
            status = "submitted"
        else:
            status = "offline"

        students.append(
            {
                "student_id": student.id,
                "attempt_id": attempt.id,
                "name": student.full_name or student.username,
                "status": status,
                "progress": progress,
                "mic_muted": False,
            }
        )

    computed_end_time = exam.end_time
    if computed_end_time is None:
        computed_end_time = exam.start_time + timedelta(minutes=exam.duration_minutes)
    remaining = computed_end_time - now
    remaining_seconds = int(remaining.total_seconds())
    if remaining_seconds < 0:
        remaining_seconds = 0

    events_qs = (
        ExamEvent.objects.filter(exam=exam)
        .select_related("student")
        .order_by("-created_at")[:20]
    )
    activity_log = []
    for ev in events_qs:
        student = ev.student
        name = student.full_name or student.username
        parts = [p for p in (name or "").split() if p]
        initials = "".join(p[0] for p in parts[:2]) if parts else (name[:2] if name else "")

        delta = now - ev.created_at
        seconds = int(delta.total_seconds())
        if seconds < 60:
            time_label = "الآن"
        elif seconds < 3600:
            minutes = seconds // 60
            time_label = f"منذ {minutes} دقيقة"
        else:
            hours = seconds // 3600
            time_label = f"منذ {hours} ساعة"

        if ev.event_type in [
            ExamEvent.EventType.CHEATING_VISIBILITY,
            ExamEvent.EventType.CHEATING_CLIPBOARD,
        ]:
            log_type = "alert"
            title = "تنبيه أمني"
            message = ev.message or "تم رصد نشاط قد يشير إلى محاولة غش."
        elif ev.event_type == ExamEvent.EventType.SUBMIT:
            log_type = "submit"
            title = "تسليم اختبار"
            message = ev.message or "قام الطالب بإنهاء الاختبار وتسليم الإجابات."
        elif ev.event_type == ExamEvent.EventType.JOIN:
            log_type = "start"
            title = "بدء الاختبار"
            message = ev.message or "التحق الطالب بالاختبار."
        else:
            log_type = "progress"
            title = "نشاط"
            message = ev.message or "تم تسجيل نشاط جديد للطالب."

        activity_log.append(
            {
                "type": log_type,
                "title": title,
                "time": time_label,
                "message": message,
                "student_name": name,
                "initials": initials,
            }
        )

    return JsonResponse(
        {
            "ok": True,
            "stats": {
                "total_students": total_students,
                "active_students": active_students,
                "submitted": submitted,
                "absent": absent,
            },
            "students": students,
            "remaining_seconds": remaining_seconds,
            "activity_log": activity_log,
        }
    )


# ============================================================================
# PROCTOR SYSTEM - نظام المراقبة المتقدم
# ============================================================================

@login_required
def proctor_init_session(request, exam_id):
    """
    تهيئة جلسة المراقبة للطالب عند بدء الاختبار
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=400)
    
    user = request.user
    from .models import ProctorSession, ProctorAudioStream
    
    try:
        exam = get_object_or_404(Exam, id=exam_id)
        
        # التحقق من أن الطالب مسموح له
        if not exam.allowed_students.filter(id=user.id).exists():
            logger.warning(f"Student {user.id} not allowed for exam {exam_id}")
            return JsonResponse({"ok": False, "error": "غير مصرح لك بالوصول لهذا الاختبار"}, status=403)
        
        # الحصول على المحاولة
        attempt = StudentExam.objects.filter(exam=exam, student=user).first()
        
        if not attempt:
            logger.warning(f"No StudentExam found for student {user.id} and exam {exam_id}")
            return JsonResponse({"ok": False, "error": "لم يتم العثور على محاولة الاختبار"}, status=404)
        
        # إنشاء أو تحديث الجلسة
        session, created = ProctorSession.objects.get_or_create(
            exam=exam,
            student=user,
            defaults={
                "student_exam": attempt,
                "is_active": True,
            }
        )
        
        if not created:
            session.is_active = True
            session.student_exam = attempt
            session.save()
        
        # إنشاء أو الحصول على audio stream
        audio_stream, _ = ProctorAudioStream.objects.get_or_create(
            session=session,
            defaults={"status": ProctorAudioStream.StreamStatus.WAITING}
        )
        
        logger.info(f"Proctor session initialized: session_id={session.id}, student={user.id}, exam={exam_id}")
        
        return JsonResponse({
            "ok": True,
            "session_id": session.id,
            "audio_stream_id": audio_stream.id,
        })
    
    except Exam.DoesNotExist:
        logger.error(f"Exam {exam_id} not found")
        return JsonResponse({"ok": False, "error": "الاختبار غير موجود"}, status=404)
    except Exception as e:
        logger.error(f"Error in proctor_init_session: {e}", exc_info=True)
        return JsonResponse({"ok": False, "error": f"خطأ في تهيئة الجلسة: {str(e)}"}, status=500)


@login_required
def proctor_upload_snapshot(request, exam_id):
    """
    استقبال snapshot من كاميرا الطالب (بدون حفظ - فقط للعرض المباشر)
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)
    
    user = request.user
    from .models import ProctorSession
    from django.utils import timezone
    
    try:
        exam = get_object_or_404(Exam, id=exam_id)
        session = get_object_or_404(ProctorSession, exam=exam, student=user, is_active=True)
        
        # الحصول على بيانات الصورة من body
        import json
        data = json.loads(request.body)
        image_data = data.get("image")
        
        if not image_data:
            return JsonResponse({"error": "No image data"}, status=400)
        
        # حفظ الصورة في الذاكرة المؤقتة فقط (لا نحفظها على الديسك)
        # نحفظ آخر snapshot في peer_connection_data كـ base64
        session.peer_connection_data['last_snapshot_base64'] = image_data
        session.last_snapshot_at = timezone.now()
        session.snapshots_count += 1
        session.save(update_fields=["peer_connection_data", "last_snapshot_at", "snapshots_count"])
        
        return JsonResponse({
            "ok": True,
            "count": session.snapshots_count,
        })
    
    except Exception as e:
        logger.error(f"Error in proctor_upload_snapshot: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def proctor_signal(request, exam_id):
    """
    WebRTC signaling endpoint للطالب
    - إرسال offer/answer/ice candidates
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)
    
    user = request.user
    from .models import ProctorSession, ProctorAudioStream
    import json
    
    try:
        exam = get_object_or_404(Exam, id=exam_id)
        session = get_object_or_404(ProctorSession, exam=exam, student=user, is_active=True)
        audio_stream = get_object_or_404(ProctorAudioStream, session=session)
        
        data = json.loads(request.body)
        signal_type = data.get("type")
        
        if signal_type == "offer":
            # حفظ SDP offer من الطالب
            audio_stream.offer_sdp = data.get("sdp", "")
            audio_stream.status = ProctorAudioStream.StreamStatus.ACTIVE
            from django.utils import timezone
            if not audio_stream.started_at:
                audio_stream.started_at = timezone.now()
            audio_stream.save()
            
            return JsonResponse({
                "ok": True,
                "message": "Offer received",
            })
        
        elif signal_type == "ice_candidate":
            # إضافة ICE candidate
            candidate = data.get("candidate")
            if candidate:
                candidates = audio_stream.ice_candidates or []
                candidates.append(candidate)
                audio_stream.ice_candidates = candidates
                audio_stream.save()
            
            return JsonResponse({"ok": True})
        
        elif signal_type == "get_answer":
            # الحصول على answer من المدرس (إن وُجد)
            return JsonResponse({
                "ok": True,
                "answer": audio_stream.answer_sdp or None,
            })
        
        else:
            return JsonResponse({"error": "Unknown signal type"}, status=400)
    
    except Exception as e:
        logger.error(f"Error in proctor_signal: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@user_passes_test(is_teacher)
def proctor_teacher_signal(request, exam_id, student_id):
    """
    WebRTC signaling endpoint للمدرس
    - إرسال answer للطالب
    - الحصول على offer من الطالب
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)
    
    user = request.user
    from .models import ProctorSession, ProctorAudioStream
    import json
    
    try:
        exam = get_object_or_404(Exam, id=exam_id, teacher=user)
        session = get_object_or_404(
            ProctorSession,
            exam=exam,
            student_id=student_id,
            is_active=True
        )
        audio_stream = get_object_or_404(ProctorAudioStream, session=session)
        
        data = json.loads(request.body)
        signal_type = data.get("type")
        
        if signal_type == "answer":
            # حفظ SDP answer من المدرس
            audio_stream.answer_sdp = data.get("sdp", "")
            audio_stream.save()
            
            return JsonResponse({
                "ok": True,
                "message": "Answer sent to student",
            })
        
        elif signal_type == "get_offer":
            # الحصول على offer من الطالب
            return JsonResponse({
                "ok": True,
                "offer": audio_stream.offer_sdp or None,
                "ice_candidates": audio_stream.ice_candidates or [],
            })
        
        elif signal_type == "ice_candidate":
            # إضافة ICE candidate من المدرس (نادر لكن ممكن)
            candidate = data.get("candidate")
            if candidate:
                candidates = audio_stream.ice_candidates or []
                candidates.append(candidate)
                audio_stream.ice_candidates = candidates
                audio_stream.save()
            
            return JsonResponse({"ok": True})
        
        else:
            return JsonResponse({"error": "Unknown signal type"}, status=400)
    
    except Exception as e:
        logger.error(f"Error in proctor_teacher_signal: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@user_passes_test(is_teacher)
def proctor_get_snapshots(request, exam_id, student_id):
    """
    الحصول على آخر snapshot للطالب (من الذاكرة - بدون حفظ)
    """
    user = request.user
    from .models import ProctorSession
    
    try:
        exam = get_object_or_404(Exam, id=exam_id, teacher=user)
        session = get_object_or_404(
            ProctorSession,
            exam=exam,
            student_id=student_id,
        )
        
        # الحصول على آخر snapshot من peer_connection_data (base64)
        last_snapshot_base64 = session.peer_connection_data.get('last_snapshot_base64')
        
        return JsonResponse({
            "ok": True,
            "total_count": session.snapshots_count,
            "last_snapshot_base64": last_snapshot_base64,
            "last_snapshot_at": session.last_snapshot_at.isoformat() if session.last_snapshot_at else None,
        })
    
    except Exception as e:
        logger.error(f"Error in proctor_get_snapshots: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@user_passes_test(is_teacher)
def proctor_end_session(request, exam_id, student_id):
    """
    إنهاء جلسة المراقبة للطالب
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)
    
    user = request.user
    from .models import ProctorSession, ProctorAudioStream
    from django.utils import timezone
    
    try:
        exam = get_object_or_404(Exam, id=exam_id, teacher=user)
        session = get_object_or_404(
            ProctorSession,
            exam=exam,
            student_id=student_id,
        )
        
        session.is_active = False
        session.ended_at = timezone.now()
        session.save()
        
        # إنهاء audio stream
        try:
            audio_stream = session.audio_stream
            audio_stream.status = ProctorAudioStream.StreamStatus.ENDED
            audio_stream.ended_at = timezone.now()
            audio_stream.save()
        except ProctorAudioStream.DoesNotExist:
            pass
        
        return JsonResponse({"ok": True})
    
    except Exception as e:
        logger.error(f"Error in proctor_end_session: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@user_passes_test(is_teacher)
def teacher_exam_end(request, exam_id):
    if request.method != "POST":
        return HttpResponseRedirect(reverse("teacher_exam_monitor", args=[exam_id]))

    user = request.user
    exam = get_object_or_404(Exam, id=exam_id, teacher=user)

    from django.utils import timezone as _tz_end

    now = _tz_end.now()
    exam.end_time = now
    exam.status = Exam.Status.FINISHED
    exam.save(update_fields=["end_time", "status", "updated_at"])

    attempts_qs = StudentExam.objects.filter(exam=exam, status=StudentExam.Status.IN_PROGRESS)
    for attempt in attempts_qs:
        attempt.status = StudentExam.Status.FINISHED
        attempt.finished_at = now
        attempt.last_activity_at = now
        attempt.score = (
            StudentAnswer.objects.filter(attempt=attempt).aggregate(total=Sum("mark_obtained"))["total"]
            or 0
        )
        attempt.save(update_fields=["status", "finished_at", "score", "last_activity_at"])

    exam.submitted_count = StudentExam.objects.filter(
        exam=exam, status=StudentExam.Status.FINISHED
    ).count()
    exam.save(update_fields=["submitted_count"])

    ExamNotification.objects.create(
        exam=exam,
        sender=user,
        recipient=None,
        message="تم إنهاء الاختبار من قبل المدرس.",
    )

    messages.success(request, "تم إنهاء الاختبار بنجاح.", extra_tags="user:teacher")
    return HttpResponseRedirect(reverse("teacher_exam_monitor", args=[exam.id]))


@login_required
@user_passes_test(is_teacher)
def teacher_exam_notify(request, exam_id):
    if request.method != "POST":
        return HttpResponseRedirect(reverse("teacher_exam_monitor", args=[exam_id]))

    user = request.user
    exam = get_object_or_404(Exam, id=exam_id, teacher=user)

    message_text = request.POST.get("message", "").strip()
    recipient_id = request.POST.get("recipient_id", "").strip()

    if not message_text:
        messages.error(request, "يرجى كتابة نص التنبيه.", extra_tags="user:teacher")
        return HttpResponseRedirect(reverse("teacher_exam_monitor", args=[exam.id]))

    recipients_qs = User.objects.none()
    if recipient_id:
        if recipient_id.isdigit():
            recipients_qs = User.objects.filter(id=int(recipient_id), role="student")
            if exam.allowed_students.exists():
                recipients_qs = recipients_qs.filter(allowed_exams=exam)
    else:
        recipients_qs = exam.allowed_students.all() if exam.allowed_students.exists() else User.objects.none()

    if recipients_qs.exists():
        for s in recipients_qs:
            ExamNotification.objects.create(
                exam=exam,
                sender=user,
                recipient=s,
                message=message_text,
            )
    else:
        ExamNotification.objects.create(
            exam=exam,
            sender=user,
            recipient=None,
            message=message_text,
        )

    messages.success(request, "تم إرسال التنبيه.")
    return redirect("teacher_exam_monitor", exam_id=exam.id)


@login_required
@user_passes_test(is_teacher)
def teacher_exam_student_action(request, exam_id, student_id):
    if request.method != "POST":
        return HttpResponseRedirect(reverse("teacher_exam_monitor", args=[exam_id]))

    user = request.user
    exam = get_object_or_404(Exam, id=exam_id, teacher=user)
    student = get_object_or_404(User, id=student_id, role="student")

    action = request.POST.get("action", "").strip()
    from django.utils import timezone as _tz_act

    now = _tz_act.now()
    attempt = StudentExam.objects.filter(exam=exam, student=student).first()

    if action == "force_submit":
        if attempt and attempt.status == StudentExam.Status.IN_PROGRESS:
            attempt.status = StudentExam.Status.FINISHED
            attempt.finished_at = now
            attempt.last_activity_at = now
            attempt.score = (
                StudentAnswer.objects.filter(attempt=attempt).aggregate(total=Sum("mark_obtained"))["total"]
                or 0
            )
            attempt.save(update_fields=["status", "finished_at", "score", "last_activity_at"])
            exam.submitted_count = StudentExam.objects.filter(
                exam=exam, status=StudentExam.Status.FINISHED
            ).count()
            exam.save(update_fields=["submitted_count"])
            ExamNotification.objects.create(
                exam=exam,
                sender=user,
                recipient=student,
                message="تم إنهاء اختبارك من قبل المدرس. تم حفظ إجاباتك الحالية.",
            )
            messages.success(request, "تم إنهاء محاولة الطالب وحفظ النتيجة الحالية.", extra_tags="user:teacher")
        else:
            messages.error(request, "لا توجد محاولة نشطة لهذا الطالب.", extra_tags="user:teacher")
    elif action == "fail_cheating":
        if attempt and attempt.status == StudentExam.Status.IN_PROGRESS:
            attempt.status = StudentExam.Status.FAILED_CHEATING
            attempt.finished_at = now
            attempt.last_activity_at = now
            attempt.save(update_fields=["status", "finished_at", "last_activity_at"])
            ExamNotification.objects.create(
                exam=exam,
                sender=user,
                recipient=student,
                message="تم ترسيبك في الاختبار بسبب رصد مخالفة (غش).",
            )
            messages.success(request, "تم ترسيب الطالب بسبب الغش.", extra_tags="user:teacher")
        else:
            messages.error(request, "لا توجد محاولة نشطة لهذا الطالب.", extra_tags="user:teacher")
    else:
        messages.error(request, "إجراء غير صالح.", extra_tags="user:teacher")

    return HttpResponseRedirect(reverse("teacher_exam_monitor", args=[exam.id]))


def _get_mock_exam_students(exam):
    raw_students = [
        {"name": "خالد عمر", "score": 95, "time_spent_minutes": 42, "status": "pass"},
        {"name": "سارة أحمد", "score": 88, "time_spent_minutes": 50, "status": "pass"},
        {"name": "منى علي", "score": 73, "time_spent_minutes": 60, "status": "pass"},
        {"name": "عمر سالم", "score": 48, "time_spent_minutes": 55, "status": "fail"},
        {"name": "سامي كمال", "score": None, "time_spent_minutes": None, "status": "pending"},
        {"name": "نور محمود", "score": 91, "time_spent_minutes": 38, "status": "pass"},
        {"name": "ليلى حسن", "score": 62, "time_spent_minutes": 70, "status": "pass"},
        {"name": "أحمد خالد", "score": 35, "time_spent_minutes": 80, "status": "fail"},
    ]

    total_mark = exam.total_mark or 100

    avatar_styles = [
        ("bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"),
        ("bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"),
        ("bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"),
        ("bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300"),
        ("bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300"),
    ]

    students = []
    for index, s in enumerate(raw_students, start=1):
        name = s["name"]
        parts = [p for p in name.split() if p]
        initials = "".join(p[0] for p in parts[:2]) if parts else ""
        score = s.get("score")
        if score is not None and total_mark > 0:
            score_percent = round((score / float(total_mark)) * 100)
        else:
            score_percent = 0
        if score_percent >= 90:
            score_bar_class = "bg-emerald-500"
        elif score_percent >= 50:
            score_bar_class = "bg-blue-500"
        else:
            score_bar_class = "bg-red-500"
        style = avatar_styles[index % len(avatar_styles)]
        style_parts = style.split()
        avatar_bg = " ".join(style_parts[:-2])
        avatar_text = " ".join(style_parts[-2:])
        time_minutes = s.get("time_spent_minutes")
        if time_minutes is None:
            time_spent_display = "--:--"
        else:
            hours = time_minutes // 60
            minutes = time_minutes % 60
            if hours:
                time_spent_display = f"{hours}س {minutes:02d}د"
            else:
                time_spent_display = f"{minutes} دقيقة"
        status = s.get("status") or "pending"
        code = f"20230{50 + index}"
        students.append(
            {
                "id": index,
                "name": name,
                "code": code,
                "initials": initials,
                "score": score,
                "score_percent": score_percent,
                "score_bar_class": score_bar_class,
                "avatar_bg": avatar_bg,
                "avatar_text": avatar_text,
                "time_spent_display": time_spent_display,
                "status": status,
                "smart_marking_enabled": True,
            }
        )
    return students


@login_required
@user_passes_test(is_teacher)
def teacher_exam_results(request, exam_id):
    from django.utils import timezone
    from datetime import timedelta
    
    user = request.user
    exam = get_object_or_404(Exam, id=exam_id, teacher=user)
    
    # Handle pass_mark update
    if request.method == "POST" and request.POST.get("action") == "update_pass_mark":
        try:
            pass_mark = int(request.POST.get("pass_mark", 50))
            if 0 <= pass_mark <= 100:
                exam.pass_mark = pass_mark
                exam.save(update_fields=["pass_mark"])
                messages.success(request, f"تم تحديث علامة حد النجاح إلى {pass_mark}%")
            else:
                messages.error(request, "يجب أن تكون علامة حد النجاح بين 0 و 100")
        except ValueError:
            messages.error(request, "قيمة غير صحيحة لعلامة حد النجاح")
        return redirect("teacher_exam_results", exam_id=exam.id)

    # Calculate actual total mark from exam questions
    total_mark_sum = (
        ExamQuestion.objects.filter(exam=exam).aggregate(total=Sum("mark"))["total"]
        or 0
    )
    
    # Check if exam time has expired
    now = timezone.now()
    exam_end_time = exam.end_time or (exam.start_time + timedelta(minutes=exam.duration_minutes) if exam.start_time and exam.duration_minutes else None)
    exam_has_expired = exam_end_time and now > exam_end_time

    # Get all allowed students for this exam
    allowed_students = exam.allowed_students.all().select_related()
    
    # Get all attempts for this exam
    attempts_dict = {}
    attempts_qs = StudentExam.objects.filter(exam=exam).select_related("student")
    for attempt in attempts_qs:
        attempts_dict[attempt.student_id] = attempt

    avatar_styles = [
        "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
        "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
        "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
        "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
        "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
    ]

    students = []
    highest_score = 0  # Track highest score
    
    for index, student in enumerate(allowed_students, start=1):
        name = student.full_name or student.username
        parts = [p for p in (name or "").split() if p]
        initials = "".join(p[0] for p in parts[:2]) if parts else (name[:2] if name else "")

        attempt = attempts_dict.get(student.id)
        
        if attempt and attempt.status != StudentExam.Status.IN_PROGRESS:
            score = float(attempt.score or 0)
            if score > highest_score:
                highest_score = score
            if total_mark_sum > 0:
                score_percent = round((score / float(total_mark_sum)) * 100)
            else:
                score_percent = 0
        else:
            score = None
            score_percent = 0

        if score_percent >= 90:
            score_bar_class = "bg-emerald-500"
        elif score_percent >= 50:
            score_bar_class = "bg-blue-500"
        else:
            score_bar_class = "bg-red-500"

        style = avatar_styles[(index - 1) % len(avatar_styles)]
        style_parts = style.split()
        avatar_bg = " ".join(style_parts[:-2])
        avatar_text = " ".join(style_parts[-2:])

        if attempt and attempt.started_at and attempt.finished_at:
            delta = attempt.finished_at - attempt.started_at
            minutes = max(int(delta.total_seconds() // 60), 0)
            hours = minutes // 60
            minutes = minutes % 60
            if hours:
                time_spent_display = f"{hours}س {minutes:02d}د"
            else:
                time_spent_display = f"{minutes} دقيقة"
        else:
            time_spent_display = "--:--"

        # Determine student status
        pass_mark = exam.pass_mark if hasattr(exam, 'pass_mark') and exam.pass_mark else 50
        if not attempt:
            # If exam has expired and student didn't start, mark as failed
            if exam_has_expired:
                status = "absent_fail"
            else:
                status = "not_started"
        elif attempt.status == StudentExam.Status.IN_PROGRESS:
            status = "pending"
        else:
            status = "pass" if score_percent >= pass_mark else "fail"
        
        # Get cheating count
        cheating_count = 0
        if attempt:
            cheating_count = ExamEvent.objects.filter(
                exam=exam,
                student=student,
                event_type__in=[
                    ExamEvent.EventType.CHEATING_VISIBILITY,
                    ExamEvent.EventType.CHEATING_CLIPBOARD,
                ]
            ).count()

        students.append(
            {
                "id": student.id,
                "name": name,
                "code": student.username,
                "initials": initials,
                "cheating_count": cheating_count,
                "score": score,
                "score_percent": score_percent,
                "score_bar_class": score_bar_class,
                "avatar_bg": avatar_bg,
                "avatar_text": avatar_text,
                "time_spent_display": time_spent_display,
                "status": status,
                "smart_marking_enabled": True,
            }
        )

    query = request.GET.get("q", "").strip()
    selected_grade = request.GET.get("grade", "").strip()

    filtered_students = []
    for s in students:
        if query and query not in s["name"]:
            continue
        if selected_grade:
            percent = s["score_percent"]
            if s["score"] is None:
                continue
            if selected_grade == "high" and not (percent > 90):
                continue
            if selected_grade == "average" and not (50 <= percent <= 90):
                continue
            if selected_grade == "low" and not (percent < 50):
                continue
        filtered_students.append(s)

    page_size = 6
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1

    total_items = len(filtered_students)
    total_pages = (total_items + page_size - 1) // page_size if total_items else 1
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    end = start + page_size
    students_page = filtered_students[start:end]

    if total_items:
        start_index = start + 1
        end_index = min(end, total_items)
    else:
        start_index = 0
        end_index = 0

    pagination = {
        "page": page,
        "total_pages": total_pages,
        "previous_page": page - 1 if page > 1 else 1,
        "next_page": page + 1 if page < total_pages else total_pages,
        "pages": list(range(1, total_pages + 1)),
        "start_index": start_index,
        "end_index": end_index,
        "total_items": total_items,
    }

    # Include both students with scores and absent students in calculations
    graded_students = [s for s in students if s["score"] is not None]
    absent_students = [s for s in students if s["status"] == "absent_fail"]
    
    # For statistics, count absent students as failed
    total_evaluated = len(graded_students) + len(absent_students)
    
    if total_evaluated > 0:
        if graded_students:
            average_score_percent = round(
                sum(s["score_percent"] for s in graded_students) / len(graded_students)
            )
        else:
            average_score_percent = 0
        
        pass_count = sum(1 for s in graded_students if s["status"] == "pass")
        # Absent students count as failed
        pass_rate = round((pass_count / total_evaluated) * 100)
    else:
        average_score_percent = 0
        pass_rate = 0

    students_total = total_evaluated
    
    # students_registered is the total number of allowed students
    students_registered = len(students)

    summary = {
        "average_score_percent": average_score_percent,
        "pass_rate": pass_rate,
        "students_total": students_total,
        "students_registered": students_registered,
    }

    buckets_def = [
        {"label": "0-50", "min": 0, "max": 50, "bg_class": "bg-red-500"},
        {"label": "50-75", "min": 50, "max": 75, "bg_class": "bg-amber-500"},
        {"label": "75-90", "min": 75, "max": 90, "bg_class": "bg-blue-500"},
        {"label": ">90", "min": 90, "max": 101, "bg_class": "bg-emerald-500"},
    ]

    grade_distribution = []
    total_graded = len(graded_students)
    for bucket in buckets_def:
        if total_graded:
            count = sum(
                1
                for s in graded_students
                if bucket["min"] <= s["score_percent"] < bucket["max"]
            )
            percent = round((count / total_graded) * 100) if count else 0
        else:
            percent = 0
        height = percent if percent > 0 else 8
        grade_distribution.append(
            {
                "label": bucket["label"],
                "percent": percent,
                "height": height,
                "bg_class": bucket["bg_class"],
            }
        )

    top_wrong_questions = []
    exam_questions = list(
        ExamQuestion.objects.filter(exam=exam).select_related("question")
    )
    # Total attempts that are finished
    finished_attempts_count = StudentExam.objects.filter(
        exam=exam, status=StudentExam.Status.FINISHED
    ).count()

    for eq in exam_questions:
        if finished_attempts_count == 0:
            continue
            
        # Correct answers for this question in finished attempts
        correct_answers_count = StudentAnswer.objects.filter(
            attempt__exam=exam, 
            attempt__status=StudentExam.Status.FINISHED,
            exam_question=eq, 
            is_correct=True
        ).count()
        
        # Wrong answers = Total finished attempts - Correct answers
        wrong_answers = finished_attempts_count - correct_answers_count
        
        if wrong_answers == 0:
            continue
            
        wrong_percent = round((wrong_answers / finished_attempts_count) * 100)
        text = eq.question.text[:100]
        top_wrong_questions.append(
            {
                "index": eq.order or len(top_wrong_questions) + 1,
                "text": text,
                "wrong_percent": wrong_percent,
            }
        )
    top_wrong_questions.sort(key=lambda x: x["wrong_percent"], reverse=True)
    top_wrong_questions = top_wrong_questions[:3]
    
    # Check if exam has essay questions
    has_essay_questions = ExamQuestion.objects.filter(
        exam=exam,
        question__question_type=Question.QuestionType.ESSAY
    ).exists()

    context = {
        "exam": exam,
        "total_mark": total_mark_sum,  # Total mark for the exam (sum of all questions)
        "highest_score": highest_score,  # Highest score achieved by any student
        "summary": summary,
        "grade_distribution": grade_distribution,
        "top_wrong_questions": top_wrong_questions,
        "students_page": students_page,
        "pagination": pagination,
        "query": query,
        "selected_grade": selected_grade,
        "has_essay_questions": has_essay_questions,
    }
    return render(request, "core/teacher_exam_results.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_exam_student_correction(request, exam_id, student_id):
    """
    التصحيح اليدوي لإجابات الطالب:
    - عرض الإجابات المقالية التي تتطلب تقييماً بشرياً.
    - رصد الدرجات لكل سؤال وتحديث مجموع درجات الطالب.
    - مراجعة إحصائيات المحاولة والوقت المستغرق.
    """
    user = request.user
    try:
        exam = get_object_or_404(Exam, id=exam_id, teacher=user)

        attempt = (
            StudentExam.objects.filter(exam=exam, student_id=student_id)
            .select_related("student")
            .first()
        )
        if not attempt:
            raise Http404("Student exam attempt not found")

        student_obj = attempt.student

        exam_questions = list(
            ExamQuestion.objects.filter(exam=exam)
            .select_related("question")
            .prefetch_related("question__choices")
        )

        answers_qs = StudentAnswer.objects.filter(attempt=attempt).select_related(
            "exam_question", "selected_choice"
        )
        answers_by_eq = {a.exam_question_id: a for a in answers_qs}

        if request.method == "POST":
            from django.db import transaction
            
            logger.info(f"=== START: Processing correction for exam {exam_id}, student {student_id} ===")
            logger.info(f"POST data keys: {list(request.POST.keys())}")
            saved_count = 0
            
            with transaction.atomic():
                for eq in exam_questions:
                    field_name = f"mark_{eq.id}"
                    mark_raw = request.POST.get(field_name, "").strip()
                    
                    # If field is empty, skip (but allow 0)
                    if mark_raw == "":
                        continue
                    
                    try:
                        mark_val = float(mark_raw)
                    except ValueError:
                        logger.warning(f"Invalid mark value '{mark_raw}' for question {eq.id}")
                        continue
                    
                    try:
                        max_mark = float(eq.mark)
                    except (TypeError, ValueError):
                        max_mark = None
                    
                    # Validate mark is within range
                    if max_mark is not None:
                        if mark_val < 0:
                            mark_val = 0
                        if mark_val > max_mark:
                            mark_val = max_mark
                    
                    # Get or create answer object
                    answer_obj, created = StudentAnswer.objects.get_or_create(
                        attempt=attempt,
                        exam_question=eq,
                    )
                    
                    # Update mark
                    answer_obj.mark_obtained = mark_val
                    
                    # Determine if correct
                    if eq.question.question_type == Question.QuestionType.MCQ:
                        answer_obj.is_correct = (mark_val >= float(eq.mark))
                    else:
                        answer_obj.is_correct = (mark_val > 0)
                    
                    # Save the answer
                    answer_obj.save()
                    saved_count += 1
                    logger.info(f"✓ Saved mark {mark_val}/{max_mark} for Q{eq.id} (answer_obj.id={answer_obj.id})")
                
                # Recalculate total score
                total_score = (
                    StudentAnswer.objects.filter(attempt=attempt).aggregate(
                        total=Sum("mark_obtained")
                    )["total"]
                    or 0
                )
                
                # Save total score to attempt
                old_score = attempt.score
                attempt.score = total_score
                attempt.save(update_fields=["score"])
                
                logger.info(f"=== COMPLETE: Saved {saved_count} marks, total score: {old_score} → {total_score} ===")

            # Get all students for navigation to next student
            all_students_list = list(exam.allowed_students.all().order_by('id'))
            current_student_index = -1
            
            for idx, s in enumerate(all_students_list):
                if s.id == int(student_id):
                    current_student_index = idx
                    break
            
            # If there's a next student, redirect to them, otherwise go to results
            if current_student_index >= 0 and current_student_index < len(all_students_list) - 1:
                next_student_id = all_students_list[current_student_index + 1].id
                messages.success(request, "تم حفظ التصحيح بنجاح. الانتقال للطالب التالي...")
                return redirect("teacher_exam_student_correction", exam_id=exam.id, student_id=next_student_id)
            else:
                messages.success(request, "تم حفظ التصحيح بنجاح. تم الانتهاء من تصحيح جميع الطلاب.")
                return redirect("teacher_exam_results", exam_id=exam.id)

    except Exception as e:
        logger.error(f"Error in teacher_exam_student_correction: {str(e)}", exc_info=True)
        messages.error(request, "حدث خطأ أثناء معالجة التصحيح.")
        return redirect("teacher_exam_results", exam_id=exam_id)

    exam_total_mark = (
        ExamQuestion.objects.filter(exam=exam).aggregate(total=Sum("mark"))["total"]
        or 0
    )
    current_total = (
        StudentAnswer.objects.filter(attempt=attempt).aggregate(
            total=Sum("mark_obtained")
        )["total"]
        or 0
    )

    correct_count = answers_qs.filter(is_correct=True).count()
    wrong_count = answers_qs.filter(is_correct=False).count()
    total_questions = len(exam_questions)
    pending_count = max(total_questions - correct_count - wrong_count, 0)
    completion_base = correct_count + wrong_count
    completion_percent = 0
    if total_questions:
        completion_percent = int((completion_base / total_questions) * 100)

    if attempt.started_at and attempt.finished_at:
        delta = attempt.finished_at - attempt.started_at
        minutes = max(int(delta.total_seconds() // 60), 0)
        hours = minutes // 60
        minutes = minutes % 60
        if hours:
            time_spent_display = f"{hours}س {minutes:02d}د"
        else:
            time_spent_display = f"{minutes} دقيقة"
    else:
        time_spent_display = "--:--"

    name = student_obj.full_name or student_obj.username
    parts = [p for p in (name or "").split() if p]
    initials = "".join(p[0] for p in parts[:2]) if parts else (name[:2] if name else "")

    # Get all students for navigation
    all_students = list(exam.allowed_students.all().order_by('id'))
    current_student_index = next((i for i, s in enumerate(all_students) if s.id == student_obj.id), 0)
    total_students = len(all_students)
    
    previous_student_id = all_students[current_student_index - 1].id if current_student_index > 0 else None
    next_student_id = all_students[current_student_index + 1].id if current_student_index < total_students - 1 else None
    
    student = {
        "id": student_obj.id,
        "name": name,
        "code": student_obj.username,
        "email": student_obj.email,
        "initials": initials,
        "time_spent_display": time_spent_display,
        "current_index": current_student_index + 1,
        "total_students": total_students,
        "previous_student_id": previous_student_id,
        "next_student_id": next_student_id,
    }

    questions = []
    for index, eq in enumerate(exam_questions, start=1):
        q = eq.question
        answer = answers_by_eq.get(eq.id)
        is_mcq = q.question_type == Question.QuestionType.MCQ
        questions.append(
            {
                "index": index,
                "exam_question": eq,
                "question": q,
                "answer": answer,
                "is_mcq": is_mcq,
            }
        )

    sidebar = {
        "current_total": current_total,
        "max_total": exam_total_mark,
        "completion_percent": completion_percent,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "pending_count": pending_count,
    }

    context = {
        "exam": exam,
        "student": student,
        "sidebar": sidebar,
        "questions": questions,
    }
    return render(request, "core/teacher_exam_student_correction.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_subjects(request):
    user = request.user

    from django.db.models import Prefetch

    subjects = (
        Subject.objects.filter(teacher=user)
        .annotate(
            exams_count=Count("exams", distinct=True),
            students_count=Count("students", distinct=True),
            questions_count=Count("questions", distinct=True),
        )
        .prefetch_related(
            Prefetch(
                "exams",
                queryset=Exam.objects.annotate(
                    questions_count=Count("exam_questions", distinct=True)
                ),
            )
        )
    )

    query = request.GET.get("q", "").strip()
    selected_grade = request.GET.get("grade", "").strip()
    selected_status = request.GET.get("status", "").strip()

    if query:
        subjects = subjects.filter(name__icontains=query)

    context = {
        "subjects": subjects,
        "query": query,
        "selected_grade": selected_grade,
        "selected_status": selected_status,
    }
    return render(request, "core/teacher_subjects.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_subject_question_bank(request, subject_id):
    """
    إدارة بنك الأسئلة للمادة:
    - إضافة أسئلة يدوياً أو عبر ملفات (PDF/Word/Text).
    - توليد أسئلة تلقائياً باستخدام الذكاء الاصطناعي بناءً على محتوى مرفوع.
    - تنظيم الأسئلة حسب النوع والصعوبة.
    """
    logger = logging.getLogger(__name__)
    user = request.user
    subject = get_object_or_404(Subject, id=subject_id, teacher=user)
    questions = Question.objects.filter(subject=subject, teacher=user)

    query = request.GET.get("q", "").strip()
    selected_type = request.GET.get("question_type", "").strip()
    selected_difficulty = request.GET.get("difficulty", "").strip()

    if query:
        questions = questions.filter(text__icontains=query)

    valid_types = {choice[0] for choice in Question.QuestionType.choices}
    if selected_type in valid_types:
        questions = questions.filter(question_type=selected_type)

    valid_difficulties = {choice[0] for choice in Question.Difficulty.choices}
    if selected_difficulty in valid_difficulties:
        questions = questions.filter(difficulty=selected_difficulty)

    questions = questions.order_by("-created_at")

    errors = {}
    ai_errors = {}
    form_data = {
        "text": "",
        "question_type": "mcq",
        "mark": "1",
        "difficulty": Question.Difficulty.MEDIUM,
    }

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "delete":
            question_id = request.POST.get("question_id")
            try:
                question = Question.objects.get(
                    id=question_id, subject=subject, teacher=user
                )
                question.delete()
                messages.success(request, "تم حذف السؤال بنجاح.", extra_tags="user:teacher")
            except Question.DoesNotExist:
                messages.error(request, "السؤال غير موجود أو غير تابع لك.", extra_tags="user:teacher")
            except Exception as e:
                logger.error(f"Error deleting question {question_id}: {str(e)}")
                messages.error(request, f"فشل حذف السؤال: {str(e)}", extra_tags="user:teacher")
            return redirect("teacher_subject_question_bank", subject_id=subject.id)

        if action == "ai_generate":
            ai_num_raw = request.POST.get("ai_num_questions", "").strip()
            # Force MCQ only for AI generation (essay questions removed due to timeout issues)
            ai_question_type = "mcq"
            ai_difficulty = request.POST.get("ai_difficulty", "varied").strip()
            ai_text_source = request.POST.get("ai_text_source", "").strip()
            ai_file = request.FILES.get("ai_file")
            ai_num_choices_raw = request.POST.get("ai_num_choices", "").strip()

            num_questions = 0
            if ai_num_raw:
                try:
                    num_questions = int(ai_num_raw)
                    if num_questions <= 0 or num_questions > 50:
                        raise ValueError
                except ValueError:
                    ai_errors["num"] = "يرجى إدخال عدد أسئلة صحيح بين 1 و 50."
            else:
                ai_errors["num"] = "يرجى تحديد عدد الأسئلة المطلوب توليدها."

            base_text = ai_text_source
            if ai_file and not base_text:
                try:
                    base_text = _extract_text_from_file(ai_file)
                except ValueError as e:
                    ai_errors["file"] = str(e)

            if not base_text:
                ai_errors["text"] = "يرجى إدخال نص للمادة أو رفع ملف مدعوم."

            num_choices = 4
            if ai_num_choices_raw:
                try:
                    num_choices = int(ai_num_choices_raw)
                    if num_choices < 2 or num_choices > 10:
                        raise ValueError
                except ValueError:
                    ai_errors["num_choices"] = "يرجى إدخال عدد اختيارات صحيح بين 2 و 10."

            if not ai_errors:
                try:
                    logger.info(f"Starting AI question generation: num_questions={num_questions}, type={ai_question_type}, difficulty={ai_difficulty}")
                    generated_questions = _generate_questions_with_ollama(
                        base_text=base_text,
                        num_questions=num_questions,
                        question_type=ai_question_type,
                        difficulty=ai_difficulty,
                        num_choices=num_choices,
                    )
                    logger.info(f"Generated {len(generated_questions) if generated_questions else 0} questions from AI")
                    
                    if not generated_questions or len(generated_questions) == 0:
                        ai_errors["response"] = "لم يتم توليد أي أسئلة من الذكاء الاصطناعي. يرجى التحقق من النص المدخل أو إعدادات Ollama."
                    else:
                        created_count, error_details = _save_generated_questions(
                            subject=subject,
                            teacher=user,
                            generated_questions=generated_questions,
                            num_choices=num_choices,
                        )
                        logger.info(f"Save result: {created_count} questions saved, {len(error_details)} errors")
                        
                        if created_count > 0:
                            success_msg = f"تم توليد وإضافة {created_count} سؤالاً إلى بنك الأسئلة."
                            if error_details:
                                success_msg += f" (تم تخطي {len(error_details)} سؤالاً بسبب مشاكل في البيانات)"
                            messages.success(request, success_msg, extra_tags="user:teacher")
                        else:
                            error_msg = "لم يتم حفظ أي أسئلة. "
                            if error_details:
                                error_msg += "الأسباب: " + "، ".join(error_details[:3])  # عرض أول 3 أخطاء
                                if len(error_details) > 3:
                                    error_msg += f" و{len(error_details) - 3} أخطاء أخرى."
                            else:
                                error_msg += "قد تكون البيانات المُولدة غير صالحة. يرجى تجربة نص أو إعدادات مختلفة."
                            messages.warning(request, error_msg, extra_tags="user:teacher")
                except TimeoutError as e:
                    logger.error(f"Timeout generating questions: {str(e)}")
                    error_msg = str(e) if str(e) else "انتهت مهلة الانتظار (120 ثانية). حاول تقليل عدد الأسئلة أو طول النص."
                    ai_errors["timeout"] = error_msg + " تأكد من أن Ollama يعمل بشكل صحيح وأن النموذج المختار سريع بما فيه الكفاية."
                except urllib.error.URLError as e:
                    logger.error(f"URL error generating questions: {str(e)}")
                    ai_errors["connection"] = "تعذر الاتصال بـ Ollama. يرجى التأكد من تشغيله على المنفذ 11434."
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                    logger.error(f"JSON error generating questions: {str(e)}")
                    ai_errors["response"] = f"تعذر فهم استجابة الذكاء الاصطناعي: {str(e)}. يرجى المحاولة لاحقاً."
                except Exception as e:
                    logger.error(f"Unexpected error generating questions: {str(e)}", exc_info=True)
                    ai_errors["general"] = f"حدث خطأ غير متوقع: {str(e)}"

            if not ai_errors:
                return redirect("teacher_subject_question_bank", subject_id=subject.id)

            return render(
                request,
                "core/teacher_subject_question_bank.html",
                {
                    "subject": subject,
                    "questions": questions,
                    "errors": errors,
                    "form_data": form_data,
                    "query": query,
                    "selected_type": selected_type,
                    "selected_difficulty": selected_difficulty,
                    "ai_errors": ai_errors,
                },
            )

        text = request.POST.get("text", "").strip()
        question_type = request.POST.get("question_type", "mcq")
        mark_raw = request.POST.get("mark", "").strip()
        difficulty = request.POST.get("difficulty", Question.Difficulty.MEDIUM)
        model_answer = request.POST.get("model_answer", "").strip()

        form_data["text"] = text
        form_data["question_type"] = question_type
        form_data["mark"] = mark_raw or "1"
        form_data["difficulty"] = difficulty
        form_data["model_answer"] = model_answer

        if not text:
            errors["text"] = "يرجى إدخال نص السؤال."

        mark = 1
        if mark_raw:
            try:
                mark = float(mark_raw)
                if mark <= 0:
                    raise ValueError
            except ValueError:
                errors["mark"] = "يرجى إدخال درجة صحيحة أكبر من صفر."

        valid_difficulties = {choice[0] for choice in Question.Difficulty.choices}
        if difficulty not in valid_difficulties:
            errors["difficulty"] = "يرجى اختيار مستوى صعوبة صحيح."

        choices_data = []
        correct_index = None
        if question_type == Question.QuestionType.MCQ:
            correct_raw = request.POST.get("correct_choice", "").strip()
            for key, value in request.POST.items():
                if not key.startswith("choices["):
                    continue
                if not key.endswith("][text]"):
                    continue
                try:
                    index_str = key.split("[", 1)[1].split("]", 1)[0]
                    index = int(index_str)
                except (IndexError, ValueError):
                    continue
                text_value = value.strip()
                if text_value:
                    choices_data.append((index, text_value))

            choices_data.sort(key=lambda x: x[0])

            if len(choices_data) < 2:
                errors["choices"] = "يرجى إدخال خيارين على الأقل."

            if correct_raw:
                try:
                    correct_index = int(correct_raw)
                except ValueError:
                    correct_index = None

            valid_choice_indices = {idx for idx, _ in choices_data}
            if correct_index is None or correct_index not in valid_choice_indices:
                errors["choices"] = "يرجى اختيار إجابة صحيحة واحدة من بين الخيارات."

        if not errors:
            question = Question.objects.create(
                subject=subject,
                teacher=user,
                text=text,
                question_type=question_type,
                mark=mark,
                difficulty=difficulty,
                model_answer=model_answer,
            )
            if question_type == Question.QuestionType.MCQ:
                order = 1
                for idx, choice_text in choices_data:
                    QuestionChoice.objects.create(
                        question=question,
                        text=choice_text,
                        is_correct=(idx == correct_index),
                        order=order,
                    )
                    order += 1
            messages.success(request, "تم إضافة السؤال إلى بنك الأسئلة.", extra_tags="user:teacher")
            return redirect("teacher_subject_question_bank", subject_id=subject.id)

    context = {
        "subject": subject,
        "questions": questions,
        "errors": errors,
        "form_data": form_data,
        "query": query,
        "selected_type": selected_type,
        "selected_difficulty": selected_difficulty,
        "ai_errors": ai_errors,
    }
    return render(request, "core/teacher_subject_question_bank.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_subject_students(request, subject_id):
    user = request.user
    subject = get_object_or_404(Subject, id=subject_id, teacher=user)

    direct_ids = subject.students.filter(
        is_active=True,
        role="student",
    ).values_list("id", flat=True)

    group_ids = User.objects.filter(
        role="student",
        is_active=True,
        student_groups__subject=subject,
        student_groups__teacher=user,
    ).values_list("id", flat=True)

    all_ids = set(direct_ids) | set(group_ids)

    all_students = User.objects.filter(
        id__in=all_ids,
        is_active=True,
        role="student",
    )

    query = request.GET.get("q", "").strip()
    if query:
        all_students = all_students.filter(
            Q(full_name__icontains=query) | Q(username__icontains=query) | Q(email__icontains=query)
        )

    all_students = all_students.order_by("full_name", "username")

    context = {
        "subject": subject,
        "students": all_students,
        "query": query,
    }
    return render(request, "core/teacher_subject_students.html", context)


def _extract_text_from_file(uploaded_file):
    name = (uploaded_file.name or "").lower()
    if name.endswith(".txt"):
        try:
            return uploaded_file.read().decode("utf-8", errors="ignore")
        except Exception:
            raise ValueError("تعذر قراءة ملف النص. يرجى التأكد من سلامة الملف.")
    if name.endswith(".pdf"):
        if not PyPDF2:
            raise ValueError("قراءة ملفات PDF تتطلب تثبيت مكتبة PyPDF2 على الخادم.")
        try:
            reader = PyPDF2.PdfReader(uploaded_file)
            text_chunks = []
            for page in reader.pages:
                text_chunks.append(page.extract_text() or "")
            text = "\n".join(text_chunks).strip()
            if not text:
                raise ValueError("لم يتم العثور على نص قابل للاستخراج من ملف PDF.")
            return text
        except Exception:
            raise ValueError("تعذر استخراج النص من ملف PDF. يرجى تجربة ملف آخر.")
    if name.endswith(".docx") or name.endswith(".doc"):
        if not docx:
            raise ValueError("قراءة ملفات Word تتطلب تثبيت مكتبة python-docx على الخادم.")
        try:
            document = docx.Document(uploaded_file)
            paragraphs = [p.text for p in document.paragraphs if p.text]
            text = "\n".join(paragraphs).strip()
            if not text:
                raise ValueError("لم يتم العثور على نص قابل للاستخراج من ملف Word.")
            return text
        except Exception:
            raise ValueError("تعذر استخراج النص من ملف Word. يرجى تجربة ملف آخر.")
    raise ValueError("نوع الملف غير مدعوم. يرجى استخدام ملفات TXT أو PDF أو Word.")


def _normalize_question_item(item):
    """تحويل item إلى dictionary صالح"""
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        try:
            parsed = json.loads(item)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _extract_questions_from_response(response_data):
    """استخراج قائمة الأسئلة من استجابة Ollama"""
    logger = logging.getLogger(__name__)
    
    # إذا كان dict مع "questions" key
    if isinstance(response_data, dict):
        questions = response_data.get("questions")
        if isinstance(questions, list):
            logger.info(f"Found {len(questions)} questions in 'questions' key")
            return questions
        # fallback: سؤال واحد في root
        if response_data.get("text") or response_data.get("question"):
            logger.info("Found single question in root dict")
            return [response_data]
        logger.warning("Dict has no 'questions' key and no question fields")
        return []
    
    # إذا كان list مباشر
    if isinstance(response_data, list):
        logger.info(f"Found {len(response_data)} questions in list format")
        return response_data
    
    logger.warning(f"Unexpected format: {type(response_data)}")
    return []


def _clean_questions_list(questions_list):
    """تنظيف قائمة الأسئلة من العناصر غير الصالحة"""
    logger = logging.getLogger(__name__)
    cleaned = []
    
    for q in questions_list:
        normalized = _normalize_question_item(q)
        if normalized:
            cleaned.append(normalized)
        else:
            logger.warning(f"Skipping invalid question: {type(q).__name__}")
    
    return cleaned


def _parse_ollama_response(body):
    """Parse استجابة Ollama وتحويلها إلى قائمة أسئلة"""
    logger = logging.getLogger(__name__)
    
    try:
        parsed = json.loads(body)
        raw_response = parsed.get("response", "")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Ollama response: {str(e)}")
        raise ValueError("تعذر فهم استجابة Ollama. تأكد من أن النموذج يعمل بشكل صحيح.")
    
    # إذا كان response كائن JSON جاهز
    if isinstance(raw_response, (dict, list)):
        questions_list = _extract_questions_from_response(raw_response)
        return _clean_questions_list(questions_list)
    
    # إذا كان response نص JSON
    if isinstance(raw_response, str):
        try:
            parsed_response = json.loads(raw_response)
            questions_list = _extract_questions_from_response(parsed_response)
            return _clean_questions_list(questions_list)
        except json.JSONDecodeError:
            # محاولة استخراج JSON من النص
            start = raw_response.find("{")
            end = raw_response.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = raw_response[start : end + 1]
                try:
                    parsed_response = json.loads(candidate)
                    questions_list = _extract_questions_from_response(parsed_response)
                    return _clean_questions_list(questions_list)
                except json.JSONDecodeError:
                    logger.error("Failed to extract JSON from response text")
                    raise ValueError("تعذر استخراج JSON من استجابة Ollama.")
            else:
                raise ValueError("لم يتم العثور على JSON صالح في استجابة Ollama.")
    
    return []


def _build_ollama_prompt(base_text, num_questions, question_type, difficulty, num_choices):
    """بناء prompt لـ Ollama"""
    difficulty_map = {
        "easy": "سهل",
        "medium": "متوسط",
        "hard": "صعب",
        "varied": "متنوع",
        "mixed": "متنوع"
    }
    difficulty_label = difficulty_map.get(difficulty.lower(), "متنوع")
    
    system_prompt = (
        "You are an experienced educator and exam designer. "
        "Your task is to create natural, human-like exam questions based on the provided text. "
        "Generate ONLY valid JSON. "
        "JSON keys and enum values (type, difficulty) MUST be in English. "
        "Content (text, choices, model_answer) MUST be in Arabic. "
        "Do NOT include any text before or after the JSON. "
        "Output MUST be valid JSON in UTF-8 encoding."
    )
    
    user_prompt = (
        f"أنت مدرس محترف ومصمم اختبارات. مهمتك هي إنشاء أسئلة امتحان طبيعية وبشرية بناءً على النص المرجعي أدناه.\n\n"
        f"الخطوات المطلوبة:\n"
        f"1. اقرأ النص المرجعي بعناية وافهم محتواه بشكل كامل\n"
        f"2. حدد المفاهيم والأفكار الرئيسية في النص\n"
        f"3. قم بتوليد بالضبط {num_questions} سؤالاً من نوع اختيار من متعدد\n"
        f"4. تأكد من أن الأسئلة تغطي محتوى النص بشكل منطقي وطبيعي\n\n"
        f"متطلبات مهمة جداً:\n"
        f"1. كل سؤال يجب أن يكون طبيعياً وبشرياً، كما لو كتبه مدرس حقيقي\n"
        f"2. السؤال يجب أن يكون واضحاً ومفهوماً، ويرتبط مباشرة بمحتوى النص\n"
        f"3. كل خيار يجب أن يكون إجابة كاملة وواضحة، وليس مجرد تكملة\n"
        f"4. الخيارات الخاطئة يجب أن تكون منطقية ومقنعة، وليست واضحة أنها خاطئة\n"
        f"5. يجب أن يكون هناك بالضبط {num_choices} خيارات لكل سؤال\n"
        f"6. إجابة واحدة فقط صحيحة (is_correct: true)، والباقي خاطئة (is_correct: false)\n"
        f"7. مستوى الصعوبة: {difficulty_label}\n"
        f"8. لا تضع علامة استفهام (؟) في نهاية السؤال\n\n"
        f"أمثلة على أسئلة جيدة (طبيعية وبشرية):\n\n"
        f"مثال 1:\n"
        f'السؤال: "ما هو الهدف الرئيسي من استخدام الذكاء الاصطناعي في التعليم"\n'
        f'الخيارات:\n'
        f'  - "تحسين تجربة التعلم وتخصيص المحتوى التعليمي لكل طالب" (صحيح)\n'
        f'  - "استبدال المدرسين بالكامل بالأنظمة الآلية" (خاطئ - لكن منطقي)\n'
        f'  - "تقليل عدد الطلاب في الفصول الدراسية" (خاطئ - لكن منطقي)\n'
        f'  - "إلغاء الحاجة للكتب والمواد التعليمية" (خاطئ - لكن منطقي)\n\n'
        f"مثال 2:\n"
        f'السؤال: "أي من العبارات التالية تصف بشكل صحيح مفهوم التعلم الآلي"\n'
        f'الخيارات:\n'
        f'  - "نظام يتعلم من البيانات ويحسن أداءه مع الوقت دون برمجة صريحة" (صحيح)\n'
        f'  - "برنامج ثابت يقوم بنفس المهام دون تغيير" (خاطئ - لكن منطقي)\n'
        f'  - "قاعدة بيانات تحتوي على معلومات محددة مسبقاً" (خاطئ - لكن منطقي)\n'
        f'  - "جهاز كمبيوتر عالي السرعة فقط" (خاطئ - لكن منطقي)\n\n'
        f"تجنب:\n"
        f"- الأسئلة التي تبدو آلية أو مبرمجة\n"
        f"- الخيارات التي تكون واضحة أنها خاطئة بشكل مفرط\n"
        f"- استخدام نفس الكلمات من النص حرفياً دون فهم\n"
        f"- الأسئلة التي لا ترتبط بمحتوى النص\n\n"
        f"الهيكل المطلوب:\n"
        "{\n"
        '  "questions": [\n'
        "    {\n"
        '      "type": "mcq",\n'
        '      "text": "سؤال طبيعي وبشري بدون علامة استفهام",\n'
        '      "difficulty": "easy" or "medium" or "hard",\n'
        '      "mark": 1,\n'
        '      "model_answer": "شرح مختصر للإجابة الصحيحة (اختياري)",\n'
        '      "choices": [\n'
    )
    
    # إضافة مثال للخيارات بناءً على num_choices
    for i in range(1, num_choices + 1):
        is_correct = "true" if i == 1 else "false"
        user_prompt += f'        {{"text": "إجابة كاملة وطبيعية {i}", "is_correct": {is_correct}}},\n'
    
    user_prompt += (
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"تأكد من:\n"
        f"- قراءة وفهم النص بشكل كامل قبل توليد الأسئلة\n"
        f"- كل سؤال له بالضبط {num_choices} خيارات\n"
        f"- الأسئلة طبيعية وبشرية وليست آلية\n"
        f"- الخيارات منطقية ومقنعة\n"
        f"- إجابة واحدة فقط صحيحة في كل سؤال\n"
        f"- الأسئلة ترتبط مباشرة بمحتوى النص\n"
        f"- لا تضع علامة استفهام في نهاية السؤال\n\n"
        f"النص المرجعي:\n"
        '"""'
        f"{base_text}"
        '"""'
    )
    
    return system_prompt + "\n\n" + user_prompt


def _generate_questions_with_ollama(base_text, num_questions, question_type, difficulty, num_choices):
    """توليد الأسئلة باستخدام Ollama"""
    logger = logging.getLogger(__name__)
    base_url = getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = getattr(settings, "OLLAMA_MODEL", "llama3")
    
    # بناء prompt
    prompt = _build_ollama_prompt(base_text, num_questions, question_type, difficulty, num_choices)
    
    # إعداد الطلب
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    
    data = json.dumps(payload).encode("utf-8")
    url = base_url.rstrip("/") + "/api/generate"
    
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    
    # إرسال الطلب
    try:
        logger.info(f"Sending request to Ollama: {url}, model: {model}")
        with urllib.request.urlopen(req, timeout=1000) as resp:
            body = resp.read().decode("utf-8")
        
        # Parse الاستجابة
        questions = _parse_ollama_response(body)
        logger.info(f"Successfully generated {len(questions)} questions")
        return questions
        
    except urllib.error.URLError as e:
        logger.error(f"Ollama connection error: {str(e)}")
        raise urllib.error.URLError("فشل الاتصال بـ Ollama. تأكد من تشغيل الخدمة على المنفذ 11434.")
    except socket.timeout:
        logger.error("Ollama request timeout after 120 seconds")
        raise TimeoutError("انتهت مهلة الانتظار (120 ثانية). حاول تقليل عدد الأسئلة أو طول النص.")
    except ValueError as e:
        logger.error(f"Failed to parse Ollama response: {str(e)}")
        raise


def _extract_question_text(item):
    """استخراج نص السؤال من item"""
    return (
        item.get("text") or
        item.get("question") or
        item.get("prompt") or
        ""
    ).strip()


def _parse_question_type(item):
    """تحديد نوع السؤال"""
    q_type_raw = str(item.get("type", "mcq")).lower().strip()
    if "essay" in q_type_raw or "مقالي" in q_type_raw or "مقال" in q_type_raw:
        return Question.QuestionType.ESSAY
    return Question.QuestionType.MCQ


def _parse_difficulty(item):
    """تحديد مستوى الصعوبة"""
    diff_raw = str(item.get("difficulty", "medium")).lower().strip()
    if "easy" in diff_raw or "سهل" in diff_raw:
        return Question.Difficulty.EASY
    if "hard" in diff_raw or "صعب" in diff_raw:
        return Question.Difficulty.HARD
    return Question.Difficulty.MEDIUM


def _parse_mark(item):
    """تحديد العلامة"""
    mark = item.get("mark") or 1
    try:
        mark = float(mark)
        return max(1, mark)  # على الأقل 1
    except (TypeError, ValueError):
        return 1


def _parse_is_correct(value):
    """تحويل قيمة is_correct إلى boolean"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "نعم", "صحيح")
    return bool(value)


def _normalize_choice(choice):
    """تحويل choice إلى dictionary صالح"""
    if isinstance(choice, dict):
        return choice
    if isinstance(choice, str):
        try:
            parsed = json.loads(choice)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _save_question_choices(question, choices_data, num_choices=None):
    """حفظ خيارات السؤال"""
    logger = logging.getLogger(__name__)
    
    if not isinstance(choices_data, list):
        logger.warning(f"Choices is not a list: {type(choices_data)}")
        return 0, False
    
    choices_created = 0
    has_correct = False
    order = 1
    
    # معالجة جميع الخيارات بدون تقييد بعدد معين
    # (num_choices يستخدم فقط في الـ prompt، لكن نحفظ كل ما يأتي)
    for choice_data in choices_data:
        choice = _normalize_choice(choice_data)
        if not choice:
            continue
        
        choice_text = (choice.get("text") or "").strip()
        if not choice_text:
            continue
        
        is_correct = _parse_is_correct(choice.get("is_correct", False))
        if is_correct:
            has_correct = True
        
        QuestionChoice.objects.create(
            question=question,
            text=choice_text,
            is_correct=is_correct,
            order=order,
        )
        order += 1
        choices_created += 1
    
    # إذا لم تكن هناك إجابة صحيحة، اجعل الأول صحيحاً
    if not has_correct and choices_created > 0:
        first_choice = QuestionChoice.objects.filter(question=question).order_by("order").first()
        if first_choice:
            first_choice.is_correct = True
            first_choice.save(update_fields=["is_correct"])
            has_correct = True
            logger.info("Auto-marked first choice as correct")
    
    # التحقق من عدد الخيارات إذا كان num_choices محدد
    if num_choices and choices_created < num_choices:
        logger.warning(f"Expected {num_choices} choices but got {choices_created}")
    
    return choices_created, has_correct


def _save_single_question(subject, teacher, item, num_choices=None):
    """حفظ سؤال واحد"""
    logger = logging.getLogger(__name__)
    
    # استخراج البيانات الأساسية
    text = _extract_question_text(item)
    if not text:
        return None, "نص السؤال فارغ"
    
    q_type = _parse_question_type(item)
    difficulty = _parse_difficulty(item)
    mark = _parse_mark(item)
    model_answer = (item.get("model_answer") or item.get("answer") or "").strip()
    
    # التحقق من الخيارات للمسائل MCQ
    if q_type == Question.QuestionType.MCQ:
        choices = item.get("choices") or []
        if not choices:
            return None, "لا يحتوي على خيارات"
        # التحقق من عدد الخيارات
        if num_choices and len(choices) < num_choices:
            logger.warning(f"Question has {len(choices)} choices but expected {num_choices}")
    
    # إنشاء السؤال
    try:
        question = Question.objects.create(
            subject=subject,
            teacher=teacher,
            text=text,
            question_type=q_type,
            difficulty=difficulty,
            mark=mark,
            model_answer=model_answer,
        )
    except Exception as e:
        logger.error(f"Failed to create question: {str(e)}")
        return None, f"خطأ في إنشاء السؤال: {str(e)}"
    
    # حفظ الخيارات للمسائل MCQ
    if q_type == Question.QuestionType.MCQ:
        choices_created, has_correct = _save_question_choices(question, choices, num_choices)
        
        if choices_created < 2:
            question.delete()
            return None, f"لم يتم إنشاء خيارات كافية ({choices_created} خيار)"
        
        logger.info(f"Question created with {choices_created} choices")
    
    return question, None


def _save_generated_questions(subject, teacher, generated_questions, num_choices=None):
    """حفظ الأسئلة المُولدة في قاعدة البيانات"""
    logger = logging.getLogger(__name__)
    
    if not generated_questions:
        logger.warning("No questions to save")
        return 0, []
    
    logger.info(f"Attempting to save {len(generated_questions)} generated questions")
    
    created_count = 0
    error_details = []
    
    for idx, item in enumerate(generated_questions, start=1):
        try:
            # تحويل item إلى dictionary صالح
            normalized_item = _normalize_question_item(item)
            if not normalized_item:
                error_msg = f"سؤال {idx}: تنسيق غير صالح"
                error_details.append(error_msg)
                logger.warning(f"Question {idx}: Invalid format")
                continue
            
            # حفظ السؤال
            question, error_msg = _save_single_question(
                subject, teacher, normalized_item, num_choices
            )
            
            if question:
                created_count += 1
                logger.info(f"Question {idx}: Saved successfully")
            else:
                error_details.append(f"سؤال {idx}: {error_msg}")
                logger.warning(f"Question {idx}: {error_msg}")
                
        except Exception as e:
            error_msg = f"سؤال {idx}: خطأ غير متوقع - {str(e)}"
            error_details.append(error_msg)
            logger.error(f"Question {idx}: Unexpected error - {str(e)}", exc_info=True)
    
    logger.info(f"Save completed: {created_count} created, {len(error_details)} errors")
    
    return created_count, error_details

@login_required
@user_passes_test(is_teacher)
def teacher_question_edit(request, subject_id, question_id):
    user = request.user
    subject = get_object_or_404(Subject, id=subject_id, teacher=user)
    question = get_object_or_404(Question, id=question_id, subject=subject, teacher=user)

    if request.method == "POST" and "cancel" in request.POST:
        return redirect("teacher_subject_question_bank", subject_id=subject.id)

    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        question_type = request.POST.get("question_type", question.question_type)
        mark_raw = request.POST.get("mark", "").strip()
        difficulty = request.POST.get("difficulty", question.difficulty)
        model_answer = request.POST.get("model_answer", "").strip()

        errors = {}

        if not text:
            errors["text"] = "يرجى إدخال نص السؤال."

        mark = question.mark
        if mark_raw:
            try:
                mark = float(mark_raw)
                if mark <= 0:
                    raise ValueError
            except ValueError:
                errors["mark"] = "يرجى إدخال درجة صحيحة أكبر من صفر."

        valid_difficulties = {choice[0] for choice in Question.Difficulty.choices}
        if difficulty not in valid_difficulties:
            errors["difficulty"] = "يرجى اختيار مستوى صعوبة صحيح."

        choices_data = []
        correct_index = None
        if question_type == Question.QuestionType.MCQ:
            correct_raw = request.POST.get("correct_choice", "").strip()
            for key, value in request.POST.items():
                if not key.startswith("choices["):
                    continue
                if not key.endswith("][text]"):
                    continue
                try:
                    index_str = key.split("[", 1)[1].split("]", 1)[0]
                    index = int(index_str)
                except (IndexError, ValueError):
                    continue
                text_value = value.strip()
                if text_value:
                    choices_data.append((index, text_value))

            choices_data.sort(key=lambda x: x[0])

            if len(choices_data) < 2:
                errors["choices"] = "يرجى إدخال خيارين على الأقل."

            if correct_raw:
                try:
                    correct_index = int(correct_raw)
                except ValueError:
                    correct_index = None

            valid_choice_indices = {idx for idx, _ in choices_data}
            if correct_index is None or correct_index not in valid_choice_indices:
                errors["choices"] = "يرجى اختيار إجابة صحيحة واحدة من بين الخيارات."

        if not errors:
            try:
                from django.db import transaction
                with transaction.atomic():
                    question.text = text
                    question.question_type = question_type
                    question.mark = mark
                    question.difficulty = difficulty
                    question.model_answer = model_answer
                    question.save()

                    if question_type == Question.QuestionType.MCQ:
                        question.choices.all().delete()
                        order = 1
                        for idx, choice_text in choices_data:
                            QuestionChoice.objects.create(
                                question=question,
                                text=choice_text,
                                is_correct=(idx == correct_index),
                                order=order,
                            )
                            order += 1
                    else:
                        question.choices.all().delete()
                
                messages.success(request, "تم تحديث السؤال بنجاح.")
                if "save_and_continue" in request.POST:
                    return redirect(
                        "teacher_question_edit",
                        subject_id=subject.id,
                        question_id=question.id,
                    )
                return redirect("teacher_subject_question_bank", subject_id=subject.id)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error updating question {question.id}: {str(e)}")
                messages.error(request, f"فشل تحديث السؤال: {str(e)}")

    context = {
        "subject": subject,
        "question": question,
    }
    return render(request, "core/teacher_question_edit.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_subject_create(request):
    user = request.user
    students = User.objects.filter(
        role="student",
        is_active=True,
        is_staff=False
    ).filter(
        Q(student_groups__teacher=user) |
        Q(subject_enrollments__teacher=user) |
        Q(join_requests__teacher=user, join_requests__status=StudentJoinRequest.Status.ACCEPTED)
    ).distinct().order_by("full_name", "username")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        redirect_to_exams = "create_and_go_to_exams" in request.POST
        redirect_to_question_bank = "create_and_go_to_question_bank" in request.POST
        description = request.POST.get("description", "").strip()
        image_file = request.FILES.get("image")
        selected_students_raw = request.POST.get("selected_students", "").strip()
        selected_students_ids = [
            s for s in selected_students_raw.split(",") if s.strip()
        ]

        errors = {}
        if not name:
            errors["name"] = "يرجى إدخال اسم المادة."

        if not errors:
            subject = Subject.objects.create(
                name=name,
                description=description,
                teacher=user,
                image=image_file,
            )
            if selected_students_ids:
                selected_students_qs = (
                    User.objects.filter(
                        id__in=selected_students_ids,
                        role="student",
                        is_active=True,
                        is_staff=False,
                    ).distinct()
                )
                if selected_students_qs.exists():
                    subject.students.add(*selected_students_qs)
            messages.success(request, "تم إنشاء المادة بنجاح.")
            if redirect_to_exams:
                return redirect("teacher_subject_exam_create", subject_id=subject.id)
            if redirect_to_question_bank:
                return redirect("teacher_subject_question_bank", subject_id=subject.id)
            return redirect("teacher_subjects")
    else:
        name = ""
        description = ""
        errors = {}
        selected_students_ids = []

    context = {
        "name": name,
        "description": description,
        "errors": errors,
        "students": students,
        "selected_students": selected_students_ids,
        "is_edit": False,
        "subject": None,
    }
    return render(request, "core/teacher_subject_create.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_subject_edit(request, subject_id):
    user = request.user
    subject = get_object_or_404(Subject, id=subject_id, teacher=user)
    students = User.objects.filter(
        role="student",
        is_active=True,
        is_staff=False
    ).filter(
        Q(student_groups__teacher=user) |
        Q(subject_enrollments__teacher=user) |
        Q(join_requests__teacher=user, join_requests__status=StudentJoinRequest.Status.ACCEPTED)
    ).distinct().order_by("full_name", "username")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        image_file = request.FILES.get("image")
        selected_students_raw = request.POST.get("selected_students", "").strip()
        selected_students_ids = [
            s for s in selected_students_raw.split(",") if s.strip()
        ]

        errors = {}
        if not name:
            errors["name"] = "يرجى إدخال اسم المادة."

        if not errors:
            subject.name = name
            subject.description = description
            if image_file:
                subject.image = image_file
            subject.save()

            subject.students.clear()
            if selected_students_ids:
                selected_students_qs = (
                    User.objects.filter(
                        id__in=selected_students_ids,
                        role="student",
                        is_active=True,
                        is_staff=False,
                    ).distinct()
                )
                if selected_students_qs.exists():
                    subject.students.add(*selected_students_qs)

            messages.success(request, "تم تحديث المادة بنجاح.")
            return redirect("teacher_subjects")
    else:
        name = subject.name
        description = subject.description
        selected_students_ids = list(
            subject.students.filter(
                role="student",
                is_active=True,
                is_staff=False,
            ).values_list("id", flat=True)
        )

    context = {
        "name": name,
        "description": description,
        "errors": {},
        "students": students,
        "selected_students": [str(sid) for sid in selected_students_ids],
        "is_edit": True,
        "subject": subject,
    }
    return render(request, "core/teacher_subject_create.html", context)


@login_required
@user_passes_test(is_teacher)
@require_POST
def teacher_subject_delete(request, subject_id):
    """
    حذف مادة دراسية
    """
    user = request.user
    subject = get_object_or_404(Subject, id=subject_id, teacher=user)
    
    try:
        subject_name = subject.name
        subject.delete()
        messages.success(request, f"تم حذف المادة '{subject_name}' بنجاح.", extra_tags="user:teacher")
    except Exception as e:
        logger.error(f"Error deleting subject {subject_id}: {str(e)}")
        messages.error(request, f"فشل حذف المادة: {str(e)}", extra_tags="user:teacher")
    
    return HttpResponseRedirect(reverse("teacher_subjects"))


@login_required
@user_passes_test(is_teacher)
def teacher_exam_create(request, subject_id=None):
    """
    إنشاء اختبار جديد:
    - تحديد تفاصيل الاختبار (الاسم، المادة، الوقت، المدة).
    - ضبط إعدادات المراقبة الآلية.
    - اختيار الطلاب المسموح لهم بدخول الاختبار (اختياري).
    """
    user = request.user
    active_subject = None
    if subject_id is not None:
        active_subject = get_object_or_404(Subject, id=subject_id, teacher=user)

    subjects = Subject.objects.filter(teacher=user).order_by("name")
    students = User.objects.filter(
        role="student",
        is_active=True,
        is_staff=False
    ).filter(
        Q(student_groups__teacher=user) |
        Q(subject_enrollments__teacher=user) |
        Q(join_requests__teacher=user, join_requests__status=StudentJoinRequest.Status.ACCEPTED)
    ).distinct().order_by("full_name", "username")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        total_mark_raw = request.POST.get("total_mark", "").strip()
        duration_raw = request.POST.get("duration_minutes", "").strip()
        late_join_raw = request.POST.get("late_join_minutes", "").strip()
        start_raw = request.POST.get("start_time", "").strip()
        marking_type = request.POST.get("marking_type", "per_question")
        shuffle_questions = request.POST.get("shuffle_questions") == "on"
        auto_proctoring = request.POST.get("auto_proctoring") == "on"
        auto_fail_on_cheating = request.POST.get("auto_fail_on_cheating") == "on"
        selected_students_raw = request.POST.get("selected_students", "").strip()
        selected_students_ids = [
            s for s in selected_students_raw.split(",") if s.strip()
        ]

        if active_subject is not None:
            subject = active_subject
        else:
            subject_id_raw = request.POST.get("subject") or ""
            subject = None
            if subject_id_raw:
                try:
                    subject = subjects.get(id=subject_id_raw)
                except Subject.DoesNotExist:
                    subject = None

        errors = {}

        if not title:
            errors["title"] = "يرجى إدخال اسم الاختبار."

        total_mark = None
        if total_mark_raw:
            try:
                total_mark = int(total_mark_raw)
                if total_mark <= 0:
                    raise ValueError
            except ValueError:
                errors["total_mark"] = "يرجى إدخال علامة كلية صحيحة أكبر من صفر."
        else:
            errors["total_mark"] = "يرجى إدخال العلامة الكلية للاختبار."

        duration_minutes = None
        if duration_raw:
            try:
                duration_minutes = int(duration_raw)
                if duration_minutes <= 0:
                    raise ValueError
            except ValueError:
                errors["duration_minutes"] = "يرجى إدخال مدة صحيحة بالدقائق."
        else:
            errors["duration_minutes"] = "يرجى تحديد مدة الاختبار بالدقائق."

        late_join_minutes = 0
        if late_join_raw:
            try:
                late_join_minutes = int(late_join_raw)
                if late_join_minutes < 0:
                    raise ValueError
            except ValueError:
                errors["late_join_minutes"] = "يرجى إدخال قيمة صحيحة لمنع الدخول."

        from django.utils.dateparse import parse_datetime
        from django.utils import timezone

        start_time = None

        if start_raw:
            start_time = parse_datetime(start_raw)
            if start_time is None:
                errors["start_time"] = "صيغة وقت البدء غير صحيحة."
        else:
            errors["start_time"] = "يرجى تحديد وقت بدء الاختبار."

        if start_time is not None:
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time, timezone.get_current_timezone())

        if subject is None:
            errors["subject"] = "يرجى اختيار المادة المرتبطة بالاختبار."

        if not errors:
            initial_status = Exam.Status.SCHEDULED
            if start_time is None:
                initial_status = Exam.Status.DRAFT
            exam = Exam.objects.create(
                title=title,
                teacher=user,
                subject=subject,
                start_time=start_time,
                duration_minutes=duration_minutes,
                status=initial_status,
                total_mark=total_mark,
                end_time=None,  # Will be calculated as start_time + duration_minutes
                late_join_minutes=late_join_minutes,
                shuffle_questions=shuffle_questions,
                auto_proctoring=auto_proctoring,
                auto_fail_on_cheating=auto_fail_on_cheating,
                marking_type=marking_type,
            )
            if selected_students_ids:
                allowed_students = list(students.filter(id__in=selected_students_ids))
                if allowed_students:
                    exam.allowed_students.add(*allowed_students)
                    exam.total_participants = len(allowed_students)
                    exam.save(update_fields=["total_participants"])
            messages.success(request, "تم إنشاء الاختبار بنجاح. يمكنك الآن إضافة الأسئلة.")
            # Redirect to exam questions page to add questions immediately
            return redirect("teacher_exam_questions", exam_id=exam.id)

        context = {
            "title": title,
            "total_mark": total_mark_raw,
            "duration_minutes": duration_raw,
            "late_join_minutes": late_join_raw,
            "start_time": start_raw,
            "marking_type": marking_type,
            "shuffle_questions": shuffle_questions,
            "auto_proctoring": auto_proctoring,
            "auto_fail_on_cheating": auto_fail_on_cheating,
            "subjects": subjects,
            "active_subject": active_subject,
            "students": students,
            "selected_students": selected_students_ids,
            "selected_students_raw": selected_students_raw,
            "errors": errors,
            "is_edit": False,
        }
        return render(request, "core/teacher_exam_create.html", context)

    context = {
        "title": "",
        "total_mark": "",
        "duration_minutes": "",
        "late_join_minutes": "",
        "start_time": "",
        "marking_type": "per_question",
        "shuffle_questions": False,
        "auto_proctoring": True,
        "auto_fail_on_cheating": False,
        "subjects": subjects,
        "active_subject": active_subject,
        "students": students,
        "selected_students": [],
        "selected_students_raw": "",
        "errors": {},
        "is_edit": False,
    }
    return render(request, "core/teacher_exam_create.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_exam_edit(request, exam_id):
    """
    تعديل بيانات الاختبار:
    - تحديث الإعدادات الزمنية والرقابية.
    - إدارة قائمة الطلاب المستهدفين.
    - ملاحظة: لا يمكن تعديل الاختبار بعد بدئه (يجب أن يكون في حالة مسودة أو مجدول).
    """
    user = request.user
    exam = get_object_or_404(
        Exam,
        id=exam_id,
        teacher=user,
        status__in=[Exam.Status.DRAFT, Exam.Status.SCHEDULED],
    )

    exam_questions = (
        ExamQuestion.objects.filter(exam=exam)
        .select_related("question")
        .order_by("order", "id")
    )

    subjects = Subject.objects.filter(teacher=user).order_by("name")
    students = User.objects.filter(
        role="student",
        is_active=True,
        is_staff=False
    ).filter(
        Q(student_groups__teacher=user) |
        Q(subject_enrollments__teacher=user) |
        Q(join_requests__teacher=user, join_requests__status=StudentJoinRequest.Status.ACCEPTED)
    ).distinct().order_by("full_name", "username")

    active_subject = exam.subject

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        total_mark_raw = request.POST.get("total_mark", "").strip()
        duration_raw = request.POST.get("duration_minutes", "").strip()
        late_join_raw = request.POST.get("late_join_minutes", "").strip()
        start_raw = request.POST.get("start_time", "").strip()
        marking_type = request.POST.get("marking_type", exam.marking_type)
        shuffle_questions = request.POST.get("shuffle_questions") == "on"
        auto_proctoring = request.POST.get("auto_proctoring") == "on"
        auto_fail_on_cheating = request.POST.get("auto_fail_on_cheating") == "on"
        selected_students_raw = request.POST.get("selected_students", "").strip()
        selected_students_ids = [
            s for s in selected_students_raw.split(",") if s.strip()
        ]

        subject = active_subject

        errors = {}

        if not title:
            errors["title"] = "يرجى إدخال اسم الاختبار."

        total_mark = None
        if total_mark_raw:
            try:
                total_mark = int(total_mark_raw)
                if total_mark <= 0:
                    raise ValueError
            except ValueError:
                errors["total_mark"] = "يرجى إدخال علامة كلية صحيحة أكبر من صفر."
        else:
            errors["total_mark"] = "يرجى إدخال العلامة الكلية للاختبار."

        duration_minutes = None
        if duration_raw:
            try:
                duration_minutes = int(duration_raw)
                if duration_minutes <= 0:
                    raise ValueError
            except ValueError:
                errors["duration_minutes"] = "يرجى إدخال مدة صحيحة بالدقائق."
        else:
            errors["duration_minutes"] = "يرجى تحديد مدة الاختبار بالدقائق."

        late_join_minutes = 0
        if late_join_raw:
            try:
                late_join_minutes = int(late_join_raw)
                if late_join_minutes < 0:
                    raise ValueError
            except ValueError:
                errors["late_join_minutes"] = "يرجى إدخال قيمة صحيحة لمنع الدخول."

        from django.utils.dateparse import parse_datetime
        from django.utils import timezone

        start_time = None

        if start_raw:
            start_time = parse_datetime(start_raw)
            if start_time is None:
                errors["start_time"] = "صيغة وقت البدء غير صحيحة."
        else:
            errors["start_time"] = "يرجى تحديد وقت بدء الاختبار."

        if start_time is not None:
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(
                    start_time, timezone.get_current_timezone()
                )

        if subject is None:
            errors["subject"] = "يرجى اختيار المادة المرتبطة بالاختبار."

        if not errors:
            exam.title = title
            exam.subject = subject
            exam.start_time = start_time
            exam.duration_minutes = duration_minutes
            exam.total_mark = total_mark
            exam.end_time = None  # Will be calculated as start_time + duration_minutes
            exam.late_join_minutes = late_join_minutes
            exam.shuffle_questions = shuffle_questions
            exam.auto_proctoring = auto_proctoring
            exam.auto_fail_on_cheating = auto_fail_on_cheating
            exam.marking_type = marking_type
            if selected_students_ids:
                allowed_students = list(students.filter(id__in=selected_students_ids))
                exam.allowed_students.set(allowed_students)
                if allowed_students:
                    exam.total_participants = len(allowed_students)
            else:
                exam.allowed_students.clear()
                exam.total_participants = 0
            exam.save()
            messages.success(request, "تم تحديث الاختبار بنجاح.")
            return redirect("teacher_exams")

        context = {
            "title": title,
            "total_mark": total_mark_raw,
            "duration_minutes": duration_raw,
            "late_join_minutes": late_join_raw,
            "start_time": start_raw,
            "marking_type": marking_type,
            "shuffle_questions": shuffle_questions,
            "auto_proctoring": auto_proctoring,
            "auto_fail_on_cheating": auto_fail_on_cheating,
            "subjects": subjects,
            "active_subject": active_subject,
            "students": students,
            "selected_students": selected_students_ids,
            "selected_students_raw": selected_students_raw,
            "errors": errors,
            "is_edit": True,
            "exam": exam,
            "exam_questions": exam_questions,
        }
        return render(request, "core/teacher_exam_create.html", context)

    # Get currently selected students
    selected_student_ids = list(exam.allowed_students.values_list("id", flat=True))
    selected_students_raw = ",".join(str(sid) for sid in selected_student_ids)
    
    context = {
        "title": exam.title,
        "total_mark": str(exam.total_mark),
        "duration_minutes": str(exam.duration_minutes),
        "late_join_minutes": str(exam.late_join_minutes),
        "start_time": exam.start_time.isoformat(timespec="minutes") if exam.start_time else "",
        "marking_type": exam.marking_type,
        "shuffle_questions": exam.shuffle_questions,
        "auto_proctoring": exam.auto_proctoring,
        "auto_fail_on_cheating": exam.auto_fail_on_cheating,
        "subjects": subjects,
        "active_subject": active_subject,
        "students": students,
        "selected_students": selected_student_ids,
        "selected_students_raw": selected_students_raw,
        "errors": {},
        "is_edit": True,
        "exam": exam,
        "exam_questions": exam_questions,
    }
    return render(request, "core/teacher_exam_create.html", context)


@login_required
@user_passes_test(is_teacher)
@require_POST
def teacher_exam_delete(request, exam_id):
    """
    حذف اختبار (يُسمح بحذف المسودة، المجدول، والمكتمل - لا يُسمح بحذف الجارِ)
    """
    from django.http import HttpResponseRedirect
    
    user = request.user
    exam = get_object_or_404(Exam, id=exam_id, teacher=user)
    
    # Only prevent deletion of ONGOING exams
    if exam.status == Exam.Status.ONGOING:
        messages.error(request, "لا يمكن حذف اختبار جارٍ حالياً. انتظر حتى ينتهي الاختبار.", extra_tags="user:teacher")
        return HttpResponseRedirect(reverse("teacher_exams"))
    
    # Allow deletion of DRAFT, SCHEDULED, and FINISHED exams
    try:
        exam_title = exam.title
        exam_status = exam.get_status_display()
        exam.delete()
        messages.success(request, f"تم حذف الاختبار '{exam_title}' ({exam_status}) بنجاح.", extra_tags="user:teacher")
    except Exception as e:
        logger.error(f"Error deleting exam {exam_id}: {str(e)}")
        messages.error(request, f"فشل حذف الاختبار: {str(e)}", extra_tags="user:teacher")
    
    # Use HttpResponseRedirect to ensure session is preserved
    return HttpResponseRedirect(reverse("teacher_exams"))

@login_required
def sync_exam_statuses_api(request):
    """
    API endpoint لتحديث حالة الاختبارات تلقائياً (للاستخدام مع AJAX)
    """
    from django.utils import timezone
    
    user = request.user
    
    if user.role == "teacher":
        exams = Exam.objects.filter(teacher=user).select_related("subject")
    elif user.role == "student":
        exams = Exam.objects.filter(allowed_students=user).select_related("subject", "teacher")
    elif user.is_staff:
        exams = Exam.objects.all().select_related("subject", "teacher")
    else:
        return JsonResponse({"error": "Unauthorized"}, status=403)
    
    # Annotate with counts
    exams = exams.annotate(
        questions_count=Count("exam_questions", distinct=True),
        allowed_students_count=Count("allowed_students", distinct=True)
    )
    
    updated_count = _sync_exam_statuses(exams)
    
    # Return updated exam statuses
    exam_statuses = {}
    for exam in exams:
        exam_statuses[exam.id] = {
            "status": exam.status,
            "status_display": exam.get_status_display(),
        }
    
    return JsonResponse({
        "success": True,
        "updated_count": updated_count,
        "exam_statuses": exam_statuses,
    })


@login_required
@user_passes_test(is_admin)
def admin_settings(request):
    settings_obj = SystemSettings.load()
    user = request.user

    account_error = ""
    account_success = ""
    system_success = ""

    if request.method == "POST":
        if "profile_submit" in request.POST:
            full_name = request.POST.get("full_name", "").strip()
            email = request.POST.get("email", "").strip()

            if full_name:
                user.full_name = full_name
            user.email = email
            user.save()
            account_success = "تم تحديث بيانات الحساب بنجاح."

        elif "password_submit" in request.POST:
            current_password = request.POST.get("current_password", "")
            new_password = request.POST.get("new_password", "")

            if not current_password or not new_password:
                account_error = "يرجى إدخال كلمة المرور الحالية والجديدة معًا."
            elif not check_password(current_password, user.password):
                account_error = "كلمة المرور الحالية غير صحيحة."
            else:
                try:
                    validate_password(new_password, user)
                    user.set_password(new_password)
                    update_session_auth_hash(request, user)
                    user.save()
                    account_success = "تم تحديث كلمة المرور بنجاح."
                except ValidationError as exc:
                    account_error = " ".join(exc.messages)

        elif "system_submit" in request.POST:
            platform_name = request.POST.get("platform_name", "").strip()
            two_factor_email = request.POST.get("two_factor_email", "").strip()
            two_factor_app_password = request.POST.get(
                "two_factor_app_password", ""
            ).strip()
            icon_file = request.FILES.get("system_icon")

            if platform_name:
                settings_obj.platform_name = platform_name
            settings_obj.two_factor_email = two_factor_email

            if two_factor_app_password:
                settings_obj.two_factor_app_password = two_factor_app_password

            if icon_file:
                settings_obj.system_icon = icon_file

            settings_obj.save()
            system_success = "تم تحديث إعدادات النظام بنجاح."

    effective_two_factor_email = (
        settings_obj.two_factor_email or getattr(settings, "EMAIL_HOST_USER", "")
    )

    context = {
        "settings_obj": settings_obj,
        "effective_two_factor_email": effective_two_factor_email,
        "account_error": account_error,
        "account_success": account_success,
        "system_success": system_success,
    }
    return render(request, "core/admin_settings.html", context)
