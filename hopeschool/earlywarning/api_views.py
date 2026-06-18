from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from datetime import date

from .models import Student, AbsenceRecord, RiskScore, InterventionPlan, Alert, AuditLog
from .serializers import (StudentSerializer, AbsenceRecordSerializer, RiskScoreSerializer,
                           InterventionPlanSerializer, AlertSerializer, AuditLogSerializer)
from .services import RiskScoringService, AlertService, LLMService
from .permissions import get_user_role


class IsOperatorOrAbove(permissions.BasePermission):
    def has_permission(self, request, view):
        return get_user_role(request.user) in ('operator', 'supervisor', 'admin')


class IsSupervisorOrAbove(permissions.BasePermission):
    def has_permission(self, request, view):
        return get_user_role(request.user) in ('supervisor', 'admin')


class IsAdminRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return get_user_role(request.user) == 'admin'


class StudentViewSet(viewsets.ModelViewSet):
    queryset           = Student.objects.all().prefetch_related('risk_scores', 'absences')
    serializer_class   = StudentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAdminRole()]
        return [IsOperatorOrAbove()]

    def get_queryset(self):
        qs = super().get_queryset()
        q  = self.request.query_params.get('q')
        rg = self.request.query_params.get('region')
        st = self.request.query_params.get('status')
        if q:
            qs = qs.filter(Q(first_name__icontains=q)|Q(last_name__icontains=q)|Q(school__icontains=q))
        if rg:
            qs = qs.filter(region=rg)
        if st:
            qs = qs.filter(status=st)
        return qs

    def perform_create(self, serializer):
        student = serializer.save()
        AuditLog.log('student_created', user=self.request.user, student=student,
                     detail=str(student), request=self.request)

    def perform_destroy(self, instance):
        AuditLog.log('student_deleted', user=self.request.user,
                     detail=str(instance), request=self.request)
        instance.delete()

    @action(detail=True, methods=['post'], permission_classes=[IsSupervisorOrAbove])
    def compute_risk(self, request, pk=None):
        student = self.get_object()
        service = RiskScoringService(
            high_risk_threshold=float(request.session.get('high_threshold', 0.65)),
            medium_risk_threshold=float(request.session.get('medium_threshold', 0.35)),
        )
        rs = service.compute(student, user=request.user)
        AlertService().check_and_create_alerts([student])
        return Response(RiskScoreSerializer(rs).data)

    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        student = self.get_object()
        logs    = AuditLog.objects.filter(related_student=student).order_by('-timestamp')[:30]
        data = [{
            'actor':     l.user.username if l.user else 'system',
            'action':    l.action,
            'detail':    l.detail,
            'result':    l.result,
            'timestamp': l.timestamp.isoformat(),
        } for l in logs]
        return Response(data)

    @action(detail=True, methods=['post'], permission_classes=[IsSupervisorOrAbove])
    def close(self, request, pk=None):
        student = self.get_object()
        student.status = 'inactive'
        student.save()
        AuditLog.log('student_updated', user=request.user, student=student,
                     detail='Closed/set inactive', request=request)
        return Response({'status': 'closed'})

    @action(detail=True, methods=['get'], permission_classes=[IsSupervisorOrAbove])
    def recommend(self, request, pk=None):
        """
        LLM-powered personalised intervention plan for the student.
        Falls back gracefully to rule-based plan if API key is missing.
        GET /api/students/{id}/recommend/
        """
        student = self.get_object()
        latest  = student.risk_scores.order_by('-computed_at').first()
        if not latest:
            return Response(
                {'error': 'No risk score found. Run compute_risk first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        llm     = LLMService()
        plan    = llm.generate_intervention_plan(student)
        is_llm  = not plan.get('fallback') and not plan.get('parse_error')

        AuditLog.log(
            'reminder_sent', user=request.user, student=student,
            detail=f"LLM intervention plan generated (llm={is_llm})",
            request=request,
        )

        return Response({
            'student_id':        student.pk,
            'student_name':      str(student),
            'risk_level':        latest.level,
            'risk_score':        latest.score,
            'absence_count_30d': student.recent_absence_count,
            'intervention_plan': plan,
            'generated_by_llm':  is_llm,
        })

    @action(detail=True, methods=['get'], permission_classes=[IsSupervisorOrAbove])
    def narrative(self, request, pk=None):
        """
        LLM-powered narrative profile summary of the student.
        Returns a human-readable paragraph for the supervisor panel.
        GET /api/students/{id}/narrative/
        """
        student  = self.get_object()
        llm      = LLMService()
        text     = llm.generate_narrative(student)
        is_llm   = "[LLM unavailable" not in text

        AuditLog.log(
            'report_exported', user=request.user, student=student,
            detail=f"LLM narrative generated (llm={is_llm})",
            request=request,
        )

        return Response({
            'student_id':       student.pk,
            'student_name':     str(student),
            'risk_level':       student.current_risk_level,
            'narrative':        text,
            'generated_by_llm': is_llm,
        })

    @action(detail=False, methods=['get'], permission_classes=[IsSupervisorOrAbove])
    def alerts_summary(self, request):
        from django.db.models import Count
        alerts = (Alert.objects.filter(resolved=False)
                  .select_related('student')
                  .values('student__id','student__first_name','student__last_name','level')
                  .annotate(cnt=Count('id')))
        return Response(list(alerts))


class AbsenceRecordViewSet(viewsets.ModelViewSet):
    queryset           = AbsenceRecord.objects.select_related('student').all()
    serializer_class   = AbsenceRecordSerializer
    permission_classes = [IsOperatorOrAbove]

    def get_queryset(self):
        qs         = super().get_queryset()
        student_id = self.request.query_params.get('student')
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs

    def perform_create(self, serializer):
        absence = serializer.save(recorded_by=self.request.user.username)
        AuditLog.log('absence_recorded', user=self.request.user, student=absence.student,
                     detail=f"date={absence.date}", request=self.request)


class RiskScoreViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = RiskScore.objects.select_related('student').all()
    serializer_class   = RiskScoreSerializer
    permission_classes = [IsSupervisorOrAbove]


class InterventionPlanViewSet(viewsets.ModelViewSet):
    queryset           = InterventionPlan.objects.select_related('student','created_by').all()
    serializer_class   = InterventionPlanSerializer
    permission_classes = [IsSupervisorOrAbove]

    def perform_create(self, serializer):
        plan = serializer.save(created_by=self.request.user)
        AuditLog.log('intervention_created', user=self.request.user, student=plan.student,
                     detail=f"state={plan.state}", request=self.request)

    def perform_update(self, serializer):
        plan = serializer.save()
        AuditLog.log('intervention_updated', user=self.request.user, student=plan.student,
                     detail=f"state={plan.state}", request=self.request)


class AlertViewSet(viewsets.ModelViewSet):
    queryset           = Alert.objects.select_related('student').all()
    serializer_class   = AlertSerializer
    permission_classes = [IsSupervisorOrAbove]

    @action(detail=False, methods=['get'])
    def dashboard_alerts(self, request):
        alerts = Alert.objects.filter(resolved=False).select_related('student')
        data   = [{'student_id': a.student.pk, 'student_name': str(a.student),
                   'level': a.level, 'message': a.message,
                   'created_at': a.created_at.isoformat()} for a in alerts]
        return Response(data)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = AuditLog.objects.select_related('user','related_student').all()
    serializer_class   = AuditLogSerializer
    permission_classes = [IsSupervisorOrAbove]
