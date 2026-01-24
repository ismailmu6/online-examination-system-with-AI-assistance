/**
 * نظام المراقبة المتقدم للمدرس
 * - استقبال الصوت من الطلاب
 * - عرض Snapshots الحية
 * - التحدث مع الطلاب (فردي أو جماعي)
 */

class ProctorTeacher {
    constructor(examId, csrfToken) {
        this.examId = examId;
        this.csrfToken = csrfToken;
        
        // Student connections (Map: studentId -> connection object)
        this.studentConnections = new Map();
        
        // المدرس audio stream للبث
        this.teacherStream = null;
        this.isBroadcasting = false;
        
        // الطالب المحدد للتحدث الفردي
        this.selectedStudentId = null;
        
        // Timers للـ polling
        this.offerPollTimers = new Map(); // studentId -> timer
        
        console.log('[ProctorTeacher] Initialized for exam:', examId);
    }
    
    /**
     * بدء الاستماع لطالب معين
     * يتم استدعاؤها فقط عند الضغط على زر "استمع"
     */
    async listenToStudent(studentId) {
        if (this.studentConnections.has(studentId)) {
            console.log('[ProctorTeacher] Already listening to student:', studentId);
            return;
        }
        
        try {
            console.log('[ProctorTeacher] Starting to listen to student:', studentId);
            
            // إنشاء peer connection
            const pc = new RTCPeerConnection({
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' },
                    { urls: 'stun:stun1.l.google.com:19302' }
                ]
            });
            
            // استقبال الـ audio stream من الطالب
            pc.ontrack = (event) => {
                console.log('[ProctorTeacher] Received track from student:', studentId);
                
                const audioElement = new Audio();
                audioElement.srcObject = event.streams[0];
                audioElement.play().catch(e => {
                    console.error('[ProctorTeacher] Error playing audio:', e);
                });
                
                // حفظ العنصر الصوتي
                const connection = this.studentConnections.get(studentId);
                if (connection) {
                    connection.audio = audioElement;
                }
            };
            
            // معالجة ICE candidates
            pc.onicecandidate = (event) => {
                if (event.candidate) {
                    this.sendTeacherSignal(studentId, 'ice_candidate', {
                        candidate: event.candidate
                    });
                }
            };
            
            // حفظ الاتصال
            this.studentConnections.set(studentId, {
                pc: pc,
                audio: null,
                isActive: false
            });
            
            // الحصول على offer من الطالب (polling)
            this._pollForOffer(studentId, pc);
            
        } catch (error) {
            console.error('[ProctorTeacher] Error listening to student:', studentId, error);
        }
    }
    
    /**
     * Polling للحصول على offer من الطالب
     */
    async _pollForOffer(studentId, pc) {
        // إيقاف أي polling سابق لهذا الطالب
        if (this.offerPollTimers.has(studentId)) {
            clearTimeout(this.offerPollTimers.get(studentId));
        }
        
        const checkOffer = async () => {
            // التحقق من أن الاتصال لا يزال موجوداً ونشطاً
            if (!this.studentConnections.has(studentId)) {
                this.offerPollTimers.delete(studentId);
                return;
            }
            
            const connection = this.studentConnections.get(studentId);
            if (!connection || !connection.pc) {
                this.offerPollTimers.delete(studentId);
                return;
            }
            
            try {
                const offerData = await this.sendTeacherSignal(studentId, 'get_offer', {});
                
                if (offerData.ok && offerData.offer) {
                    // تعيين remote description
                    await pc.setRemoteDescription(new RTCSessionDescription({
                        type: 'offer',
                        sdp: offerData.offer
                    }));
                    
                    // إنشاء answer
                    const answer = await pc.createAnswer();
                    await pc.setLocalDescription(answer);
                    
                    // إرسال answer للطالب
                    await this.sendTeacherSignal(studentId, 'answer', {
                        sdp: answer.sdp
                    });
                    
                    // تحديث حالة الاتصال
                    connection.isActive = true;
                    
                    // إيقاف polling بعد نجاح الاتصال
                    this.offerPollTimers.delete(studentId);
                    
                    console.log('[ProctorTeacher] Successfully connected to student:', studentId);
                } else {
                    // لم نتلقى offer بعد، نحاول مرة أخرى بعد ثانيتين
                    const timer = setTimeout(checkOffer, 2000);
                    this.offerPollTimers.set(studentId, timer);
                }
            } catch (error) {
                console.error('[ProctorTeacher] Error checking for offer:', error);
                // إعادة المحاولة بعد 3 ثوانٍ
                const timer = setTimeout(checkOffer, 3000);
                this.offerPollTimers.set(studentId, timer);
            }
        };
        
        // بدء polling
        checkOffer();
    }
    
    /**
     * إيقاف الاستماع لطالب
     */
    stopListeningToStudent(studentId) {
        // إيقاف polling
        if (this.offerPollTimers.has(studentId)) {
            clearTimeout(this.offerPollTimers.get(studentId));
            this.offerPollTimers.delete(studentId);
        }
        
        const connection = this.studentConnections.get(studentId);
        if (connection) {
            if (connection.pc) {
                connection.pc.close();
            }
            if (connection.audio) {
                connection.audio.pause();
                connection.audio.srcObject = null;
            }
            this.studentConnections.delete(studentId);
            console.log('[ProctorTeacher] Stopped listening to student:', studentId);
        }
    }
    
    /**
     * الاستماع لجميع الطلاب (معطّل - نستمع لطالب واحد فقط)
     */
    async listenToAllStudents(studentIds) {
        console.log('[ProctorTeacher] Auto-listen disabled. Use individual listen buttons.');
        // لا نستمع تلقائياً لجميع الطلاب
        // المدرس يختار يدوياً من يريد الاستماع له
    }
    
    /**
     * الحصول على Snapshots لطالب
     */
    async getStudentSnapshots(studentId) {
        try {
            const response = await fetch(`/proctor/${this.examId}/teacher/snapshots/${studentId}/`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                },
            });
            
            const data = await response.json();
            return data;
            
        } catch (error) {
            console.error('[ProctorTeacher] Error getting snapshots:', error);
            return null;
        }
    }
    
    /**
     * بدء البث الصوتي للطلاب (جماعي أو فردي)
     */
    async startBroadcast(targetStudentId = null) {
        try {
            if (!this.teacherStream) {
                // طلب الميكروفون
                this.teacherStream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });
                console.log('[ProctorTeacher] Microphone access granted');
            }
            
            this.isBroadcasting = true;
            this.selectedStudentId = targetStudentId;
            
            // إرسال إشعار للطلاب أن المدرس بدأ البث
            try {
                await fetch(`/teacher-dashboard/exams/${this.examId}/monitor/notify/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: new URLSearchParams({
                        'message': targetStudentId 
                            ? '🎤 المدرس يتحدث معك الآن - استمع جيداً'
                            : '🎤 المدرس يتحدث للجميع - استمع جيداً'
                    })
                });
            } catch (error) {
                console.error('[ProctorTeacher] Error sending notification:', error);
            }
            
            if (targetStudentId) {
                console.log('[ProctorTeacher] Broadcasting to student:', targetStudentId);
                // بث لطالب واحد فقط
                await this.sendAudioToStudent(targetStudentId);
            } else {
                console.log('[ProctorTeacher] Broadcasting to all students (announcement only)');
                // بث إعلان لجميع الطلاب (بدون إنشاء اتصالات صوتية)
                // الإشعار سيصل عبر نظام الإشعارات
            }
            
            return true;
            
        } catch (error) {
            console.error('[ProctorTeacher] Error starting broadcast:', error);
            alert('فشل في الوصول للميكروفون. يرجى السماح بالوصول للميكروفون من إعدادات المتصفح.');
            return false;
        }
    }
    
    /**
     * إرسال الصوت لطالب محدد
     */
    async sendAudioToStudent(studentId) {
        try {
            const connection = this.studentConnections.get(studentId);
            if (!connection || !connection.pc) {
                console.warn('[ProctorTeacher] No connection for student:', studentId);
                return;
            }
            
            // إضافة audio track من المدرس
            const audioTrack = this.teacherStream.getAudioTracks()[0];
            const sender = connection.pc.getSenders().find(s => s.track && s.track.kind === 'audio');
            
            if (sender) {
                // استبدال المسار الحالي
                await sender.replaceTrack(audioTrack);
            } else {
                // إضافة مسار جديد
                connection.pc.addTrack(audioTrack, this.teacherStream);
            }
            
            console.log('[ProctorTeacher] Audio sent to student:', studentId);
            
        } catch (error) {
            console.error('[ProctorTeacher] Error sending audio to student:', studentId, error);
        }
    }
    
    /**
     * إيقاف البث الصوتي
     */
    async stopBroadcast() {
        // إزالة audio track من جميع الاتصالات
        for (const [studentId, connection] of this.studentConnections) {
            if (connection.pc) {
                const senders = connection.pc.getSenders();
                senders.forEach(sender => {
                    if (sender.track && sender.track.kind === 'audio') {
                        connection.pc.removeTrack(sender);
                    }
                });
            }
        }
        
        if (this.teacherStream) {
            this.teacherStream.getTracks().forEach(track => track.stop());
            this.teacherStream = null;
        }
        
        this.isBroadcasting = false;
        this.selectedStudentId = null;
        
        // إرسال إشعار للطلاب أن المدرس أوقف البث
        try {
            await fetch(`/teacher-dashboard/exams/${this.examId}/monitor/notify/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': this.csrfToken,
                },
                body: new URLSearchParams({
                    'message': '🔇 المدرس أنهى التحدث'
                })
            });
        } catch (error) {
            console.error('[ProctorTeacher] Error sending stop notification:', error);
        }
        
        console.log('[ProctorTeacher] Broadcast stopped');
    }
    
    /**
     * إرسال signal للطالب
     */
    async sendTeacherSignal(studentId, type, data) {
        try {
            const response = await fetch(`/proctor/${this.examId}/teacher/signal/${studentId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                },
                body: JSON.stringify({
                    type: type,
                    ...data
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('[ProctorTeacher] Error sending signal:', error);
            return { ok: false, error: error.message };
        }
    }
    
    /**
     * إنهاء جلسة مراقبة طالب
     */
    async endStudentSession(studentId) {
        try {
            const response = await fetch(`/proctor/${this.examId}/teacher/end/${studentId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                },
            });
            
            const data = await response.json();
            if (data.ok) {
                this.stopListeningToStudent(studentId);
                console.log('[ProctorTeacher] Ended session for student:', studentId);
            }
            
        } catch (error) {
            console.error('[ProctorTeacher] Error ending session:', error);
        }
    }
    
    /**
     * تنظيف جميع الاتصالات
     */
    cleanup() {
        console.log('[ProctorTeacher] Cleaning up...');
        
        // إيقاف جميع timers
        for (const [studentId, timer] of this.offerPollTimers) {
            clearTimeout(timer);
        }
        this.offerPollTimers.clear();
        
        // إيقاف جميع اتصالات الطلاب
        for (const [studentId, connection] of this.studentConnections) {
            this.stopListeningToStudent(studentId);
        }
        
        // إيقاف بث المدرس
        this.stopBroadcast();
        
        console.log('[ProctorTeacher] Cleanup complete');
    }
}

// تصدير للاستخدام العام
window.ProctorTeacher = ProctorTeacher;
