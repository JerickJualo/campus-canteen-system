from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django import forms

class LoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'placeholder': 'Enter Username',
        'class': 'form-input',
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': 'Enter Password',
        'class': 'form-input',
    }))

def seed_default_users():
    """Seed default admin and cashier accounts if they do not exist in the database, and verify profile roles."""
    # Seed Admin: admin / admin123
    if not User.objects.filter(username='admin').exists():
        admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@campus.edu',
            password='admin123'
        )
        if hasattr(admin_user, 'profile'):
            admin_user.profile.role = 'admin'
            admin_user.profile.save()
    else:
        admin_user = User.objects.get(username='admin')
        if hasattr(admin_user, 'profile') and admin_user.profile.role != 'admin':
            admin_user.profile.role = 'admin'
            admin_user.profile.save()

    # Seed Cashier: cashier / cashier123
    if not User.objects.filter(username='cashier').exists():
        cashier_user = User.objects.create_user(
            username='cashier',
            email='cashier@campus.edu',
            password='cashier123'
        )
        if hasattr(cashier_user, 'profile'):
            cashier_user.profile.role = 'cashier'
            cashier_user.profile.save()
    else:
        cashier_user = User.objects.get(username='cashier')
        if hasattr(cashier_user, 'profile') and cashier_user.profile.role != 'cashier':
            cashier_user.profile.role = 'cashier'
            cashier_user.profile.save()

def login_view(request):
    # Ensure default users are seeded on loading/posting the login screen
    seed_default_users()
    
    if request.user.is_authenticated:
        role = 'cashier'
        if hasattr(request.user, 'profile'):
            role = request.user.profile.role
            
        if role == 'admin' or request.user.is_staff or request.user.is_superuser:
            return redirect('inventory_dashboard')
        elif role == 'monitor':
            return redirect('monitor_dashboard')
        return redirect('cashier')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                role = 'cashier'
                if hasattr(user, 'profile'):
                    role = user.profile.role
                    
                if role == 'admin' or user.is_staff or user.is_superuser:
                    messages.success(request, f"Welcome back, Admin {user.username}!")
                    return redirect('inventory_dashboard')
                elif role == 'monitor':
                    messages.success(request, f"Welcome back, Monitor {user.username}!")
                    return redirect('monitor_dashboard')
                else:
                    messages.success(request, f"Welcome back, Cashier {user.username}!")
                    return redirect('cashier')
            else:
                messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, "You have logged out successfully.")
    return redirect('login')


from accounts.decorators import admin_required
from accounts.models import UserProfile

class UserCreationForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={
        'placeholder': 'Enter Username',
        'class': 'form-input',
    }))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={
        'placeholder': 'Enter Email (Optional)',
        'class': 'form-input',
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': 'Enter Password',
        'class': 'form-input',
    }))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': 'Confirm Password',
        'class': 'form-input',
    }))
    role = forms.ChoiceField(choices=[('cashier', 'Cashier'), ('monitor', 'Monitor')], widget=forms.Select(attrs={
        'class': 'form-input',
    }))

@admin_required
def manage_users(request):
    """View to allow administrators to list users and create cashier or monitor accounts."""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username'].strip()
            email = form.cleaned_data['email'].strip()
            password = form.cleaned_data['password']
            confirm_password = form.cleaned_data['confirm_password']
            role = form.cleaned_data['role']

            if User.objects.filter(username=username).exists():
                messages.error(request, f"Username '{username}' already exists.")
            elif password != confirm_password:
                messages.error(request, "Passwords do not match.")
            else:
                # Create the user account
                new_user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password
                )
                # Assign role via Profile
                if not hasattr(new_user, 'profile'):
                    UserProfile.objects.create(user=new_user, role=role)
                else:
                    new_user.profile.role = role
                    new_user.profile.save()

                messages.success(request, f"Successfully created user account '{username}' with role '{role.capitalize()}'.")
                return redirect('manage_users')
    else:
        form = UserCreationForm()

    users = User.objects.all().select_related('profile').order_by('-date_joined')
    return render(request, 'accounts/user_management.html', {
        'users': users,
        'form': form,
    })

