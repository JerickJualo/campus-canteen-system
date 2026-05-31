from django.urls import path
from .views import login_view, logout_view, manage_users

urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('manage/', manage_users, name='manage_users'),
]
