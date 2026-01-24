# Examination System - Class Diagram Summary

## ملخص سريع للنماذج والعلاقات

### إحصائيات النظام
- **إجمالي النماذج**: 19 نموذج
- **إجمالي العلاقات**: 50+ علاقة
- **علاقات One-to-Many**: 30+
- **علاقات Many-to-Many**: 3
- **علاقات One-to-One**: 2
- **علاقات Self-Reference**: 1

---

## تصنيف النماذج حسب الوظيفة

### 1. إدارة المستخدمين (2 نماذج)
- `User` - المستخدم الرئيسي
- `TeacherNotificationSettings` - إعدادات إشعارات المدرسين

### 2. المواد والمجموعات (2 نماذج)
- `Subject` - المادة الدراسية
- `Group` - المجموعة الدراسية

### 3. بنك الأسئلة (2 نماذج)
- `Question` - السؤال
- `QuestionChoice` - خيارات السؤال

### 4. إدارة الاختبارات (2 نماذج)
- `Exam` - الاختبار
- `ExamQuestion` - ربط السؤال بالاختبار

### 5. محاولات الطلاب (2 نماذج)
- `StudentExam` - محاولة الطالب
- `StudentAnswer` - إجابة الطالب

### 6. الأحداث والإشعارات (2 نماذج)
- `ExamEvent` - حدث أثناء الاختبار
- `ExamNotification` - إشعار من المدرس

### 7. نظام الرسائل (2 نماذج)
- `Message` - رسالة بين المستخدمين
- `GroupMessage` - رسالة في مجموعة

### 8. طلبات الانضمام (1 نموذج)
- `StudentJoinRequest` - طلب انضمام طالب

### 9. إعدادات النظام (1 نموذج)
- `SystemSettings` - إعدادات عامة

### 10. نظام المراقبة (3 نماذج)
- `ProctorSession` - جلسة المراقبة
- `ProctorSnapshot` - صورة من الكاميرا
- `ProctorAudioStream` - البث الصوتي

---

## العلاقات الرئيسية

### User (المستخدم) - المركز الرئيسي
```
User
├── OneToOne → TeacherNotificationSettings
├── OneToMany → Subject (as teacher)
├── OneToMany → Group (as teacher)
├── OneToMany → Exam (as teacher)
├── OneToMany → Question (as teacher)
├── OneToMany → StudentExam (as student)
├── OneToMany → ExamEvent (as student)
├── OneToMany → ExamNotification (sender/recipient)
├── OneToMany → Message (sender/recipient)
├── OneToMany → GroupMessage (sender)
├── OneToMany → StudentJoinRequest (student/teacher)
├── OneToMany → ProctorSession (student)
├── ManyToMany → Subject (enrolled_students)
├── ManyToMany → Group (students)
└── ManyToMany → Exam (allowed_students)
```

### Exam (الاختبار) - الكيان المركزي
```
Exam
├── ManyToOne → Subject
├── ManyToOne → User (teacher)
├── ManyToMany → User (allowed_students)
├── OneToMany → ExamQuestion
├── OneToMany → StudentExam
├── OneToMany → ExamEvent
├── OneToMany → ExamNotification
└── OneToMany → ProctorSession
```

### Subject (المادة) - التنظيم الأكاديمي
```
Subject
├── ManyToOne → User (teacher)
├── ManyToMany → User (students)
├── OneToMany → Group
├── OneToMany → Exam
└── OneToMany → Question
```

---

## الأنواع (Enums) المستخدمة

### UserRole
- `STUDENT` - طالب
- `TEACHER` - مدرس
- (Admin: `is_superuser=True`)

### ExamStatus
- `DRAFT` - مسودة
- `SCHEDULED` - مجدول
- `ONGOING` - جاري
- `FINISHED` - مكتمل

### QuestionType
- `MCQ` - اختيار من متعدد
- `ESSAY` - مقالي

### QuestionDifficulty
- `EASY` - سهل
- `MEDIUM` - متوسط
- `HARD` - صعب

### StudentExamStatus
- `IN_PROGRESS` - قيد التنفيذ
- `FINISHED` - مكتمل
- `FAILED_CHEATING` - فشل بسبب الغش

### ExamEventType
- `JOIN` - انضمام
- `SUBMIT` - إرسال
- `PROGRESS` - تقدم
- `CHEATING_VISIBILITY` - محاولة غش (إخفاء النافذة)
- `CHEATING_CLIPBOARD` - محاولة غش (نسخ/لصق)
- `CAMERA_ALLOWED` - السماح بالكاميرا
- `CAMERA_DENIED` - رفض الكاميرا

### MessageDirection
- `TEACHER_TO_SUPERVISOR` - من المدرس للمشرف
- `SUPERVISOR_TO_TEACHER` - من المشرف للمدرس
- `TEACHER_TO_STUDENT` - من المدرس للطالب
- `STUDENT_TO_TEACHER` - من الطالب للمدرس
- `SUPERVISOR_TO_SUPERVISOR` - من مشرف لمشرف

### JoinRequestStatus
- `PENDING` - في الانتظار
- `ACCEPTED` - مقبول
- `REJECTED` - مرفوض

### JoinRequestSource
- `FROM_STUDENT` - من الطالب
- `FROM_TEACHER` - من المدرس

### ProctorStreamStatus
- `WAITING` - في الانتظار
- `ACTIVE` - نشط
- `PAUSED` - متوقف مؤقتاً
- `ENDED` - منتهي

---

## القيود (Constraints)

### Unique Constraints
1. **ExamQuestion**: `(exam, question)` - سؤال واحد لا يمكن أن يكون في نفس الاختبار مرتين
2. **StudentExam**: `(exam, student)` - طالب واحد لا يمكن أن يحاول نفس الاختبار مرتين
3. **StudentAnswer**: `(attempt, exam_question)` - إجابة واحدة لكل سؤال في كل محاولة
4. **ProctorSession**: `(exam, student)` - جلسة مراقبة واحدة لكل طالب في كل اختبار
5. **Group**: `code` - كود فريد للمجموعة

---

## تدفقات العمل الرئيسية

### 1. إنشاء اختبار
```
Teacher → Exam → ExamQuestion → Question
```

### 2. محاولة الطالب
```
Student → StudentExam → StudentAnswer → ExamQuestion → Question
```

### 3. نظام المراقبة
```
Student → ProctorSession → ProctorSnapshot
                    ↓
            ProctorAudioStream
```

### 4. نظام الرسائل
```
User → Message → Message (reply)
User → GroupMessage → Group
```

### 5. طلبات الانضمام
```
Student → StudentJoinRequest → Teacher
Teacher → StudentJoinRequest → Student
```

---

## استخدام المخطط في SRS

### Section 3: System Design
- استخدم المخطط لشرح هيكلية قاعدة البيانات
- اشرح العلاقات بين الكيانات

### Section 4: Data Models
- استخدم المخطط كمرجع لكل نموذج بيانات
- اشرح كل حقل وعلاقته

### Section 5: System Architecture
- استخدم المخطط لشرح بنية البيانات
- اشرح كيفية تفاعل المكونات

### Appendix A: Database Schema
- ضع المخطط كملحق في نهاية الوثيقة

---

## الملفات المتوفرة

1. **examination_system_class_diagram.puml** - مخطط PlantUML (الأكثر تفصيلاً)
2. **examination_system_class_diagram.mmd** - مخطط Mermaid (للاستخدام في GitHub)
3. **examination_system_class_diagram_simple.md** - وصف نصي مفصل لكل نموذج
4. **README.md** - دليل الاستخدام
5. **CLASS_DIAGRAM_SUMMARY.md** - هذا الملف (ملخص سريع)

---

## كيفية التحديث

عند إضافة نماذج جديدة أو تعديل النماذج الموجودة:

1. افتح ملف `.puml` أو `.mmd`
2. أضف/عدّل النموذج الجديد
3. أضف العلاقات الجديدة
4. اختبر المخطط
5. قم بتحديث الملفات التوثيقية

---

## المراجع

- Django Models Documentation
- PlantUML Documentation: https://plantuml.com/
- Mermaid Documentation: https://mermaid.js.org/
