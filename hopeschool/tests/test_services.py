import pytest
from datetime import date, timedelta
from django.contrib.auth.models import User
from earlywarning.models import Student, AbsenceRecord, AuditLog
from earlywarning.services import RiskScoringService, AlertService


def make_student(label='S'):
    return Student.objects.create(
        first_name=label, last_name='Test',
        date_of_birth=date(2010,1,1), school='X',
        grade='8A', region='tunis', status='active',
    )


@pytest.mark.django_db
class TestRiskScoringService:
    def test_no_absences_is_low(self):
        s = make_student('NoAbs')
        rs = RiskScoringService().compute(s)
        assert rs.level == 'low'
        assert rs.score == 0.0

    def test_many_unjustified_is_high(self):
        s = make_student('High')
        for i in range(12):
            AbsenceRecord.objects.create(student=s,
                date=date.today()-timedelta(days=i),
                justified=False, recorded_by='op')
        rs = RiskScoringService().compute(s)
        assert rs.level == 'high'
        assert rs.score >= 0.65

    def test_score_in_range(self):
        s = make_student('Range')
        rs = RiskScoringService().compute(s)
        assert 0.0 <= rs.score <= 1.0

    def test_explanation_not_empty(self):
        s = make_student('Expl')
        rs = RiskScoringService().compute(s)
        assert rs.explanation.strip()

    def test_justified_absences_lower_score(self):
        s1 = make_student('Just')
        s2 = make_student('Unjust')
        for i in range(8):
            AbsenceRecord.objects.create(student=s1, date=date.today()-timedelta(days=i),
                                          justified=True, recorded_by='op')
            AbsenceRecord.objects.create(student=s2, date=date.today()-timedelta(days=i),
                                          justified=False, recorded_by='op')
        rs1 = RiskScoringService().compute(s1)
        rs2 = RiskScoringService().compute(s2)
        assert rs1.score < rs2.score

    def test_custom_threshold(self):
        s = make_student('Thresh')
        for i in range(3):
            AbsenceRecord.objects.create(student=s, date=date.today()-timedelta(days=i),
                                          justified=False, recorded_by='op')
        rs = RiskScoringService(high_risk_threshold=0.1).compute(s)
        assert rs.level == 'high'

    def test_audit_log_created(self):
        s = make_student('Audit')
        RiskScoringService().compute(s)
        assert AuditLog.objects.filter(action='risk_computed', related_student=s).exists()


@pytest.mark.django_db
class TestAlertService:
    def test_alert_for_high_risk(self):
        s = make_student('AlertHigh')
        for i in range(12):
            AbsenceRecord.objects.create(student=s, date=date.today()-timedelta(days=i),
                                          justified=False, recorded_by='op')
        RiskScoringService().compute(s)
        alerts = AlertService().check_and_create_alerts([s])
        assert len(alerts) == 1

    def test_no_alert_for_low_risk(self):
        s = make_student('AlertLow')
        RiskScoringService().compute(s)
        alerts = AlertService().check_and_create_alerts([s])
        assert len(alerts) == 0
