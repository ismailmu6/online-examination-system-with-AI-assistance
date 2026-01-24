# 🚀 دليل النشر والتشغيل - نظام الاختبارات الإلكترونية

**الإصدار:** 1.0.0
**التاريخ:** 2026-01-14

---

## 📋 المحتويات

1. [متطلبات النظام](#متطلبات-النظام)
2. [التثبيت للتطوير](#التثبيت-للتطوير)
3. [التثبيت للإنتاج](#التثبيت-للإنتاج)
4. [الإعدادات](#الإعدادات)
5. [قاعدة البيانات](#قاعدة-البيانات)
6. [اختبار النظام](#اختبار-النظام)
7. [النشر](#النشر)
8. [الصيانة](#الصيانة)

---

## 🔧 متطلبات النظام

### الحد الأدنى:
- **Python:** 3.10 أو أحدث
- **RAM:** 2 GB
- **Storage:** 500 MB
- **OS:** Windows, Linux, macOS

### الموصى به للإنتاج:
- **Python:** 3.12
- **RAM:** 4 GB
- **Storage:** 10 GB SSD
- **CPU:** 2 Cores
- **OS:** Ubuntu 22.04 LTS أو أحدث

---

## 💻 التثبيت للتطوير

### الخطوة 1: تحميل المشروع

```bash
cd examination_system
```

### الخطوة 2: إنشاء بيئة افتراضية

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### الخطوة 3: تثبيت المكتبات

```bash
pip install -r requirements.txt
```

### الخطوة 4: إعداد قاعدة البيانات

```bash
python manage.py migrate
```

### الخطوة 5: إنشاء مستخدم مدير

```bash
python manage.py createsuperuser
```

سيُطلب منك:
- Username
- Email
- Password (يجب أن يكون قوياً)

### الخطوة 6: تشغيل السيرفر

```bash
python manage.py runserver
```

الآن افتح المتصفح على: `http://127.0.0.1:8000/`

---

## 🏭 التثبيت للإنتاج

### الخطوة 1: تحديث النظام

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt upgrade -y
sudo apt install python3.12 python3.12-venv python3-pip postgresql nginx git -y
```

### الخطوة 2: إنشاء مستخدم النظام

```bash
sudo useradd -m -s /bin/bash examapp
sudo su - examapp
```

### الخطوة 3: تحميل المشروع

```bash
git clone <your-repo-url> examination_system
cd examination_system
```

### الخطوة 4: إنشاء بيئة افتراضية

```bash
python3.12 -m venv venv
source venv/bin/activate
```

### الخطوة 5: تثبيت المكتبات

```bash
pip install -r requirements_production.txt
```

### الخطوة 6: إعداد متغيرات البيئة

```bash
cp env.example .env
nano .env
```

**املأ المتغيرات:**
```env
DJANGO_SECRET_KEY=<generate-strong-key>
DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DB_PASSWORD=your-database-password
```

**لتوليد SECRET_KEY:**
```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

### الخطوة 7: إعداد PostgreSQL

```bash
sudo -u postgres psql
```

في PostgreSQL shell:
```sql
CREATE DATABASE examination_system;
CREATE USER examapp WITH PASSWORD 'your-password';
ALTER ROLE examapp SET client_encoding TO 'utf8';
ALTER ROLE examapp SET default_transaction_isolation TO 'read committed';
ALTER ROLE examapp SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE examination_system TO examapp;
\q
```

### الخطوة 8: تطبيق Migrations

```bash
export DJANGO_SETTINGS_MODULE=examination_system.settings_production
python manage.py migrate
```

### الخطوة 9: جمع الملفات الثابتة

```bash
python manage.py collectstatic --noinput
```

### الخطوة 10: إنشاء مستخدم مدير

```bash
python manage.py createsuperuser
```

### الخطوة 11: اختبار التشغيل

```bash
gunicorn examination_system.wsgi:application --bind 127.0.0.1:8000
```

إذا عمل بنجاح، اضغط Ctrl+C للإيقاف.

---

## ⚙️ الإعدادات

### إعدادات التطوير (settings.py)

```python
DEBUG = True
ALLOWED_HOSTS = []
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

### إعدادات الإنتاج (settings_production.py)

```python
DEBUG = False
ALLOWED_HOSTS = ['yourdomain.com']
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'examination_system',
        'USER': 'examapp',
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Security Settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
```

---

## 🗄️ قاعدة البيانات

### SQLite (للتطوير فقط)

**المزايا:**
- ✅ سهل الإعداد
- ✅ لا يحتاج خادم منفصل

**العيوب:**
- ❌ غير مناسب للإنتاج
- ❌ محدود في الأداء

### PostgreSQL (موصى به للإنتاج)

**المزايا:**
- ✅ أداء عالي
- ✅ موثوقية عالية
- ✅ دعم للمعاملات المعقدة

**الإعداد:**
```bash
# Install
sudo apt install postgresql postgresql-contrib

# Start service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database (see Step 7 in Production Installation)
```

### النسخ الاحتياطي

**SQLite:**
```bash
cp db.sqlite3 db.backup.sqlite3
```

**PostgreSQL:**
```bash
pg_dump examination_system > backup.sql

# للاستعادة:
psql examination_system < backup.sql
```

---

## 🧪 اختبار النظام

### فحص النظام

```bash
python manage.py check
python manage.py check --deploy
```

### تشغيل الاختبارات

```bash
python manage.py test
```

### فحص الأمان

```bash
python manage.py check --deploy
```

يجب أن تحصل على:
```
System check identified no issues (0 silenced).
```

---

## 🌐 النشر

### الطريقة 1: Gunicorn + Nginx (موصى به)

#### 1. إنشاء خدمة Systemd

```bash
sudo nano /etc/systemd/system/examapp.service
```

**المحتوى:**
```ini
[Unit]
Description=Examination System Gunicorn daemon
After=network.target

[Service]
User=examapp
Group=www-data
WorkingDirectory=/home/examapp/examination_system
Environment="PATH=/home/examapp/examination_system/venv/bin"
Environment="DJANGO_SETTINGS_MODULE=examination_system.settings_production"
ExecStart=/home/examapp/examination_system/venv/bin/gunicorn \
          --workers 4 \
          --bind unix:/home/examapp/examination_system/examapp.sock \
          examination_system.wsgi:application

[Install]
WantedBy=multi-user.target
```

**تفعيل الخدمة:**
```bash
sudo systemctl start examapp
sudo systemctl enable examapp
sudo systemctl status examapp
```

#### 2. إعداد Nginx

```bash
sudo nano /etc/nginx/sites-available/examapp
```

**المحتوى:**
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location = /favicon.ico { access_log off; log_not_found off; }
    
    location /static/ {
        root /home/examapp/examination_system;
    }

    location /media/ {
        root /home/examapp/examination_system;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/examapp/examination_system/examapp.sock;
    }
}
```

**تفعيل الموقع:**
```bash
sudo ln -s /etc/nginx/sites-available/examapp /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

#### 3. إعداد SSL (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### الطريقة 2: Docker (اختياري)

**قريباً...**

---

## 🔧 الصيانة

### تحديث الكود

```bash
cd /home/examapp/examination_system
source venv/bin/activate
git pull origin main
pip install -r requirements_production.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart examapp
```

### مراقبة الأخطاء

```bash
# عرض آخر 50 سطر من السجل
tail -50 logs/error.log

# متابعة السجل مباشرة
tail -f logs/error.log
```

### إعادة تشغيل الخدمة

```bash
sudo systemctl restart examapp
sudo systemctl restart nginx
```

### فحص حالة الخدمة

```bash
sudo systemctl status examapp
sudo systemctl status nginx
```

### تنظيف الملفات المؤقتة

```bash
python manage.py clearsessions
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -delete
```

---

## 📊 المراقبة

### الأدوات الموصى بها:

1. **Sentry** - لتتبع الأخطاء
2. **New Relic** - لمراقبة الأداء
3. **Uptime Robot** - لمراقبة توفر الموقع
4. **Prometheus + Grafana** - للإحصائيات المفصلة

### مراقبة الموارد

```bash
# CPU and Memory
htop

# Disk space
df -h

# Database size
sudo du -sh /var/lib/postgresql/

# Application size
du -sh /home/examapp/examination_system/
```

---

## 🆘 حل المشاكل

### المشكلة: "502 Bad Gateway"

**الحل:**
```bash
# تحقق من حالة Gunicorn
sudo systemctl status examapp

# تحقق من السجلات
sudo journalctl -u examapp -n 50

# أعد التشغيل
sudo systemctl restart examapp
```

### المشكلة: "Static files not loading"

**الحل:**
```bash
# جمع الملفات الثابتة مرة أخرى
python manage.py collectstatic --noinput

# تحقق من صلاحيات المجلد
ls -la staticfiles/

# إعطاء صلاحيات للمجلد
sudo chown -R examapp:www-data staticfiles/
```

### المشكلة: "Database connection error"

**الحل:**
```bash
# تحقق من حالة PostgreSQL
sudo systemctl status postgresql

# تحقق من الاتصال
psql -U examapp -d examination_system -h localhost

# تحقق من كلمة المرور في .env
cat .env | grep DB_PASSWORD
```

---

## 📚 الموارد الإضافية

### الوثائق:
- [SYSTEM_AUDIT_REPORT.md](SYSTEM_AUDIT_REPORT.md) - تقرير الفحص الشامل
- [COMPREHENSIVE_TEST_REPORT.md](COMPREHENSIVE_TEST_REPORT.md) - تقرير الاختبار الشامل
- [CODE_STATISTICS.md](CODE_STATISTICS.md) - إحصائيات الكود
- [SYSTEM_FEATURES_DOCUMENTATION.md](SYSTEM_FEATURES_DOCUMENTATION.md) - وثائق المميزات

### الدعم:
- **Email:** support@yourdomain.com
- **Documentation:** docs.yourdomain.com

---

## ✅ قائمة التحقق قبل النشر

- [ ] تم تعيين `DEBUG = False`
- [ ] تم تعيين `SECRET_KEY` قوي
- [ ] تم تعيين `ALLOWED_HOSTS`
- [ ] تم إعداد PostgreSQL
- [ ] تم تشغيل `migrate`
- [ ] تم تشغيل `collectstatic`
- [ ] تم إنشاء superuser
- [ ] تم إعداد SSL certificate
- [ ] تم اختبار جميع الوظائف
- [ ] تم إعداد النسخ الاحتياطي
- [ ] تم إعداد المراقبة
- [ ] تم إعداد الـ firewall

---


