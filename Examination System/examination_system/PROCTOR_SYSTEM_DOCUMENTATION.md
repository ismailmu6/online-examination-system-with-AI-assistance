# 📹 نظام المراقبة المتقدم (Advanced Proctor System)

## 📋 نظرة عامة

تم إضافة نظام مراقبة متقدم يشبه Snapchat لمراقبة الطلاب أثناء الاختبار، يتضمن:

1. ✅ **Snapshots تلقائية** من كاميرا الطالب كل 30 ثانية
2. ✅ **صوت مستمر** من الطالب للمدرس (WebRTC)
3. ✅ **تحدث فردي** من المدرس لطالب محدد (قيد التطوير)
4. ✅ **تحدث جماعي** من المدرس لجميع الطلاب (قيد التطوير)

---

## 🏗️ البنية التقنية

### قاعدة البيانات

#### 1. ProctorSession
```python
class ProctorSession(models.Model):
    exam = ForeignKey(Exam)
    student = ForeignKey(User)
    student_exam = ForeignKey(StudentExam)
    
    is_active = BooleanField(default=True)
    camera_enabled = BooleanField(default=False)
    microphone_enabled = BooleanField(default=False)
    
    last_snapshot = ImageField(upload_to="proctor_snapshots/")
    last_snapshot_at = DateTimeField()
    snapshots_count = IntegerField(default=0)
    warnings_count = IntegerField(default=0)
    
    peer_connection_data = JSONField(default=dict)
    
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    ended_at = DateTimeField(null=True)
```

#### 2. ProctorSnapshot
```python
class ProctorSnapshot(models.Model):
    session = ForeignKey(ProctorSession)
    image = ImageField(upload_to="proctor_snapshots/")
    
    faces_detected = IntegerField(default=0)
    suspicious = BooleanField(default=False)
    notes = TextField(blank=True)
    
    created_at = DateTimeField(auto_now_add=True)
```

#### 3. ProctorAudioStream
```python
class ProctorAudioStream(models.Model):
    class StreamStatus(TextChoices):
        WAITING = "waiting"
        ACTIVE = "active"
        PAUSED = "paused"
        ENDED = "ended"
    
    session = OneToOneField(ProctorSession)
    status = CharField(choices=StreamStatus.choices)
    
    offer_sdp = TextField()  # من الطالب
    answer_sdp = TextField()  # من المدرس
    ice_candidates = JSONField(default=list)
    
    bytes_received = BigIntegerField(default=0)
    packets_lost = IntegerField(default=0)
    
    started_at = DateTimeField()
    last_activity_at = DateTimeField(auto_now=True)
    ended_at = DateTimeField()
```

---

## 🔌 API Endpoints

### للطالب:

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/proctor/<exam_id>/init/` | POST | تهيئة جلسة المراقبة |
| `/proctor/<exam_id>/snapshot/` | POST | رفع snapshot من الكاميرا |
| `/proctor/<exam_id>/signal/` | POST | WebRTC signaling (offer/ICE) |

### للمدرس:

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/proctor/<exam_id>/teacher/signal/<student_id>/` | POST | WebRTC signaling (answer/ICE) |
| `/proctor/<exam_id>/teacher/snapshots/<student_id>/` | GET | الحصول على آخر snapshots |
| `/proctor/<exam_id>/teacher/end/<student_id>/` | POST | إنهاء جلسة المراقبة |

---

## 💻 كيفية العمل

### جانب الطالب

#### 1. بدء نظام المراقبة تلقائياً

عند بدء الاختبار، يتم تحميل `proctor-student.js` تلقائياً:

```javascript
var proctor = new ProctorStudent(examId, csrfToken);
proctor.start();
```

#### 2. طلب أذونات الكاميرا والميكروفون

```javascript
this.localStream = await navigator.mediaDevices.getUserMedia({
    video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        facingMode: 'user'
    },
    audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
    }
});
```

#### 3. التقاط Snapshots تلقائياً

- **أول snapshot:** فوراً عند بدء الاختبار
- **Snapshots متكررة:** كل 30 ثانية
- **الطريقة:**
  1. التقاط صورة من video stream
  2. تحويلها لـ base64
  3. إرسالها عبر POST إلى `/proctor/<exam_id>/snapshot/`

```javascript
captureSnapshot() {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);
    const imageData = canvas.toDataURL('image/jpeg', 0.8);
    await this.uploadSnapshot(imageData);
}
```

#### 4. بث الصوت المستمر (WebRTC)

```javascript
// 1. إنشاء peer connection
this.peerConnection = new RTCPeerConnection({
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' }
    ]
});

// 2. إضافة audio track
const audioTrack = this.localStream.getAudioTracks()[0];
this.peerConnection.addTrack(audioTrack, this.localStream);

// 3. إنشاء offer
const offer = await this.peerConnection.createOffer();
await this.peerConnection.setLocalDescription(offer);

// 4. إرسال offer للسيرفر
await this.sendSignal('offer', { sdp: offer.sdp });

// 5. انتظار answer من المدرس (polling كل 2 ثانية)
this.waitForAnswer();
```

---

### جانب المدرس

#### 1. بدء الاستماع لجميع الطلاب

عند فتح صفحة المراقبة، يتم تحميل `proctor-teacher.js`:

```javascript
var proctor = new ProctorTeacher(examId, csrfToken);

// الاستماع لجميع الطلاب النشطين
proctor.listenToAllStudents(activeStudentIds);
```

#### 2. استقبال الصوت من طالب واحد

```javascript
listenToStudent(studentId) {
    // 1. إنشاء peer connection
    const pc = new RTCPeerConnection({...});
    
    // 2. استقبال audio track
    pc.ontrack = (event) => {
        const audioElement = new Audio();
        audioElement.srcObject = event.streams[0];
        audioElement.play();
    };
    
    // 3. الحصول على offer من الطالب
    const offerData = await this.sendTeacherSignal(studentId, 'get_offer', {});
    
    // 4. إنشاء answer
    await pc.setRemoteDescription(new RTCSessionDescription({
        type: 'offer',
        sdp: offerData.offer
    }));
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    
    // 5. إرسال answer للطالب
    await this.sendTeacherSignal(studentId, 'answer', {
        sdp: answer.sdp
    });
}
```

#### 3. عرض Snapshots الحية

- **التحديث:** كل 10 ثوانٍ
- **العرض:** في بطاقة الطالب (video tile)

```javascript
setInterval(function() {
    activeStudentIds.forEach(function(studentId) {
        proctor.getStudentSnapshots(studentId).then(function(data) {
            if (data && data.ok && data.last_snapshot_url) {
                var img = document.getElementById('snapshot-' + studentId);
                if (img) {
                    img.src = data.last_snapshot_url;
                }
            }
        });
    });
}, 10000);
```

#### 4. التحدث مع الطلاب

**زر "تحدث مع الكل":**
```javascript
broadcastBtn.onclick = function() {
    if (!proctor.isBroadcasting) {
        proctor.startBroadcast(null);  // null = جميع الطلاب
    } else {
        proctor.stopBroadcast();
    }
};
```

**تحدث فردي (قيد التطوير):**
```javascript
proctor.startBroadcast(studentId);  // studentId محدد
```

---

## 🎨 واجهة المستخدم

### للطالب

#### مؤشر المراقبة النشطة
```html
<div class="fixed top-4 left-4 z-50 bg-white p-2 rounded-full shadow-lg border-2 border-red-500">
    <span class="material-symbols-outlined text-red-500 animate-pulse">videocam</span>
</div>
```

- **الموقع:** أعلى يسار الشاشة
- **اللون:** أحمر مع animation نابض
- **الغرض:** تذكير الطالب أن المراقبة نشطة

### للمدرس

#### بطاقة الطالب المحسّنة

```html
<div class="relative aspect-video bg-slate-900 rounded-xl overflow-hidden">
    <!-- Snapshot Image -->
    <img id="snapshot-{{ student_id }}" src="..." class="w-full h-full object-cover"/>
    
    <!-- Audio Indicator -->
    <div class="absolute top-3 left-3 bg-black/60 text-white rounded-lg">
        <span class="material-symbols-rounded text-green-400 animate-pulse">volume_up</span>
        <span class="text-[10px] font-bold">صوت</span>
    </div>
    
    <!-- Camera Indicator -->
    <div class="absolute top-3 left-20 bg-black/60 text-white rounded-lg">
        <span class="material-symbols-rounded text-red-500 animate-pulse">videocam</span>
        <span class="text-[10px] font-bold">كاميرا</span>
    </div>
    
    <!-- Student Info -->
    <div class="absolute bottom-0 inset-x-0 p-3 bg-gradient-to-t from-black/90">
        <div class="font-bold text-sm">{{ student.name }}</div>
        <div class="text-[10px]">
            <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
            <span>نشط الآن</span>
        </div>
    </div>
</div>
```

#### زر التحدث الجماعي

```html
<button id="broadcast-btn" class="px-4 py-2 bg-blue-600 text-white rounded-xl">
    <span class="material-symbols-rounded">campaign</span>
    <span>تحدث مع الكل</span>
</button>
```

---

## 🔒 الأمان والخصوصية

### 1. التحقق من الصلاحيات

```python
# في proctor_init_session
if not exam.allowed_students.filter(id=user.id).exists():
    return JsonResponse({"error": "غير مصرح"}, status=403)

# في proctor_teacher_signal
exam = get_object_or_404(Exam, id=exam_id, teacher=user)
```

### 2. CSRF Protection

جميع الطلبات POST تتطلب CSRF token:
```javascript
headers: {
    'X-CSRFToken': this.csrfToken,
}
```

### 3. تخزين الصور

- **المسار:** `media/proctor_snapshots/YYYY/MM/DD/`
- **التنظيم:** حسب التاريخ لسهولة الإدارة
- **الحجم:** JPEG بجودة 0.8 (متوازن بين الحجم والجودة)

### 4. حذف البيانات

عند حذف الاختبار، يتم حذف:
- جلسات المراقبة (ProctorSession)
- جميع Snapshots (ProctorSnapshot)
- بيانات Audio Stream (ProctorAudioStream)

(Django cascade delete)

---

## 📊 الإحصائيات المتاحة

### في ProctorSession:
- `snapshots_count`: عدد الصور الملتقطة
- `warnings_count`: عدد التحذيرات (للتطوير المستقبلي)
- `created_at` / `updated_at` / `ended_at`: التوقيتات

### في ProctorAudioStream:
- `bytes_received`: حجم البيانات المستلمة
- `packets_lost`: عدد الحزم المفقودة
- `started_at` / `last_activity_at` / `ended_at`: التوقيتات

---

## 🚀 التطوير المستقبلي

### ميزات قيد التطوير:

1. **✨ التحدث الفردي:**
   - إنشاء peer connection منفصل لكل طالب
   - إرسال audio stream من المدرس للطالب المحدد

2. **✨ التحدث الجماعي:**
   - Broadcast audio stream لجميع الطلاب
   - قد يحتاج media server (SFU) للكفاءة

3. **✨ تحليل الصور بالـ AI:**
   - كشف عدد الوجوه (`faces_detected`)
   - كشف السلوك المشبوه (`suspicious`)
   - استخدام OpenCV أو Face Recognition libraries

4. **✨ تسجيل الجلسات:**
   - حفظ audio stream كملف
   - إمكانية المراجعة لاحقاً

5. **✨ جودة الاتصال:**
   - عرض latency, packet loss, bitrate
   - تحذير عند ضعف الاتصال

6. **✨ إشعارات فورية:**
   - تنبيه المدرس عند فقدان اتصال الطالب
   - تنبيه عند كشف أكثر من وجه

---

## 🛠️ متطلبات المتصفح

### الطالب:
- ✅ Chrome/Edge 80+
- ✅ Firefox 75+
- ✅ Safari 14+
- ✅ Opera 67+

### المدرس:
- ✅ نفس المتطلبات

### الميزات المطلوبة:
- `navigator.mediaDevices.getUserMedia()`
- `RTCPeerConnection`
- `canvas.toDataURL()`

### التحقق:
```javascript
if (!ProctorStudent.isSupported()) {
    alert('متصفحك غير مدعوم');
}
```

---

## 📝 ملاحظات مهمة

### 1. Bandwidth
- **Snapshot:** ~50-100 KB كل 30 ثانية = ~3 KB/s
- **Audio:** ~32-64 kbps
- **المجموع لكل طالب:** ~70 KB/s
- **100 طالب:** ~7 MB/s

### 2. Storage
- **Snapshot:** ~50 KB
- **اختبار ساعة واحدة:** 120 صورة = ~6 MB
- **100 طالب:** ~600 MB لكل اختبار

### 3. Privacy Compliance
- ⚠️ يجب إخطار الطلاب بالمراقبة
- ⚠️ يجب الحصول على موافقة صريحة
- ⚠️ يجب حذف البيانات بعد فترة معينة (GDPR)

### 4. الأداء
- استخدام STUN servers مجانية (Google)
- قد تحتاج TURN server للشبكات المعقدة
- الـ polling للـ answer كل 2 ثانية (يمكن تحسينه بـ WebSocket)

---

## 🔧 الصيانة والإدارة

### Django Admin

تم تسجيل جميع النماذج في admin:
```python
@admin.register(ProctorSession)
class ProctorSessionAdmin(admin.ModelAdmin):
    list_display = [
        "id", "student", "exam", "is_active",
        "camera_enabled", "microphone_enabled",
        "snapshots_count", "warnings_count", "created_at"
    ]
```

### الوصول:
`/admin/core/proctorsession/`

### الميزات:
- عرض جميع الجلسات
- تصفية حسب الحالة والتاريخ
- البحث بالطالب أو الاختبار
- عرض الصور المرفوعة

---

## 📞 الدعم والمساعدة

### في حالة المشاكل:

#### 1. الطالب لا يستطيع بدء المراقبة
- تأكد من منح أذونات الكاميرا/الميكروفون
- تحقق من دعم المتصفح
- افتح Console للبحث عن أخطاء

#### 2. المدرس لا يرى الصور
- تأكد من أن الطالب بدأ الاختبار
- انتظر 30 ثانية للـ snapshot الأول
- تحقق من السيرفر logs

#### 3. الصوت لا يعمل
- تأكد من WebRTC signaling يعمل
- تحقق من STUN servers accessible
- قد تحتاج TURN server

### Logs:
```bash
# Django logs
tail -f examination_system/logs/error.log | grep Proctor

# Browser console
# افتح Developer Tools > Console
# ابحث عن [ProctorStudent] أو [ProctorTeacher]
```

---

## ✅ الخلاصة

تم بنجاح إضافة نظام مراقبة متقدم يوفر:
- ✅ مراقبة بصرية عبر Snapshots تلقائية
- ✅ مراقبة صوتية مستمرة
- ✅ واجهة حديثة وسهلة الاستخدام
- ✅ أمان وخصوصية
- ✅ قابلية التوسع والتطوير

**🎉 النظام جاهز للاستخدام!**
