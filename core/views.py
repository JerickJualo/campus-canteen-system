from django.core.paginator import Paginator
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from accounts.decorators import admin_required
from .models import ActivityLog

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


@admin_required
def activity_log_view(request):
    logs = ActivityLog.objects.select_related('user')
    action_filter = request.GET.get('action', '').strip()
    search_query = request.GET.get('search', '').strip()

    if action_filter:
        logs = logs.filter(action_type=action_filter)

    if search_query:
        logs = logs.filter(description__icontains=search_query)

    paginator = Paginator(logs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)

    return render(request, 'activity_log.html', {
        'page_obj': page_obj,
        'action_choices': ActivityLog.ACTION_CHOICES,
        'action_filter': action_filter,
        'search_query': search_query,
        'query_params': query_params.urlencode(),
    })
