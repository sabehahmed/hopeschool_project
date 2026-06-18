from rest_framework import serializers
from datetime import date
from .models import Student, AbsenceRecord, RiskScore, InterventionPlan, Alert, AuditLog, VALID_TRANSITIONS


class StudentSerializer(serializers.ModelSerializer):
    age                  = serializers.ReadOnlyField()
    recent_absence_count = serializers.ReadOnlyField()
    current_risk_level   = serializers.ReadOnlyField()

    class Meta:
        model  = Student
        fields = ['id','first_name','last_name','date_of_birth','school','grade',
                  'region','status','age','recent_absence_count','current_risk_level',
                  'created_at','updated_at']
        read_only_fields = ['created_at','updated_at']

    def validate_first_name(self, v):
        if not v.strip():
            raise serializers.ValidationError("First name cannot be blank.")
        return v.strip()

    def validate_last_name(self, v):
        if not v.strip():
            raise serializers.ValidationError("Last name cannot be blank.")
        return v.strip()

    def validate_date_of_birth(self, v):
        if v > date.today():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return v


class AbsenceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AbsenceRecord
        fields = ['id','student','date','justified','notes','recorded_by','created_at']
        read_only_fields = ['recorded_by','created_at']

    def validate_date(self, v):
        if v > date.today():
            raise serializers.ValidationError("Absence date cannot be in the future.")
        return v

    def validate(self, data):
        student = data.get('student')
        d       = data.get('date')
        qs      = AbsenceRecord.objects.filter(student=student, date=d)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {'date': f"An absence record already exists for this student on {d}."}
            )
        return data


class RiskScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RiskScore
        fields = ['id','student','score','level','explanation','computed_at','computed_by']
        read_only_fields = ['computed_by']

    def validate_score(self, v):
        if not (0.0 <= v <= 1.0):
            raise serializers.ValidationError("Score must be between 0 and 1.")
        return v

    def validate_explanation(self, v):
        if not v.strip():
            raise serializers.ValidationError("Explanation is required.")
        return v


class InterventionPlanSerializer(serializers.ModelSerializer):
    created_by_username = serializers.SerializerMethodField()

    class Meta:
        model  = InterventionPlan
        fields = ['id','student','created_by','created_by_username','description',
                  'state','created_at','updated_at']
        read_only_fields = ['created_by','created_at','updated_at']

    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else None

    def validate_state(self, v):
        if self.instance:
            old     = self.instance.state
            allowed = VALID_TRANSITIONS.get(old, [])
            if v != old and v not in allowed:
                raise serializers.ValidationError(
                    f"Invalid transition '{old}' → '{v}'. Allowed: {allowed}"
                )
        return v


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Alert
        fields = ['id','student','level','message','resolved','created_at']


class AuditLogSerializer(serializers.ModelSerializer):
    user_username = serializers.SerializerMethodField()

    class Meta:
        model  = AuditLog
        fields = ['id','user','user_username','action','related_student',
                  'detail','result','timestamp','ip_address']

    def get_user_username(self, obj):
        return obj.user.username if obj.user else 'system'
