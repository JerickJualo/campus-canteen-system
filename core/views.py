from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def home(request):
    role = 'cashier'
    if hasattr(request.user, 'profile'):
        role = request.user.profile.role

    is_admin = role == 'admin' or request.user.is_staff or request.user.is_superuser

    return render(request, 'home.html', {
        'role': role,
        'is_admin': is_admin,
    })

@login_required
def developers_view(request):
    return render(request, 'developers.html')
