from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('checkout', 'Checkout'),
        ('void', 'Void'),
        ('shift', 'Shift'),
        ('inventory', 'Inventory'),
        ('restock', 'Restock'),
        ('user', 'User'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
    )
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES)
    description = models.CharField(max_length=255)
    target = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_action_type_display()}: {self.description}"


def log_activity(user, action_type, description, target=''):
    return ActivityLog.objects.create(
        user=user if getattr(user, 'is_authenticated', False) else None,
        action_type=action_type,
        description=description[:255],
        target=target[:120],
    )
