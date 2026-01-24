from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()

class SignUpForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': '........',
            'class': 'form-input'
        }),
        label=_('Password'),
        help_text=_('Must contain at least 8 characters')
    )
    full_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'أدخل اسمك الكامل',
            'class': 'form-input'
        }),
        label=_('Full Name')
    )
    
    class Meta:
        model = User
        fields = ('role', 'full_name', 'email', 'password')
        widgets = {
            'email': forms.EmailInput(attrs={
                'placeholder': 'name@example.com',
                'class': 'form-input'
            }),
            'role': forms.RadioSelect(attrs={
                'class': 'hidden-role-input'
            }),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
            if User.objects.filter(username__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError(_('هذا البريد الإلكتروني مسجل بالفعل.'))
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        # Normalize email and use it as username
        email = self.cleaned_data.get('email').lower()
        user.email = email
        user.username = email
        if commit:
            user.save()
        return user
