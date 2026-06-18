import pytest
from datetime import date, timedelta
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from earlywarning.models import Student, AbsenceRecord, RiskScore, InterventionPlan, AuditLog


def make_student(**kwargs):
    defaults = dict(
        first_name='Amira', last_name='Ben Ali',
        date_of_birth=date(2010,3,15), school='Lycée Carthage',
        grade='8A', region='tunis', status='active',
    )
    defaults.update(kwargs)
    return Student.objects.create(**defaults)


@pytest.mark.django_db
class TestStudentModel:
    def test_creation(self):
        s = make_student()
        assert s.pk is not None
        assert 'Amira' in str(s)

    def test_future_dob_rejected(self):
        with pytest.raises(ValidationError):
            s = Student(first_name='X', last_name='Y',
                        date_of_birth=date.today()+timedelta(days=1),
                        school='X', grade='1A')
            s.full_clean()

    def test_blank_name_rejected(self):
        with pytest.raises(ValidationError):
            s = Student(first_name='', last_name='', school='X',
                        grade='1A', date_of_birth=date(2010,1,1))
            s.full_clean()

    def test_age_property(self):
        s = make_student(date_of_birth=date(2010,1,1))
        assert s.age >= 14

    def test_recent_absence_count(self):
        s = make_student()
        AbsenceRecord.objects.create(student=s, date=date.today(),
                                      justified=False, recorded_by='op')
        assert s.recent_absence_count == 1


@pytest.mark.django_db
class TestAbsenceModel:
    def test_future_date_rejected(self):
        s = make_student()
        with pytest.raises(ValidationError):
            a = AbsenceRecord(student=s, date=date.today()+timedelta(days=1),
                              justified=False, recorded_by='op')
            a.full_clean()

    def test_duplicate_same_day_blocked(self):
        s = make_student()
        AbsenceRecord.objects.create(student=s, date=date.today(),
                                      justified=False, recorded_by='op')
        with pytest.raises(IntegrityError):
            AbsenceRecord.objects.create(student=s, date=date.today(),
                                          justified=True, recorded_by='op')


@pytest.mark.django_db
class TestRiskScoreModel:
    def test_empty_explanation_rejected(self):
        s = make_student()
        with pytest.raises(ValidationError):
            rs = RiskScore(student=s, score=0.9, level='high',
                           computed_at=date.today(), explanation='')
            rs.full_clean()

    def test_score_out_of_range_rejected(self):
        s = make_student()
        with pytest.raises(ValidationError):
            rs = RiskScore(student=s, score=1.5, level='high',
                           computed_at=date.today(), explanation='Test')
            rs.full_clean()


@pytest.mark.django_db
class TestInterventionStateMachine:
    def test_draft_to_active_allowed(self):
        u = User.objects.create_user('tuser', password='x')
        s = make_student()
        plan = InterventionPlan.objects.create(student=s, created_by=u,
                                                description='Test', state='draft')
        plan.state = 'active'
        plan.full_clean()  # should not raise

    def test_draft_to_closed_blocked(self):
        u = User.objects.create_user('tuser2', password='x')
        s = make_student()
        plan = InterventionPlan.objects.create(student=s, created_by=u,
                                                description='Test', state='draft')
        plan.state = 'closed'
        with pytest.raises(ValidationError):
            plan.full_clean()
