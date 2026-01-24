from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.core.mail import send_mail, get_connection
from django.conf import settings
from django.contrib import messages
from django.views.decorators.http import require_POST
from .forms import SignUpForm
import random

User = get_user_model()

def send_verification_email(request, user):
    """Helper function to generate code and send email"""
    # Generate 6-digit code
    verification_code = str(random.randint(100000, 999999))
    
    # Store in session
    request.session['verification_code'] = verification_code
    request.session['verification_user_id'] = user.id
    request.session['verification_email'] = user.email
    
    subject = 'رمز التحقق الخاص بك - منصة الاختبارات الذكية'
    message = f'مرحباً {user.full_name}،\n\nرمز التحقق الخاص بك هو: {verification_code}\n\nاستخدم هذا الرمز لإكمال عملية إنشاء الحساب.\n\nشكراً لك.'
    
    from core.models import SystemSettings
    settings_obj = SystemSettings.load()

    from_email = settings_obj.two_factor_email or settings.DEFAULT_FROM_EMAIL

    try:
        if settings_obj.two_factor_email and settings_obj.two_factor_app_password:
            connection = get_connection(
                host=settings.EMAIL_HOST,
                port=settings.EMAIL_PORT,
                username=settings_obj.two_factor_email,
                password=settings_obj.two_factor_app_password,
                use_tls=settings.EMAIL_USE_TLS,
            )
            send_mail(
                subject,
                message,
                from_email,
                [user.email],
                fail_silently=False,
                connection=connection,
            )
        else:
            send_mail(
                subject,
                message,
                from_email,
                [user.email],
                fail_silently=False,
            )
        # Also print to console for development
        print(f"============================================")
        print(f"EMAIL SENT TO: {user.email}")
        print(f"VERIFICATION CODE: {verification_code}")
        print(f"============================================")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            try:
                user = form.save(commit=False)
                user.is_active = False # Deactivate until verified
                user.save()
                
                send_verification_email(request, user)
                
                return redirect('verify_email')
            except Exception as e:
                form.add_error(None, f"حدث خطأ أثناء إنشاء الحساب: {str(e)}")
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})

def verify_email(request):
    if 'verification_user_id' not in request.session:
        return redirect('signup')
        
    email = request.session.get('verification_email')
    
    if request.method == 'POST':
        otp = request.POST.get('otp')
        stored_code = request.session.get('verification_code')
        
        if otp == stored_code:
            user_id = request.session.get('verification_user_id')
            try:
                user = User.objects.get(id=user_id)
                user.is_active = True
                user.save()

                auth_login(request, user)

                request.session.pop('verification_code', None)
                request.session.pop('verification_user_id', None)
                request.session.pop('verification_email', None)

                if user.is_staff:
                    next_url = 'admin_dashboard'
                elif getattr(user, "role", None) == "teacher":
                    next_url = 'teacher_dashboard'
                elif getattr(user, "role", None) == "student":
                    next_url = 'student_dashboard'
                else:
                    next_url = 'home'

                return redirect(next_url)
            except User.DoesNotExist:
                return redirect('signup')
        else:
            return render(request, 'accounts/verify_2fa.html', {
                'email': email,
                'error': 'رمز التحقق غير صحيح، يرجى المحاولة مرة أخرى.'
            })
            
    return render(request, 'accounts/verify_2fa.html', {'email': email})

def resend_code(request):
    if 'verification_user_id' not in request.session:
        return redirect('signup')
        
    user_id = request.session.get('verification_user_id')
    try:
        user = User.objects.get(id=user_id)
        if send_verification_email(request, user):
            messages.success(request, 'تم إعادة إرسال رمز التحقق بنجاح.')
        else:
            messages.error(request, 'حدث خطأ أثناء إرسال البريد الإلكتروني.')
    except User.DoesNotExist:
        return redirect('signup')
        
    return redirect('verify_email')

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next')
            if not next_url:
                if user.is_staff:
                    next_url = 'admin_dashboard'
                elif getattr(user, "role", None) == "teacher":
                    next_url = 'teacher_dashboard'
                elif getattr(user, "role", None) == "student":
                    next_url = 'student_dashboard'
                else:
                    next_url = 'home'
            return redirect(next_url)
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})

def setup_2fa(request):
    return render(request, 'accounts/setup_2fa.html')

@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect('login')
