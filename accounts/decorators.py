from django.shortcuts import redirect
from django.contrib import messages

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
            # Block modifications (POST/PUT/DELETE)
            if request.method != 'GET':
                messages.error(request, "Permission Denied: Monitors cannot perform modifications.")
                return redirect('monitor_dashboard')
            # Allow viewing of admin report details or list if we want, but since they have monitor dashboard,
            # let's direct them to monitor dashboard for standard admin routes.
            if request.path.startswith('/inventory/') or request.path.startswith('/cashier/reports/'):
                messages.warning(request, "As a Monitor, you are directed to the unified monitoring counter.")
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
    - If user is an admin, redirects them to inventory dashboard.
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
            
        if role == 'admin' or request.user.is_staff or request.user.is_superuser:
            messages.error(request, "Permission Denied: Administrators cannot access the Cashier counter.")
            return redirect('inventory_dashboard')
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view

