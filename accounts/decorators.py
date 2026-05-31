from django.shortcuts import redirect
from django.contrib import messages

MONITOR_VIEW_ONLY_URLS = {
    'inventory_list',
    'inventory_history',
    'inventory_print_checklist',
    'daily_report',
    'daily_report_by_date',
    'monthly_report',
    'monthly_report_by_month',
    'daily_report_history',
    'monthly_report_history',
    'report_history',
}


def admin_required(view_func):
    """
    Decorator for views that checks if the user is logged in and is an admin
    (i.e., is_staff or is_superuser or profile.role == 'admin').
    - If user is a monitor, redirects to the unified monitor dashboard.
    - Otherwise, redirects cashiers back to cashier panel.
    """
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'/accounts/login/?next={request.path}')
        
        # Check role profile
        role = 'cashier'
        if hasattr(request.user, 'profile'):
            role = request.user.profile.role
            
        if role == 'monitor':
            if request.method != 'GET':
                messages.error(request, "Permission Denied: Monitors cannot perform modifications.")
                return redirect('monitor_dashboard')

            url_name = getattr(getattr(request, 'resolver_match', None), 'url_name', '')
            if url_name not in MONITOR_VIEW_ONLY_URLS:
                messages.warning(request, "As a Monitor, you can only view approved inventory and report pages.")
                return redirect('monitor_dashboard')
            
        elif role != 'admin' and not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "Permission Denied: Only administrators can access this section.")
            return redirect('cashier')
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def cashier_required(view_func):
    """
    Decorator for views that checks if the user is logged in and is a cashier.
    - If user is a monitor, redirects them to monitor dashboard.
    - Admin users are also allowed so they can operate the cashier desk when needed.
    """
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'/accounts/login/?next={request.path}')
            
        role = 'cashier'
        if hasattr(request.user, 'profile'):
            role = request.user.profile.role
            
        if role == 'monitor':
            if request.method != 'GET':
                messages.error(request, "Permission Denied: Monitors cannot perform checkout actions.")
                return redirect('monitor_dashboard')
            return redirect('monitor_dashboard')
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view

