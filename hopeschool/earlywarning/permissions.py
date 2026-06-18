from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from earlywarning.models import AuditLog
from functools import wraps
from django.shortcuts import redirect


def get_user_role(user):
    if not user.is_authenticated:
        return None
    if user.is_staff or user.groups.filter(name='admin').exists():
        return 'admin'
    if user.groups.filter(name='supervisor').exists():
        return 'supervisor'
    if user.groups.filter(name='operator').exists():
        return 'operator'
    return 'operator'  # default


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            role = get_user_role(request.user)
            if role not in roles:
                AuditLog.log('unauthorized_access', user=request.user,
                             detail=f"Tried to access {request.path} — role={role}",
                             result='blocked', request=request)
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


class RoleRequiredMixin(UserPassesTestMixin):
    allowed_roles = []

    def test_func(self):
        return get_user_role(self.request.user) in self.allowed_roles

    def handle_no_permission(self):
        AuditLog.log('unauthorized_access', user=self.request.user,
                     detail=f"Tried to access {self.request.path}",
                     result='blocked', request=self.request)
        raise PermissionDenied
