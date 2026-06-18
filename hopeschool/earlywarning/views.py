import csv
import io
import json
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from .models import Student, AbsenceRecord, RiskScore, InterventionPlan, Alert, AuditLog
from .forms import (StudentForm, AbsenceForm, InterventionForm,
                    BulkUploadForm, RiskThresholdForm, LoginForm)
from .services import RiskScoringService, AlertService
from .permissions import role_required, get_user_role


# ── Auth ──────────────────────────────────────────────────────────────────────

# ✅ NOUVEAU — remplace par ça
def login_view(request):
    from django.contrib.auth.forms import AuthenticationForm
    form = AuthenticationForm(request, data=request.POST or None)
    if form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect('dashboard')
    return render(request, 'earlywarning/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    role = get_user_role(request.user)
    today = date.today()
    cutoff = today - timedelta(days=30)

    total_students  = Student.objects.filter(status='active').count()
    high_risk       = Student.objects.filter(risk_scores__level='high',
                                              risk_scores__computed_at=today).distinct().count()
    medium_risk     = Student.objects.filter(risk_scores__level='medium',
                                              risk_scores__computed_at=today).distinct().count()
    open_alerts     = Alert.objects.filter(resolved=False).count()
    open_interventions = InterventionPlan.objects.exclude(state='closed').count()

    recent_absences = (
        AbsenceRecord.objects
        .filter(date__gte=cutoff, justified=False)
        .select_related('student')
        .order_by('-date')[:10]
    )
    recent_alerts = Alert.objects.filter(resolved=False).select_related('student')[:8]

    # Chart data — absences per day last 14 days
    chart_labels, chart_data = [], []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        cnt = AbsenceRecord.objects.filter(date=d, justified=False).count()
        chart_labels.append(d.strftime('%d %b'))
        chart_data.append(cnt)

    context = {
        'role': role,
        'total_students': total_students,
        'high_risk': high_risk,
        'medium_risk': medium_risk,
        'open_alerts': open_alerts,
        'open_interventions': open_interventions,
        'recent_absences': recent_absences,
        'recent_alerts': recent_alerts,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'earlywarning/dashboard.html', context)


# ── Students ──────────────────────────────────────────────────────────────────

@login_required
def student_list(request):
    role = get_user_role(request.user)
    qs = Student.objects.all().prefetch_related('risk_scores', 'absences', 'alerts')

    q      = request.GET.get('q', '')
    region = request.GET.get('region', '')
    risk   = request.GET.get('risk', '')
    status = request.GET.get('status', '')

    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(school__icontains=q))
    if region:
        qs = qs.filter(region=region)
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 20)
    page      = paginator.get_page(request.GET.get('page'))

    from .models import REGION_CHOICES, STATUS_CHOICES
    return render(request, 'earlywarning/student_list.html', {
        'page': page, 'role': role,
        'region_choices': REGION_CHOICES, 'status_choices': STATUS_CHOICES,
        'filters': {'q': q, 'region': region, 'risk': risk, 'status': status},
    })


@login_required
def student_detail(request, pk):
    role    = get_user_role(request.user)
    student = get_object_or_404(Student.objects.prefetch_related(
        'absences', 'risk_scores', 'interventions', 'alerts'), pk=pk)

    absences      = student.absences.all()[:20]
    risk_scores   = student.risk_scores.all()[:5]
    interventions = student.interventions.all()
    timeline      = AuditLog.objects.filter(related_student=student).order_by('-timestamp')[:20]

    return render(request, 'earlywarning/student_detail.html', {
        'student': student, 'role': role,
        'absences': absences, 'risk_scores': risk_scores,
        'interventions': interventions, 'timeline': timeline,
    })


@login_required
@role_required('operator', 'supervisor', 'admin')
def student_create(request):
    form = StudentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        student = form.save()
        AuditLog.log('student_created', user=request.user, student=student,
                     detail=str(student), request=request)
        messages.success(request, f"Student {student} created successfully.")
        return redirect('student_detail', pk=student.pk)
    return render(request, 'earlywarning/student_form.html', {'form': form, 'action': 'Create'})


@login_required
@role_required('operator', 'supervisor', 'admin')
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    form    = StudentForm(request.POST or None, instance=student)
    if request.method == 'POST' and form.is_valid():
        form.save()
        AuditLog.log('student_updated', user=request.user, student=student,
                     detail=str(student), request=request)
        messages.success(request, "Student updated.")
        return redirect('student_detail', pk=student.pk)
    return render(request, 'earlywarning/student_form.html',
                  {'form': form, 'action': 'Edit', 'student': student})


@login_required
@role_required('admin')
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        name = str(student)
        student.delete()
        AuditLog.log('student_deleted', user=request.user,
                     detail=f"Deleted: {name}", request=request)
        messages.success(request, f"{name} deleted.")
        return redirect('student_list')
    return render(request, 'earlywarning/confirm_delete.html', {'object': student})


# ── Absences ──────────────────────────────────────────────────────────────────

@login_required
@role_required('operator', 'supervisor', 'admin')
def absence_create(request, student_pk=None):
    student = get_object_or_404(Student, pk=student_pk) if student_pk else None
    initial = {'student': student} if student else {}
    form    = AbsenceForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        absence = form.save(commit=False)
        absence.recorded_by = request.user.username
        absence.save()
        AuditLog.log('absence_recorded', user=request.user, student=absence.student,
                     detail=f"date={absence.date} justified={absence.justified}", request=request)
        messages.success(request, "Absence recorded.")
        return redirect('student_detail', pk=absence.student.pk)
    return render(request, 'earlywarning/absence_form.html', {'form': form, 'student': student})


# ── Risk Scoring ──────────────────────────────────────────────────────────────

@login_required
@role_required('supervisor', 'admin')
def compute_risk(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk)
    service = RiskScoringService(
        high_risk_threshold=float(request.session.get('high_threshold', 0.65)),
        medium_risk_threshold=float(request.session.get('medium_threshold', 0.35)),
    )
    rs = service.compute(student, user=request.user)
    AlertService().check_and_create_alerts([student])
    messages.success(request, f"Risk computed: {rs.level.upper()} ({rs.score:.2f})")
    return redirect('student_detail', pk=student.pk)


@login_required
@role_required('supervisor', 'admin')
def compute_all_risks(request):
    students = Student.objects.filter(status='active')
    service  = RiskScoringService(
        high_risk_threshold=float(request.session.get('high_threshold', 0.65)),
        medium_risk_threshold=float(request.session.get('medium_threshold', 0.35)),
    )
    scores = service.compute_bulk(students, user=request.user)
    AlertService().check_and_create_alerts(list(students))
    messages.success(request, f"Risk computed for {len(scores)} students.")
    return redirect('dashboard')


# ── Supervisor Panel ──────────────────────────────────────────────────────────

@login_required
@role_required('supervisor', 'admin')
def supervisor_panel(request):
    role     = get_user_role(request.user)
    form     = RiskThresholdForm(request.POST or None, initial={
        'high_threshold':   request.session.get('high_threshold', 0.65),
        'medium_threshold': request.session.get('medium_threshold', 0.35),
    })
    if request.method == 'POST' and form.is_valid():
        request.session['high_threshold']   = form.cleaned_data['high_threshold']
        request.session['medium_threshold'] = form.cleaned_data['medium_threshold']
        messages.success(request, "Risk thresholds updated.")
        return redirect('supervisor_panel')

    high_risk_students = (
        Student.objects.filter(risk_scores__level='high')
        .distinct().select_related()
        .prefetch_related('risk_scores', 'interventions')[:20]
    )
    open_plans = InterventionPlan.objects.exclude(state='closed').select_related('student', 'created_by')[:20]
    audit_log  = AuditLog.objects.all().select_related('user', 'related_student')[:30]

    return render(request, 'earlywarning/supervisor_panel.html', {
        'role': role, 'form': form,
        'high_risk_students': high_risk_students,
        'open_plans': open_plans, 'audit_log': audit_log,
    })


# ── Interventions ─────────────────────────────────────────────────────────────

@login_required
@role_required('supervisor', 'admin')
def intervention_create(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk)
    form    = InterventionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        plan = form.save(commit=False)
        plan.student    = student
        plan.created_by = request.user
        plan.save()
        AuditLog.log('intervention_created', user=request.user, student=student,
                     detail=f"state={plan.state}", request=request)
        messages.success(request, "Intervention plan created.")
        return redirect('student_detail', pk=student.pk)
    return render(request, 'earlywarning/intervention_form.html',
                  {'form': form, 'student': student, 'action': 'Create'})


@login_required
@role_required('supervisor', 'admin')
def intervention_update(request, pk):
    plan    = get_object_or_404(InterventionPlan, pk=pk)
    old_state = plan.state
    form    = InterventionForm(request.POST or None, instance=plan)
    if request.method == 'POST' and form.is_valid():
        try:
            updated = form.save(commit=False)
            updated.full_clean()
            updated.save()
            AuditLog.log('intervention_updated', user=request.user, student=plan.student,
                         detail=f"state: {old_state} → {updated.state}", request=request)
            messages.success(request, f"Intervention updated: {old_state} → {updated.state}")
            return redirect('student_detail', pk=plan.student.pk)
        except Exception as e:
            messages.error(request, str(e))
    return render(request, 'earlywarning/intervention_form.html',
                  {'form': form, 'student': plan.student, 'action': 'Update', 'plan': plan})


# ── Admin Config ──────────────────────────────────────────────────────────────

@login_required
@role_required('admin')
def admin_config(request):
    role      = get_user_role(request.user)
    all_logs  = AuditLog.objects.select_related('user', 'related_student')[:50]
    all_users = __import__('django.contrib.auth.models', fromlist=['User']).User.objects.all()
    return render(request, 'earlywarning/admin_config.html',
                  {'role': role, 'all_logs': all_logs, 'all_users': all_users})


# ── Bulk Upload ───────────────────────────────────────────────────────────────

@login_required
@role_required('operator', 'supervisor', 'admin')
def bulk_upload(request):
    form    = BulkUploadForm(request.POST or None, request.FILES or None)
    results = None
    if request.method == 'POST' and form.is_valid():
        csv_file = request.FILES['csv_file']
        try:
            decoded  = csv_file.read().decode('utf-8')
            reader   = csv.DictReader(io.StringIO(decoded))
            required = {'first_name', 'last_name', 'date_of_birth', 'school', 'grade', 'region', 'status'}

            if not required.issubset(set(reader.fieldnames or [])):
                missing = required - set(reader.fieldnames or [])
                AuditLog.log('bulk_upload_failed', user=request.user,
                             detail=f"Missing columns: {missing}", result='failure', request=request)
                messages.error(request, f"CSV missing required columns: {missing}")
                return render(request, 'earlywarning/bulk_upload.html', {'form': form})

            created, errors = 0, []
            for i, row in enumerate(reader, start=2):
                try:
                    dob = date.fromisoformat(row['date_of_birth'].strip())
                    s   = Student(
                        first_name=row['first_name'].strip(),
                        last_name=row['last_name'].strip(),
                        date_of_birth=dob,
                        school=row['school'].strip(),
                        grade=row['grade'].strip(),
                        region=row.get('region', 'other').strip().lower(),
                        status=row.get('status', 'active').strip().lower(),
                    )
                    s.full_clean()
                    s.save()
                    created += 1
                except Exception as e:
                    errors.append(f"Row {i}: {e}")

            AuditLog.log('bulk_upload', user=request.user,
                         detail=f"created={created} errors={len(errors)}", request=request)
            results = {'created': created, 'errors': errors}
            messages.success(request, f"Bulk upload complete: {created} students created, {len(errors)} error(s).")
        except Exception as e:
            AuditLog.log('bulk_upload_failed', user=request.user,
                         detail=str(e), result='failure', request=request)
            messages.error(request, f"Failed to parse CSV: {e}")

    return render(request, 'earlywarning/bulk_upload.html', {'form': form, 'results': results})


# ── Export ────────────────────────────────────────────────────────────────────

@login_required
@role_required('supervisor', 'admin')
def export_report(request):
    region = request.GET.get('region', '')
    risk   = request.GET.get('risk', '')

    qs = Student.objects.prefetch_related('risk_scores', 'absences').filter(status='active')
    if region:
        qs = qs.filter(region=region)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="hopeschool_report.csv"'
    writer   = csv.writer(response)
    writer.writerow(['ID', 'Last Name', 'First Name', 'School', 'Grade', 'Region',
                     'Age', 'Absences (30d)', 'Risk Level', 'Risk Score', 'Risk Explanation'])
    for s in qs:
        latest = s.risk_scores.order_by('-computed_at').first()
        writer.writerow([
            s.pk, s.last_name, s.first_name, s.school, s.grade, s.region,
            s.age, s.recent_absence_count,
            latest.level if latest else 'N/A',
            f"{latest.score:.2f}" if latest else 'N/A',
            latest.explanation if latest else 'Not computed',
        ])
    AuditLog.log('report_exported', user=request.user,
                 detail=f"filters: region={region} risk={risk}", request=request)
    return response


# ── Alerts ────────────────────────────────────────────────────────────────────

@login_required
@role_required('supervisor', 'admin')
@require_POST
def resolve_alert(request, pk):
    alert = get_object_or_404(Alert, pk=pk)
    alert.resolved = True
    alert.save()
    messages.success(request, "Alert resolved.")
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


# ── AI Analysis ───────────────────────────────────────────────────────────────

@login_required
@role_required('supervisor', 'admin')
def ai_analysis(request, pk):
    from earlywarning.services import LLMService
    student = get_object_or_404(Student, pk=pk)
    latest  = student.risk_scores.order_by('-computed_at').first()

    if not latest:
        messages.error(request, "Please compute a risk score first before running AI analysis.")
        return redirect('student_detail', pk=pk)

    llm       = LLMService()
    narrative = llm.generate_narrative(student)
    plan      = llm.generate_intervention_plan(student)
    is_llm    = not plan.get('fallback') and not plan.get('parse_error')

    AuditLog.log('risk_computed', user=request.user, student=student,
                 detail=f"AI analysis viewed (llm={is_llm})", request=request)

    return render(request, 'earlywarning/ai_analysis.html', {
        'student':   student,
        'narrative': narrative,
        'plan':      plan,
        'is_llm':    is_llm,
        'latest':    latest,
    })
