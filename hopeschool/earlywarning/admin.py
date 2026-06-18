from django.contrib import admin
from .models import Student, AbsenceRecord, RiskScore, InterventionPlan, Alert, AuditLog


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display  = ['last_name','first_name','school','grade','region','status','recent_absence_count','current_risk_level']
    list_filter   = ['status','region','grade']
    search_fields = ['first_name','last_name','school']


@admin.register(AbsenceRecord)
class AbsenceAdmin(admin.ModelAdmin):
    list_display  = ['student','date','justified','recorded_by']
    list_filter   = ['justified','date']
    search_fields = ['student__first_name','student__last_name']


@admin.register(RiskScore)
class RiskScoreAdmin(admin.ModelAdmin):
    list_display = ['student','level','score','computed_at']
    list_filter  = ['level','computed_at']


@admin.register(InterventionPlan)
class InterventionAdmin(admin.ModelAdmin):
    list_display = ['student','state','created_by','created_at']
    list_filter  = ['state']


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['student','level','resolved','created_at']
    list_filter  = ['level','resolved']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display  = ['timestamp','user','action','related_student','result']
    list_filter   = ['action','result']
    search_fields = ['user__username','detail']
    readonly_fields = ['timestamp']
