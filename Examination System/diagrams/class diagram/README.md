# Examination System - Class Diagram Documentation

## نظرة عامة

هذا الملف يحتوي على مخطط Class Diagram أكاديمي ومنظم لنظام الاختبارات الذكية (Examination System). المخطط يتبع معايير UML ويتم تنظيم النماذج في Packages منطقية حسب الوظيفة.

## هيكلية المخطط

المخطط منظم في **6 Packages رئيسية**:

### 1. **User Management** (إدارة المستخدمين)
- `User` - المستخدم الرئيسي (يمتد من AbstractUser)
- `TeacherNotificationSettings` - إعدادات إشعارات المدرسين

### 2. **Academic Management** (الإدارة الأكاديمية)
- `Subject` - المادة الدراسية
- `Group` - المجموعة الدراسية
- `Question` - السؤال
- `QuestionChoice` - خيارات السؤال

### 3. **Exam Management** (إدارة الاختبارات)
- `Exam` - الاختبار
- `ExamQuestion` - ربط السؤال بالاختبار
- `StudentExam` - محاولة الطالب
- `StudentAnswer` - إجابة الطالب
- `ExamEvent` - حدث أثناء الاختبار
- `ExamNotification` - إشعار من المدرس

### 4. **Proctoring System** (نظام المراقبة)
- `ProctorSession` - جلسة المراقبة
- `ProctorSnapshot` - صورة من الكاميرا
- `ProctorAudioStream` - البث الصوتي

### 5. **Communication System** (نظام التواصل)
- `Message` - رسالة بين المستخدمين
- `GroupMessage` - رسالة في مجموعة
- `StudentJoinRequest` - طلب انضمام طالب

### 6. **System Configuration** (إعدادات النظام)
- `SystemSettings` - إعدادات عامة للنظام

## الملفات المتوفرة

### 1. examination_system_class_diagram.puml
**الوصف**: مخطط PlantUML أكاديمي ومنظم  
**المميزات**:
- منظم في Packages منطقية
- ألوان مختلفة لكل Package
- علاقات واضحة ومنظمة
- ملاحظات أكاديمية
- يتبع معايير UML

**كيفية الاستخدام**:
1. افتح [PlantUML Online Server](http://www.plantuml.com/plantuml/uml/)
2. انسخ محتوى الملف
3. الصق في المحرر
4. سيتم توليد المخطط تلقائياً

### 2. examination_system_class_diagram.mmd
**الوصف**: مخطط Mermaid منظم  
**المميزات**:
- مناسب للعرض في GitHub
- يدعمه VS Code وMarkdown
- منظم في أقسام واضحة

**كيفية الاستخدام**:
- في GitHub: الملف يعرض تلقائياً
- في VS Code: استخدم إضافة Mermaid
- في Markdown: استخدم محررات تدعم Mermaid

### 3. examination_system_class_diagram_simple.md
**الوصف**: وصف نصي مفصل لكل نموذج  
**المميزات**:
- شرح تفصيلي لكل حقل
- العلاقات موضحة
- مناسب كمرجع سريع

### 4. CLASS_DIAGRAM_SUMMARY.md
**الوصف**: ملخص سريع للنظام  
**المميزات**:
- إحصائيات النظام
- تدفقات العمل
- ملاحظات مهمة

## التنظيم الأكاديمي

### معايير UML المستخدمة

1. **Packages**: تجميع النماذج حسب الوظيفة
2. **Stereotypes**: استخدام `<<extends>>`, `<<enumeration>>`
3. **Multiplicity**: 
   - `||--o{` : One-to-Many
   - `}o--o{` : Many-to-Many
   - `||--||` : One-to-One
4. **Visibility**: `+` للـ public attributes/methods
5. **Constraints**: موضحة في الملاحظات

### الألوان المستخدمة

- **User Management**: أزرق فاتح (#E3F2FD)
- **Academic Management**: أخضر فاتح (#F1F8E9)
- **Exam Management**: برتقالي فاتح (#FFF3E0)
- **Proctoring System**: وردي فاتح (#FCE4EC)
- **Communication System**: بنفسجي فاتح (#E8EAF6)
- **System Configuration**: رمادي (#F5F5F5)

## العلاقات الرئيسية

### علاقات One-to-Many (1:N)
```
User → Subject (teacher)
User → Group (teacher)
User → Exam (teacher)
User → Question (teacher)
User → StudentExam (student)
Subject → Group
Subject → Exam
Subject → Question
Exam → ExamQuestion
Exam → StudentExam
Exam → ProctorSession
Question → QuestionChoice
Question → ExamQuestion
StudentExam → StudentAnswer
ProctorSession → ProctorSnapshot
```

### علاقات Many-to-Many (N:M)
```
User ↔ Subject (enrolled_students)
User ↔ Group (students)
User ↔ Exam (allowed_students)
```

### علاقات One-to-One (1:1)
```
User ↔ TeacherNotificationSettings
ProctorSession ↔ ProctorAudioStream
```

### علاقات Self-Reference
```
Message → Message (replies)
```

## القيود (Constraints)

### Unique Constraints
1. **ExamQuestion**: `(exam, question)` - سؤال واحد لا يمكن أن يكون في نفس الاختبار مرتين
2. **StudentExam**: `(exam, student)` - طالب واحد لا يمكن أن يحاول نفس الاختبار مرتين
3. **StudentAnswer**: `(attempt, exam_question)` - إجابة واحدة لكل سؤال في كل محاولة
4. **ProctorSession**: `(exam, student)` - جلسة مراقبة واحدة لكل طالب في كل اختبار
5. **Group**: `code` - كود فريد للمجموعة

## الأنواع (Enumerations)

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

## استخدام المخطط في SRS

### Section 3: System Design
- استخدم المخطط لشرح هيكلية قاعدة البيانات
- اشرح العلاقات بين الكيانات
- اشرح التنظيم في Packages

### Section 4: Data Models
- استخدم المخطط كمرجع لكل نموذج بيانات
- اشرح كل حقل وعلاقته
- اشرح القيود والأنواع

### Section 5: System Architecture
- استخدم المخطط لشرح بنية البيانات
- اشرح كيفية تفاعل المكونات
- اشرح تدفقات العمل

### Appendix A: Database Schema
- ضع المخطط كملحق في نهاية الوثيقة
- أضف شرح للـ Packages
- أضف ملاحظات أكاديمية

## كيفية التحديث

عند إضافة نماذج جديدة أو تعديل النماذج الموجودة:

1. حدد Package المناسب للنموذج الجديد
2. أضف النموذج في الملف `.puml` داخل Package المناسب
3. أضف العلاقات مع النماذج الأخرى
4. أضف الملاحظات الأكاديمية إذا لزم الأمر
5. اختبر المخطط باستخدام PlantUML
6. قم بتحديث الملفات التوثيقية

## الأدوات الموصى بها

### لعرض PlantUML:
- [PlantUML Online Server](http://www.plantuml.com/plantuml/uml/)
- VS Code Extension: "PlantUML"
- IntelliJ IDEA: "PlantUML integration"
- Command Line: `plantuml examination_system_class_diagram.puml`

### لعرض Mermaid:
- GitHub (عرض تلقائي)
- VS Code Extension: "Markdown Preview Mermaid Support"
- [Mermaid Live Editor](https://mermaid.live/)

## المراجع

- [UML Class Diagram Specification](https://www.uml-diagrams.org/class-diagrams.html)
- [PlantUML Documentation](https://plantuml.com/)
- [Mermaid Documentation](https://mermaid.js.org/)
- Django Models Documentation

## ملاحظات أكاديمية

1. **التنظيم**: المخطط منظم في Packages منطقية تسهل الفهم والصيانة
2. **المعايير**: يتبع معايير UML القياسية
3. **الوضوح**: العلاقات واضحة ومنظمة
4. **التوثيق**: كل Package موثق بالملاحظات
5. **القيود**: جميع القيود موضحة في الملاحظات
