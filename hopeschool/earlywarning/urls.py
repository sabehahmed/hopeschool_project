from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views, api_views

router = DefaultRouter()
router.register(r'students',      api_views.StudentViewSet,          basename='student')
router.register(r'absences',      api_views.AbsenceRecordViewSet,    basename='absence')
router.register(r'risk-scores',   api_views.RiskScoreViewSet,        basename='riskscore')
router.register(r'interventions', api_views.InterventionPlanViewSet, basename='intervention')
router.register(r'alerts',        api_views.AlertViewSet,            basename='alert')
router.register(r'audit-logs',    api_views.AuditLogViewSet,         basename='auditlog')

urlpatterns = [
    # Auth
    path('login/',  views.login_view,  name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/',           views.dashboard,         name='dashboard'),
    path('supervisor/',          views.supervisor_panel,  name='supervisor_panel'),
    path('admin-config/',        views.admin_config,      name='admin_config'),

    # Students
    path('students/',                    views.student_list,   name='student_list'),
    path('students/create/',             views.student_create, name='student_create'),
    path('students/<int:pk>/',           views.student_detail, name='student_detail'),
    path('students/<int:pk>/edit/',      views.student_edit,   name='student_edit'),
    path('students/<int:pk>/delete/',    views.student_delete, name='student_delete'),

    # Absences
    path('absences/create/',                        views.absence_create,                  name='absence_create'),
    path('students/<int:student_pk>/absences/add/', views.absence_create,                  name='absence_create_for_student'),

    # Risk
    path('students/<int:student_pk>/compute-risk/', views.compute_risk,      name='compute_risk'),
    path('compute-all-risks/',                      views.compute_all_risks, name='compute_all_risks'),

    # Interventions
    path('students/<int:student_pk>/interventions/create/', views.intervention_create, name='intervention_create'),
    path('interventions/<int:pk>/update/',                  views.intervention_update, name='intervention_update'),

    # AI Analysis
    path('students/<int:pk>/ai-analysis/', views.ai_analysis, name='ai_analysis'),

    # Alerts
    path('alerts/<int:pk>/resolve/', views.resolve_alert, name='resolve_alert'),

    # Bulk upload & export
    path('bulk-upload/', views.bulk_upload,    name='bulk_upload'),
    path('export/',      views.export_report,  name='export_report'),

    # API
    path('api/', include((router.urls, 'api'))),
]
