from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from accounts.models import User
from .models import (
    Subject,
    Exam,
    Question,
    QuestionChoice,
    ExamQuestion,
    StudentExam,
    StudentAnswer,
    ExamEvent,
    Group,
)


class SubjectExamCascadeDeleteTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher1",
            password="testpass123",
            role="teacher",
        )

    def test_exams_deleted_when_subject_deleted(self):
        subject = Subject.objects.create(
            name="رياضيات",
            description="مادة الرياضيات",
            teacher=self.teacher,
        )

        other_subject = Subject.objects.create(
            name="فيزياء",
            description="مادة الفيزياء",
            teacher=self.teacher,
        )

        exam1 = Exam.objects.create(
            title="اختبار 1",
            subject=subject,
            teacher=self.teacher,
            start_time=timezone.now(),
            duration_minutes=60,
        )
        exam2 = Exam.objects.create(
            title="اختبار 2",
            subject=subject,
            teacher=self.teacher,
            start_time=timezone.now(),
            duration_minutes=45,
        )
        other_exam = Exam.objects.create(
            title="اختبار فيزياء",
            subject=other_subject,
            teacher=self.teacher,
            start_time=timezone.now(),
            duration_minutes=30,
        )

        self.assertEqual(Exam.objects.filter(subject=subject).count(), 2)
        self.assertTrue(Exam.objects.filter(id=exam1.id).exists())
        self.assertTrue(Exam.objects.filter(id=exam2.id).exists())
        self.assertTrue(Exam.objects.filter(id=other_exam.id).exists())

        subject.delete()

        self.assertEqual(Exam.objects.filter(subject=subject).count(), 0)
        self.assertFalse(Exam.objects.filter(id=exam1.id).exists())
        self.assertFalse(Exam.objects.filter(id=exam2.id).exists())
        self.assertTrue(Exam.objects.filter(id=other_exam.id).exists())

    def test_delete_subject_via_view_removes_exams_from_ui(self):
        subject = Subject.objects.create(
            name="أحياء",
            description="مادة الأحياء",
            teacher=self.teacher,
        )

        Exam.objects.create(
            title="اختبار أحياء",
            subject=subject,
            teacher=self.teacher,
            start_time=timezone.now(),
            duration_minutes=40,
        )

        self.client.force_login(self.teacher)

        response = self.client.post(
            f"/teacher-dashboard/subjects/{subject.id}/delete/", follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Subject.objects.filter(id=subject.id).exists())
        self.assertEqual(Exam.objects.filter(subject=subject).count(), 0)

        exams_response = self.client.get("/teacher-dashboard/exams/")
        self.assertEqual(exams_response.status_code, 200)
        self.assertNotContains(exams_response, "اختبار أحياء")


class ExamFlowTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher_exam",
            password="testpass123",
            role="teacher",
        )
        self.student = User.objects.create_user(
            username="student1",
            password="testpass123",
            role="student",
        )

        self.subject = Subject.objects.create(
            name="رياضيات",
            description="مادة الرياضيات",
            teacher=self.teacher,
        )

        self.group = Group.objects.create(
            name="مجموعة تجريبية",
            code="testgroup1",
            subject=self.subject,
            teacher=self.teacher,
        )
        self.group.students.add(self.student)

        self.question = Question.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            text="ما حاصل 2 + 2؟",
            question_type=Question.QuestionType.MCQ,
            difficulty=Question.Difficulty.EASY,
            mark=1,
        )
        self.choice_correct = QuestionChoice.objects.create(
            question=self.question,
            text="4",
            is_correct=True,
            order=1,
        )
        self.choice_wrong = QuestionChoice.objects.create(
            question=self.question,
            text="5",
            is_correct=False,
            order=2,
        )

        start = timezone.now() - timezone.timedelta(minutes=1)
        self.exam = Exam.objects.create(
            title="اختبار تجريبي",
            subject=self.subject,
            teacher=self.teacher,
            start_time=start,
            duration_minutes=10,
            total_mark=1,
            late_join_minutes=5,
            status=Exam.Status.SCHEDULED,
        )
        ExamQuestion.objects.create(
            exam=self.exam,
            question=self.question,
            order=1,
            mark=1,
        )
        self.exam.allowed_students.add(self.student)
        self.exam.total_participants = 1
        self.exam.save(update_fields=["total_participants"])

    def test_student_exam_and_answers_flow(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("student_exam_take", args=[self.exam.id]))
        # إذا قام view بإعادة التوجيه نحو قائمة الاختبارات بسبب الرسائل،
        # فهذا يعني أن الوصول مسموح وتم إنشاء محاولة، وهو سلوك مقبول هنا.
        self.assertIn(response.status_code, (200, 302))

        attempt = StudentExam.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(attempt.status, StudentExam.Status.IN_PROGRESS)
        self.assertIsNotNone(attempt.started_at)

        response = self.client.post(
            reverse("student_exam_take", args=[self.exam.id]) + "?q=1",
            {
                "action": "next",
                "current_index": "1",
                "choice": str(self.choice_correct.id),
            },
        )
        self.assertEqual(response.status_code, 302)

        answer = StudentAnswer.objects.get(attempt=attempt)
        self.assertEqual(answer.exam_question.question, self.question)
        self.assertEqual(answer.selected_choice, self.choice_correct)
        self.assertTrue(answer.is_correct)

    def test_exam_event_creation_via_api(self):
        self.client.force_login(self.student)

        url = reverse("student_exam_event", args=[self.exam.id])
        response = self.client.post(
            url,
            {"event_type": ExamEvent.EventType.CHEATING_VISIBILITY, "message": "test"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)

        event = ExamEvent.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(event.event_type, ExamEvent.EventType.CHEATING_VISIBILITY)
        self.assertEqual(event.message, "test")
