"""
Example Django models for ProxmoxMCP authentication.

These models should be integrated into your Django application's auth app.
"""

import hashlib
from datetime import datetime
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserRole(models.Model):
    """
    User role model for RBAC.
    """
    name = models.CharField(max_length=50, unique=True)
    is_superuser = models.BooleanField(default=False)
    can_write = models.BooleanField(default=False)
    can_admin = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'auth_user_roles'
        verbose_name = 'User Role'
        verbose_name_plural = 'User Roles'


class ApplicationToken(models.Model):
    """
    API tokens for ProxmoxMCP access.
    """
    PERMISSION_CHOICES = [
        ('read', 'Read Only'),
        ('write', 'Read & Write'),
        ('admin', 'Administrator'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_tokens')
    name = models.CharField(max_length=100)
    token_hash = models.CharField(max_length=128, unique=True, db_index=True)
    permission = models.CharField(max_length=10, choices=PERMISSION_CHOICES, default='read')
    
    # Optional expiration
    expires = models.DateTimeField(null=True, blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # IP restrictions (optional)
    allowed_ips = models.TextField(
        blank=True, 
        help_text="Comma-separated list of allowed IP addresses/ranges"
    )
    
    def save(self, *args, **kwargs):
        # Auto-hash the token if it's not already hashed
        if self.token_hash and len(self.token_hash) != 128:
            self.token_hash = self.hash_token(self.token_hash)
        super().save(*args, **kwargs)
    
    @staticmethod
    def hash_token(token):
        """Hash a token using SHA-512."""
        return hashlib.sha512(token.encode('utf-8')).hexdigest()
    
    @classmethod
    def create_token(cls, user, name, permission='read', expires_days=None):
        """
        Create a new API token for a user.
        
        Args:
            user: Django User instance
            name: Token name/description
            permission: Permission level
            expires_days: Optional expiration in days
            
        Returns:
            Tuple of (ApplicationToken instance, raw_token)
        """
        import secrets
        
        # Generate a secure random token
        raw_token = secrets.token_hex(32)
        token_hash = cls.hash_token(raw_token)
        
        # Set expiration if specified
        expires = None
        if expires_days:
            expires = timezone.now() + timezone.timedelta(days=expires_days)
        
        token = cls.objects.create(
            user=user,
            name=name,
            token_hash=token_hash,
            permission=permission,
            expires=expires
        )
        
        return token, raw_token
    
    def is_expired(self):
        """Check if token is expired."""
        if not self.expires:
            return False
        return timezone.now() > self.expires
    
    def update_last_used(self):
        """Update last used timestamp."""
        self.last_used = timezone.now()
        self.save(update_fields=['last_used'])
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"
    
    class Meta:
        db_table = 'auth_application_tokens'
        verbose_name = 'Application Token'
        verbose_name_plural = 'Application Tokens'
        ordering = ['-created_at']


# Extend User model with role relationship
User.add_to_class(
    'role',
    models.ForeignKey(
        UserRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )
)


# Admin interface (optional)
try:
    from django.contrib import admin
    
    @admin.register(UserRole)
    class UserRoleAdmin(admin.ModelAdmin):
        list_display = ['name', 'is_superuser', 'can_write', 'can_admin', 'created_at']
        list_filter = ['is_superuser', 'can_write', 'can_admin']
        search_fields = ['name', 'description']
        readonly_fields = ['created_at', 'updated_at']
    
    @admin.register(ApplicationToken)
    class ApplicationTokenAdmin(admin.ModelAdmin):
        list_display = ['user', 'name', 'permission', 'is_active', 'expires', 'last_used', 'created_at']
        list_filter = ['permission', 'is_active', 'created_at', 'expires']
        search_fields = ['user__username', 'name']
        readonly_fields = ['token_hash', 'created_at', 'last_used']
        
        fieldsets = (
            ('Basic Information', {
                'fields': ('user', 'name', 'permission')
            }),
            ('Security', {
                'fields': ('token_hash', 'expires', 'is_active', 'allowed_ips')
            }),
            ('Tracking', {
                'fields': ('created_at', 'last_used'),
                'classes': ('collapse',)
            })
        )
        
        def save_model(self, request, obj, form, change):
            if not change:  # Creating new token
                # Generate token and show it to admin
                token, raw_token = ApplicationToken.create_token(
                    user=obj.user,
                    name=obj.name,
                    permission=obj.permission,
                    expires_days=30 if obj.expires else None
                )
                obj.pk = token.pk
                obj.token_hash = token.token_hash
                
                # Store raw token in messages to show to admin
                from django.contrib import messages
                messages.success(
                    request,
                    f"Token created successfully. Raw token (save this): {raw_token}"
                )
            else:
                super().save_model(request, obj, form, change)

except ImportError:
    # Django admin not available
    pass
