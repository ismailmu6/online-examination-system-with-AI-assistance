/**
 * نظام المراقبة المتقدم للطالب
 * - التقاط صور تلقائية من الكاميرا (Snapshots)
 * - بث صوتي مستمر للمدرس (WebRTC)
 * 
 * @version 2.0 - إعادة بناء كاملة
 */

class ProctorStudent {
    constructor(examId, csrfToken) {
        // معلومات الجلسة
        this.examId = examId;
        this.csrfToken = csrfToken;
        this.sessionId = null;
        this.audioStreamId = null;
        
        // Media Streams
        this.mediaStream = null;
        this.videoTrack = null;
        this.audioTrack = null;
        
        // WebRTC للصوت
        this.peerConnection = null;
        
        // Timers
        this.snapshotTimer = null;
        this.answerPollTimer = null;
        
        // الإعدادات
        this.config = {
            snapshotInterval: 1000, // ثانية واحدة
            answerPollInterval: 2000, // ثانيتان
            videoConstraints: {
                width: { ideal: 640 },
                height: { ideal: 480 },
                facingMode: 'user'
            },
            audioConstraints: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        };
        
        // الحالة
        this.state = {
            isActive: false,
            hasCamera: false,
            hasMicrophone: false,
            isInitialized: false
        };
        
        console.log('[ProctorStudent] Initialized for exam:', examId);
    }
    
    /**
     * بدء نظام المراقبة
     */
    async start() {
        if (this.state.isActive) {
            console.warn('[ProctorStudent] Already started');
            return;
        }
        
        try {
            console.log('[ProctorStudent] Starting...');
            
            // 1. تهيئة الجلسة
            await this._initSession();
            
            // 2. طلب أذونات الكاميرا والميكروفون
            await this._requestMedia();
            
            // 3. بدء التقاط الصور
            this._startSnapshots();
            
            // 4. بدء البث الصوتي (إذا كان الميكروفون متاحاً)
            if (this.state.hasMicrophone) {
                await this._startAudioStream();
            } else {
                console.log('[ProctorStudent] Microphone not available, skipping audio stream');
            }
            
            this.state.isActive = true;
            console.log('[ProctorStudent] Started successfully');
            
        } catch (error) {
            console.error('[ProctorStudent] Failed to start:', error);
            this._cleanup();
            throw error;
        }
    }
    
    /**
     * إيقاف نظام المراقبة
     */
    stop() {
        console.log('[ProctorStudent] Stopping...');
        this._cleanup();
        this.state.isActive = false;
        console.log('[ProctorStudent] Stopped');
    }
    
    /**
     * تهيئة الجلسة مع السيرفر
     */
    async _initSession() {
        try {
            const response = await fetch(`/proctor/${this.examId}/init/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                },
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }
            
            const data = await response.json();
            
            if (!data.ok) {
                throw new Error(data.error || 'Failed to initialize session');
            }
            
            this.sessionId = data.session_id;
            this.audioStreamId = data.audio_stream_id;
            this.state.isInitialized = true;
            
            console.log('[ProctorStudent] Session initialized:', this.sessionId);
            
        } catch (error) {
            console.error('[ProctorStudent] Session init failed:', error);
            throw new Error(`فشل في تهيئة الجلسة: ${error.message}`);
        }
    }
    
    /**
     * طلب أذونات الكاميرا والميكروفون
     * الميكروفون اختياري - النظام يعمل حتى لو فشل
     */
    async _requestMedia() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('المتصفح لا يدعم الوصول للكاميرا والميكروفون');
        }
        
        console.log('[ProctorStudent] Requesting media permissions...');
        
        // محاولة 1: طلب الكاميرا والميكروفون معاً
        try {
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                video: this.config.videoConstraints,
                audio: this.config.audioConstraints
            });
            
            this._processMediaStream(this.mediaStream);
            this._sendEvent('camera_allowed', 
                this.state.hasMicrophone 
                    ? 'الكاميرا والمايكروفون مفعّلان أثناء الاختبار.'
                    : 'الكاميرا مفعّلة. الميكروفون غير متاح.'
            );
            
            return;
            
        } catch (error) {
            console.warn('[ProctorStudent] Failed to get both, trying video only:', error);
        }
        
        // محاولة 2: طلب الكاميرا فقط
        try {
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                video: this.config.videoConstraints,
                audio: false
            });
            
            this._processMediaStream(this.mediaStream);
            this._sendEvent('camera_allowed', 'الكاميرا مفعّلة. الميكروفون غير متاح.');
            
            return;
            
        } catch (error) {
            console.error('[ProctorStudent] Failed to get video:', error);
            const errorMsg = this._getMediaErrorMessage(error);
            this._sendEvent('camera_denied', errorMsg);
            throw new Error(errorMsg);
        }
    }
    
    /**
     * معالجة Media Stream
     */
    _processMediaStream(stream) {
        if (!stream) {
            throw new Error('فشل في الحصول على stream');
        }
        
        const videoTracks = stream.getVideoTracks();
        const audioTracks = stream.getAudioTracks();
        
        if (videoTracks.length === 0) {
            throw new Error('لا توجد كاميرا متاحة');
        }
        
        this.videoTrack = videoTracks[0];
        this.audioTrack = audioTracks.length > 0 ? audioTracks[0] : null;
        
        this.state.hasCamera = true;
        this.state.hasMicrophone = this.audioTrack !== null;
        
        console.log('[ProctorStudent] Media stream processed:', {
            video: this.state.hasCamera,
            audio: this.state.hasMicrophone
        });
    }
    
    /**
     * الحصول على رسالة خطأ مناسبة
     */
    _getMediaErrorMessage(error) {
        const errorMap = {
            'NotAllowedError': 'تم رفض الوصول. يرجى السماح بالوصول في إعدادات المتصفح.',
            'PermissionDeniedError': 'تم رفض الوصول. يرجى السماح بالوصول في إعدادات المتصفح.',
            'NotFoundError': 'لم يتم العثور على كاميرا متصلة.',
            'DevicesNotFoundError': 'لم يتم العثور على كاميرا متصلة.',
            'NotReadableError': 'الكاميرا مستخدمة من قبل تطبيق آخر.',
            'TrackStartError': 'الكاميرا مستخدمة من قبل تطبيق آخر.'
        };
        
        return errorMap[error.name] || 'فشل في الوصول للكاميرا.';
    }
    
    /**
     * بدء التقاط الصور التلقائية
     */
    _startSnapshots() {
        if (!this.state.hasCamera) {
            console.warn('[ProctorStudent] Cannot start snapshots - no camera');
            return;
        }
        
        // التقاط أول صورة فوراً
        this._captureSnapshot();
        
        // ثم كل فترة محددة
        this.snapshotTimer = setInterval(() => {
            this._captureSnapshot();
        }, this.config.snapshotInterval);
        
        console.log('[ProctorStudent] Snapshot capture started');
    }
    
    /**
     * التقاط صورة من الكاميرا وإرسالها
     */
    async _captureSnapshot() {
        if (!this.state.hasCamera || !this.videoTrack) {
            return;
        }
        
        try {
            // إنشاء video element مؤقت
            const video = document.createElement('video');
            video.srcObject = new MediaStream([this.videoTrack]);
            video.muted = true;
            video.playsInline = true;
            video.autoplay = true;
            
            // انتظار تحميل الفيديو
            await new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('Timeout waiting for video'));
                }, 3000);
                
                video.onloadedmetadata = () => {
                    clearTimeout(timeout);
                    if (video.videoWidth > 0 && video.videoHeight > 0) {
                        resolve();
                    } else {
                        reject(new Error('Invalid video dimensions'));
                    }
                };
                
                video.onerror = (err) => {
                    clearTimeout(timeout);
                    reject(err);
                };
                
                video.play().catch(reject);
            });
            
            // رسم الصورة على canvas
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);
            
            // تحويل لـ base64
            const imageData = canvas.toDataURL('image/jpeg', 0.8);
            
            // تنظيف
            video.srcObject = null;
            
            // إرسال للسيرفر
            await this._uploadSnapshot(imageData);
            
        } catch (error) {
            console.error('[ProctorStudent] Snapshot capture failed:', error);
            // لا نرمي الخطأ - نستمر في المحاولة
        }
    }
    
    /**
     * رفع الصورة للسيرفر
     */
    async _uploadSnapshot(imageData) {
        try {
            const response = await fetch(`/proctor/${this.examId}/snapshot/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                },
                body: JSON.stringify({ image: imageData })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (!data.ok) {
                throw new Error(data.error || 'Upload failed');
            }
            
        } catch (error) {
            console.error('[ProctorStudent] Snapshot upload failed:', error);
            throw error;
        }
    }
    
    /**
     * بدء البث الصوتي (WebRTC)
     */
    async _startAudioStream() {
        if (!this.state.hasMicrophone || !this.audioTrack) {
            return;
        }
        
        try {
            // إنشاء Peer Connection مع إعدادات محسّنة للصوت
            this.peerConnection = new RTCPeerConnection({
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' },
                    { urls: 'stun:stun1.l.google.com:19302' }
                ],
                iceCandidatePoolSize: 10
            });
            
            // إضافة audio track مع إعدادات محسّنة
            const sender = this.peerConnection.addTrack(this.audioTrack, this.mediaStream);
            
            // تحسين إعدادات الصوت
            if (sender && sender.track && sender.track.getSettings) {
                const params = sender.getParameters();
                if (params && params.encodings) {
                    params.encodings[0] = {
                        ...params.encodings[0],
                        maxBitrate: 64000, // 64 kbps للصوت الواضح
                        priority: 'high'
                    };
                    sender.setParameters(params).catch(err => {
                        console.warn('[ProctorStudent] Failed to set audio parameters:', err);
                    });
                }
            }
            
            // معالجة الأحداث
            this.peerConnection.ontrack = (event) => {
                this._handleTeacherAudio(event.streams[0]);
            };
            
            this.peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    this._sendSignal('ice_candidate', { candidate: event.candidate });
                }
            };
            
            // معالجة تغيير حالة الاتصال
            this.peerConnection.onconnectionstatechange = () => {
                console.log('[ProctorStudent] Connection state:', this.peerConnection.connectionState);
                if (this.peerConnection.connectionState === 'failed') {
                    console.warn('[ProctorStudent] Connection failed, attempting to reconnect...');
                    this._reconnectAudioStream();
                }
            };
            
            // إنشاء offer مع إعدادات محسّنة
            const offer = await this.peerConnection.createOffer({
                offerToReceiveAudio: true,
                offerToReceiveVideo: false
            });
            
            // إضافة SDP constraints للصوت
            offer.sdp = this._optimizeAudioSDP(offer.sdp);
            
            await this.peerConnection.setLocalDescription(offer);
            
            // إرسال offer
            await this._sendSignal('offer', { sdp: offer.sdp });
            
            // بدء polling للحصول على answer
            this._pollForAnswer();
            
            console.log('[ProctorStudent] Audio stream started');
            
        } catch (error) {
            console.error('[ProctorStudent] Audio stream failed:', error);
            // لا نرمي الخطأ - النظام يعمل بدون صوت
        }
    }
    
    /**
     * تحسين SDP للصوت
     */
    _optimizeAudioSDP(sdp) {
        // تحسين إعدادات الصوت في SDP
        return sdp
            .replace(/a=fmtp:111/g, 'a=fmtp:111 minptime=10;useinbandfec=1')
            .replace(/a=rtpmap:111 opus\/48000\/2/g, 'a=rtpmap:111 opus/48000/2');
    }
    
    /**
     * إعادة الاتصال بالبث الصوتي
     */
    async _reconnectAudioStream() {
        if (this.peerConnection) {
            this.peerConnection.close();
            this.peerConnection = null;
        }
        
        // إعادة المحاولة بعد ثانية
        setTimeout(() => {
            if (this.state.hasMicrophone && this.audioTrack) {
                this._startAudioStream();
            }
        }, 1000);
    }
    
    /**
     * معالجة صوت المدرس
     */
    _handleTeacherAudio(stream) {
        try {
            const audio = new Audio();
            audio.srcObject = stream;
            audio.play().then(() => {
                console.log('[ProctorStudent] Teacher audio playing');
                this._showNotification('المدرس يتحدث - استمع جيداً!');
            }).catch(error => {
                console.error('[ProctorStudent] Error playing teacher audio:', error);
            });
        } catch (error) {
            console.error('[ProctorStudent] Error handling teacher audio:', error);
        }
    }
    
    /**
     * Polling للحصول على answer من المدرس
     */
    _pollForAnswer() {
        const checkAnswer = async () => {
            if (!this.peerConnection || this.peerConnection.connectionState === 'closed') {
                return;
            }
            
            try {
                const data = await this._sendSignal('get_answer', {});
                
                if (data.ok && data.answer) {
                    const answer = new RTCSessionDescription({
                        type: 'answer',
                        sdp: data.answer
                    });
                    
                    await this.peerConnection.setRemoteDescription(answer);
                    console.log('[ProctorStudent] Received answer from teacher');
                } else {
                    // المحاولة مرة أخرى
                    this.answerPollTimer = setTimeout(checkAnswer, this.config.answerPollInterval);
                }
            } catch (error) {
                console.error('[ProctorStudent] Error checking for answer:', error);
                this.answerPollTimer = setTimeout(checkAnswer, this.config.answerPollInterval * 2);
            }
        };
        
        checkAnswer();
    }
    
    /**
     * إرسال WebRTC signal
     */
    async _sendSignal(type, data) {
        try {
            const response = await fetch(`/proctor/${this.examId}/signal/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                },
                body: JSON.stringify({ type, ...data })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            return await response.json();
            
        } catch (error) {
            console.error('[ProctorStudent] Signal send failed:', error);
            throw error;
        }
    }
    
    /**
     * إرسال حدث للاختبار
     */
    _sendEvent(eventType, message) {
        try {
            const formData = new FormData();
            formData.append('event_type', eventType);
            formData.append('message', message || '');
            
            fetch(`/student-dashboard/exams/${this.examId}/events/`, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': this.csrfToken
                },
                body: formData
            }).catch(error => {
                console.error('[ProctorStudent] Event send failed:', error);
            });
        } catch (error) {
            console.error('[ProctorStudent] Error sending event:', error);
        }
    }
    
    /**
     * إظهار إشعار
     */
    _showNotification(message) {
        const existing = document.getElementById('proctor-notification');
        if (existing) {
            existing.remove();
        }
        
        const notification = document.createElement('div');
        notification.id = 'proctor-notification';
        notification.className = 'fixed top-20 left-1/2 transform -translate-x-1/2 bg-blue-600 text-white px-6 py-3 rounded-xl shadow-2xl z-50 flex items-center gap-3';
        notification.innerHTML = `<span class="material-symbols-rounded text-2xl">volume_up</span><span class="font-bold">${message}</span>`;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }
    
    /**
     * تنظيف الموارد
     */
    _cleanup() {
        // إيقاف timers
        if (this.snapshotTimer) {
            clearInterval(this.snapshotTimer);
            this.snapshotTimer = null;
        }
        
        if (this.answerPollTimer) {
            clearTimeout(this.answerPollTimer);
            this.answerPollTimer = null;
        }
        
        // إغلاق Peer Connection
        if (this.peerConnection) {
            this.peerConnection.close();
            this.peerConnection = null;
        }
        
        // إيقاف Media Tracks
        if (this.videoTrack) {
            this.videoTrack.stop();
            this.videoTrack = null;
        }
        
        if (this.audioTrack) {
            this.audioTrack.stop();
            this.audioTrack = null;
        }
        
        // إيقاف Media Stream
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }
        
        // إعادة تعيين الحالة
        this.state.hasCamera = false;
        this.state.hasMicrophone = false;
        this.state.isInitialized = false;
    }
    
    /**
     * التحقق من دعم المتصفح
     */
    static isSupported() {
        return !!(
            navigator.mediaDevices &&
            navigator.mediaDevices.getUserMedia &&
            window.RTCPeerConnection
        );
    }
}

// تصدير للاستخدام العام
window.ProctorStudent = ProctorStudent;
