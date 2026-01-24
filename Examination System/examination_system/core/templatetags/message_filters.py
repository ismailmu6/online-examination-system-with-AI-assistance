from django import template
from django.contrib import messages

register = template.Library()


@register.filter
def filter_messages_by_user(message_list, user):
    """
    فلترة الرسائل حسب المستخدم الحالي
    """
    if not user or not message_list:
        return []
    
    filtered = []
    for message in message_list:
        # إذا كانت الرسالة تحتوي على tag للمستخدم، نتحقق منها
        message_user_tag = getattr(message, 'user_tag', None)
        
        # إذا لم يكن هناك tag محدد، نعرض الرسالة للجميع
        if message_user_tag is None:
            filtered.append(message)
        # إذا كان tag يطابق المستخدم الحالي
        elif message_user_tag == user.role or (user.is_staff and message_user_tag == 'admin'):
            filtered.append(message)
    
    return filtered


@register.simple_tag
def get_user_messages(request, user_role=None):
    """
    الحصول على الرسائل المخصصة للمستخدم الحالي
    """
    if not request.user or not request.user.is_authenticated:
        return []
    
    user = request.user
    # استخدام storage للحصول على الرسائل بدون استهلاكها
    storage = messages.get_messages(request)
    
    filtered = []
    for message in storage:
        # الحصول على extra_tags
        extra_tags = getattr(message, 'extra_tags', '') or ''
        
        # إذا لم يكن هناك tag محدد (رسالة عامة)، نعرضها فقط للمستخدم المناسب
        if not extra_tags or 'user:' not in extra_tags:
            # عرض الرسائل العامة فقط إذا كانت user_role مطابقة أو إذا كان المستخدم admin
            if user_role is None:
                filtered.append(message)
            elif user.role == user_role:
                filtered.append(message)
            elif user.is_staff and user_role == 'admin':
                filtered.append(message)
        else:
            # التحقق من tag المستخدم المحدد
            user_tag = f'user:{user.role}'
            admin_tag = 'user:admin'
            
            if user_tag in extra_tags:
                filtered.append(message)
            elif user.is_staff and admin_tag in extra_tags:
                filtered.append(message)
    
    return filtered
