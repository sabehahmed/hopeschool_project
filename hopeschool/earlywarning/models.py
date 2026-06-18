from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date


# ── Choices ──────────────────────────────────────────────────────────────────

REGION_CHOICES = [
    ('tunis', 'Tunis'), ('sfax', 'Sfax'), ('sousse', 'Sousse'),
    ('bizerte', 'Bizerte'), ('gabes', 'Gabès'), ('ariana', 'Ariana'),
    ('other', 'Other'),
]

STATUS_CHOICES = [
    ('active', 'Active'), ('inactive', 'Inactive'), ('transferred', 'Transferred'),
]

RISK_LEVEL_CHOICES = [
    ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'),
]

INTERVENTION_STATE_CHOICES = [
    ('draft', 'Draft'), ('active', 'Active'),
    ('follow_up', 'Follow-Up'), ('closed', 'Closed'),
]

VALID_TRANSITIONS = {
    'draft': ['active'],
    'active': ['follow_up', 'closed'],
    'follow_up': ['closed'],
    'closed': [],
}

ACTION_CHOICES = [
    ('user_login', 'User Login'),
    ('student_created', 'Student Created'),
    ('student_updated', 'Student Updated'),
    ('student_deleted', 'Student Deleted'),
    ('absence_recorded', 'Absence Recorded'),
    ('risk_computed', 'Risk Computed'),
    ('alert_created', 'Alert Created'),
    ('intervention_created', 'Intervention Created'),
    ('intervention_updated', 'Intervention Updated'),
    ('unauthorized_access', 'Unauthorized Access Attempt'),
    ('reminder_sent', 'Reminder Sent'),
    ('bulk_upload', 'Bulk Upload'),
    ('bulk_upload_failed', 'Bulk Upload Failed'),
    ('report_exported', 'Report Exported'),
]


# ── Models ────────────────────────────────────────────────────────────────────

class Student(models.Model):
    first_name    = models.CharField(max_length=100)
    last_name     = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    school        = models.CharField(max_length=200)
    grade         = models.CharField(max_length=20)
    region        = models.CharField(max_length=50, choices=REGION_CHOICES, default='tunis')
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [models.Index(fields=['school', 'grade']),
                   models.Index(fields=['region'])]

    def clean(self):
        if not self.first_name or not self.first_name.strip():
            raise ValidationError({'first_name': 'First name is required.'})
        if not self.last_name or not self.last_name.strip():
            raise ValidationError({'last_name': 'Last name is required.'})
        if self.date_of_birth and self.date_of_birth > date.today():
            raise ValidationError({'date_of_birth': 'Date of birth cannot be in the future.'})

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.school} — {self.grade})"

    @property
    def age(self):
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def recent_absence_count(self):
        cutoff = date.today() - timezone.timedelta(days=30)
        return self.absences.filter(date__gte=cutoff, justified=False).count()

    @property
    def current_risk_level(self):
        score = self.risk_scores.order_by('-computed_at').first()
        return score.level if score else 'low'


class AbsenceRecord(models.Model):
    student     = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='absences')
    date        = models.DateField()
    justified   = models.BooleanField(default=False)
    notes       = models.TextField(blank=True)
    recorded_by = models.CharField(max_length=150)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'date')
        ordering = ['-date']
        indexes = [models.Index(fields=['student', 'date'])]

    def clean(self):
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'Absence date cannot be in the future.'})

    def __str__(self):
        status = 'justified' if self.justified else 'unjustified'
        return f"{self.student} — {self.date} ({status})"


class RiskScore(models.Model):
    student      = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='risk_scores')
    score        = models.FloatField()
    level        = models.CharField(max_length=10, choices=RISK_LEVEL_CHOICES)
    explanation  = models.TextField()
    computed_at  = models.DateField()
    computed_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-computed_at']

    def clean(self):
        if not (0.0 <= self.score <= 1.0):
            raise ValidationError({'score': 'Score must be between 0 and 1.'})
        if not self.explanation or not self.explanation.strip():
            raise ValidationError({'explanation': 'Explanation is required — no opaque decisions.'})

    def __str__(self):
        return f"{self.student} — {self.level} ({self.score:.2f}) on {self.computed_at}"


class InterventionPlan(models.Model):
    student     = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='interventions')
    created_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='interventions_created')
    description = models.TextField()
    state       = models.CharField(max_length=20, choices=INTERVENTION_STATE_CHOICES, default='draft')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        if self.pk:
            old = InterventionPlan.objects.get(pk=self.pk)
            allowed = VALID_TRANSITIONS.get(old.state, [])
            if self.state != old.state and self.state not in allowed:
                raise ValidationError(
                    {'state': f"Invalid transition: '{old.state}' → '{self.state}'. "
                              f"Allowed: {allowed}"}
                )

    def __str__(self):
        return f"Plan for {self.student} [{self.state}]"


class Alert(models.Model):
    student    = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='alerts')
    level      = models.CharField(max_length=10, choices=RISK_LEVEL_CHOICES)
    message    = models.TextField()
    resolved   = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Alert[{self.level}] — {self.student}"


class AuditLog(models.Model):
    user            = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action          = models.CharField(max_length=50, choices=ACTION_CHOICES)
    related_student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True)
    detail          = models.TextField(blank=True)
    result          = models.CharField(max_length=10, default='success',
                                       choices=[('success','Success'),('failure','Failure'),('blocked','Blocked')])
    timestamp       = models.DateTimeField(auto_now_add=True)
    ip_address      = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.action} by {self.user} — {self.result}"

    @classmethod
    def log(cls, action, user=None, student=None, detail='', result='success', request=None):
        ip = None
        if request:
            x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')
        cls.objects.create(
            action=action, user=user, related_student=student,
            detail=detail, result=result, ip_address=ip
        )
