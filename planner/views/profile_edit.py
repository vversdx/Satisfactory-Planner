from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from ..forms import UserEditForm, ProfileEditForm
from ..models import UserProfile

@login_required
def edit_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        user_form = UserEditForm(request.POST, instance=request.user)
        profile_form = ProfileEditForm(request.POST, request.FILES, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            return redirect('profile')
    else:
        user_form = UserEditForm(instance=request.user)
        profile_form = ProfileEditForm(instance=profile)

    return render(request, 'planner/edit_profile.html', {
        'user_form': user_form,
        'profile_form': profile_form,
    })
