from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile

class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('username',)
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'username': 'Имя пользователя',
        }

class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('avatar', 'bio')
        widgets = {
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'avatar': 'Аватар',
            'bio': 'О себе',
        }
