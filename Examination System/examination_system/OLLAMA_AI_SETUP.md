# 🤖 دليل إعداد Ollama AI - ميزة توليد الأسئلة التلقائي

**الميزة:** توليد أسئلة اختبار تلقائياً باستخدام الذكاء الاصطناعي

---

## ⚠️ المشكلة الحالية: TimeoutError

إذا واجهت خطأ `TimeoutError at /teacher-dashboard/subjects/XX/question-bank/`، فهذا يعني أن:

1. **Ollama غير مثبت** على جهازك
2. **Ollama غير مشغّل** حالياً
3. **Ollama يستغرق وقتاً طويلاً** للرد

---

## ✅ الحلول المتاحة

### الحل 1: تثبيت وتشغيل Ollama (موصى به)

#### الخطوة 1: تحميل Ollama

**Windows:**
```bash
# قم بتحميل Ollama من الموقع الرسمي:
# https://ollama.ai/download/windows

# أو باستخدام winget:
winget install Ollama.Ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS:**
```bash
brew install ollama
```

#### الخطوة 2: تشغيل Ollama

**Windows:**
```bash
# سيتم تشغيل Ollama تلقائياً كخدمة في الخلفية
# أو يمكنك تشغيله يدوياً:
ollama serve
```

**Linux/macOS:**
```bash
# تشغيل Ollama في الخلفية
ollama serve &

# أو كخدمة systemd (Linux):
sudo systemctl start ollama
sudo systemctl enable ollama
```

#### الخطوة 3: تحميل النموذج

```bash
# تحميل نموذج llama3 (موصى به)
ollama pull llama3

# أو نموذج أخف (إذا كان جهازك بطيئاً):
ollama pull llama3:8b

# أو نموذج أصغر:
ollama pull phi3
```

#### الخطوة 4: اختبار Ollama

```bash
# اختبار بسيط
curl http://localhost:11434/api/version

# يجب أن تحصل على:
# {"version":"0.x.x"}
```

#### الخطوة 5: تعديل إعدادات Django (اختياري)

إذا كنت تستخدم نموذجاً مختلفاً، أضف إلى `settings.py`:

```python
# في examination_system/examination_system/settings.py

# Ollama AI Settings
OLLAMA_BASE_URL = "http://127.0.0.1:11434"  # الافتراضي
OLLAMA_MODEL = "llama3"  # أو "phi3" أو "llama3:8b"
```

---

### الحل 2: تعطيل ميزة AI (مؤقت)

إذا كنت لا تريد استخدام AI، يمكنك:

#### الطريقة 1: عدم استخدام زر "توليد بالذكاء الاصطناعي"

فقط استخدم **"إضافة يدوياً"** في صفحة بنك الأسئلة.

#### الطريقة 2: تعطيل الميزة بالكامل (للمطورين)

أضف إلى `settings.py`:

```python
# Disable AI features
ENABLE_AI_FEATURES = False
```

ثم في `views.py`، أضف شرطاً:

```python
if getattr(settings, 'ENABLE_AI_FEATURES', True):
    # AI code here
    pass
else:
    ai_errors["disabled"] = "ميزة الذكاء الاصطناعي معطلة حالياً."
```

---

### الحل 3: زيادة Timeout (للأجهزة البطيئة)

إذا كان Ollama يعمل لكنه بطيء، عدّل `views.py`:

```python
# في دالة _generate_questions_with_ollama
# السطر ~3837
with urllib.request.urlopen(req, timeout=60) as resp:  # كان 60
    # غيّره إلى 180 (3 دقائق) أو 300 (5 دقائق)
```

**ملاحظة:** هذا قد يجعل الصفحة بطيئة جداً!

---

## 📊 متطلبات النظام لـ Ollama

### الحد الأدنى:
- **RAM:** 8 GB
- **Storage:** 5 GB حرة
- **CPU:** متعدد النوى

### الموصى به:
- **RAM:** 16 GB
- **Storage:** 10 GB SSD
- **GPU:** NVIDIA RTX (اختياري لكن يسرّع كثيراً)
- **CPU:** 4 cores أو أكثر

---

## 🚀 استخدام ميزة AI

بعد إعداد Ollama:

1. افتح صفحة **بنك الأسئلة** لأي مادة
2. اضغط على تبويب **"توليد بالذكاء الاصطناعي"**
3. املأ النموذج:
   - **عدد الأسئلة:** 1-50
   - **نوع الأسئلة:** اختيار من متعدد أو مقالي
   - **مستوى الصعوبة:** سهل، متوسط، صعب، أو متنوع
   - **نص المادة:** انسخ محتوى الدرس هنا
   - **أو ارفع ملف:** PDF, Word, أو Text
4. اضغط **"توليد الأسئلة"**
5. انتظر 30-120 ثانية (حسب قوة جهازك)
6. سيتم إضافة الأسئلة تلقائياً إلى بنك الأسئلة

---

## 🐛 حل المشاكل الشائعة

### المشكلة: "تعذر الاتصال بـ Ollama"

**الحل:**
```bash
# تحقق من أن Ollama يعمل
netstat -an | findstr 11434  # Windows
netstat -an | grep 11434     # Linux/macOS

# إذا لم يظهر شيء، شغّل Ollama:
ollama serve
```

### المشكلة: "انتهت مهلة الانتظار"

**الحلول:**
1. قلّل عدد الأسئلة (جرّب 5 أسئلة أولاً)
2. قلّل طول النص المدخل
3. استخدم نموذجاً أصغر (phi3 بدلاً من llama3)
4. زِد الـ timeout في الكود (انظر الحل 3 أعلاه)

### المشكلة: "الأسئلة المولدة غير جيدة"

**الحلول:**
1. حسّن جودة النص المدخل
2. جرّب نموذجاً أكبر (llama3:70b)
3. عدّل الـ prompt في `_generate_questions_with_ollama`

---

## 🔧 للمطورين: تخصيص AI

### تعديل النموذج:

```python
# في settings.py
OLLAMA_MODEL = "phi3"  # نموذج أسرع
# أو
OLLAMA_MODEL = "llama3:70b"  # نموذج أقوى (يحتاج RAM أكثر)
```

### تعديل الـ Prompt:

عدّل `_generate_questions_with_ollama` في `core/views.py`:

```python
system_prompt = (
    "You are a professional assistant..."
    # أضف تعليماتك المخصصة هنا
)
```

---

## 📚 موارد إضافية

- **موقع Ollama:** https://ollama.ai/
- **قائمة النماذج:** https://ollama.ai/library
- **Documentation:** https://github.com/ollama/ollama

---

## ✅ الخلاصة

**للاستخدام الفوري:**
```bash
# 1. ثبّت Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. شغّل Ollama
ollama serve

# 3. حمّل النموذج
ollama pull llama3

# 4. جرّب النظام
# الآن افتح صفحة بنك الأسئلة واستخدم ميزة AI
```

**إذا لم ترد استخدام AI:**
- فقط استخدم زر **"إضافة يدوياً"** في بنك الأسئلة
- الميزة اختيارية تماماً!

---

**🎉 استمتع بتوليد الأسئلة التلقائي! 🤖**

