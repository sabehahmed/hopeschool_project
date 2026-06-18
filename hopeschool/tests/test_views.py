import pytest
from datetime import date, timedelta
from django.urls import reverse
from django.contrib.auth.models import User, Group
from earlywarning.models import Student, AbsenceRecord, AuditLog


def make_group(name):
    g, _ = Group.objects.get_or_create(name=name)
    return g

def make_user(username, group_name, staff=False):
    u, _ = User.objects.get_or_create(username=username)
    u.set_password('pass1234!'); u.is_staff = staff; u.save()
    u.groups.set([make_group(group_name)])
    return u

def make_student():
    return Student.objects.create(
        first_name='Test', last_name='Student',
        date_of_birth=date(2010,1,1), school='X',
        grade='8A', region='tunis', status='active',
    )


@pytest.mark.django_db
class TestAuthViews:
    def test_login_page_loads(self, client):
        r = client.get(reverse('login'))
        assert r.status_code == 200

    def test_login_valid(self, client):
        make_user('op1', 'operator')
        r = client.post(reverse('login'), {'username':'op1','password':'pass1234!'})
        assert r.status_code == 302

    def test_login_invalid(self, client):
        r = client.post(reverse('login'), {'username':'nobody','password':'wrong'})
        assert r.status_code == 200  # re-renders form

    def test_dashboard_requires_login(self, client):
        r = client.get(reverse('dashboard'))
        assert r.status_code in (302, 403)


@pytest.mark.django_db
class TestPermissions:
    def test_operator_blocked_from_supervisor_panel(self, client):
        make_user('op2','operator')
        client.login(username='op2', password='pass1234!')
        r = client.get(reverse('supervisor_panel'))
        assert r.status_code in (302, 403)
        assert AuditLog.objects.filter(action='unauthorized_access').exists()

    def test_supervisor_can_access_panel(self, client):
        make_user('sup1','supervisor')
        client.login(username='sup1', password='pass1234!')
        r = client.get(reverse('supervisor_panel'))
        assert r.status_code == 200

    def test_operator_blocked_from_delete(self, client):
        make_user('op3','operator')
        s = make_student()
        client.login(username='op3', password='pass1234!')
        r = client.post(reverse('student_delete', kwargs={'pk': s.pk}))
        assert r.status_code in (302, 403)
        assert Student.objects.filter(pk=s.pk).exists()

    def test_admin_can_delete(self, client):
        make_user('adm1','admin', staff=True)
        s = make_student()
        client.login(username='adm1', password='pass1234!')
        r = client.post(reverse('student_delete', kwargs={'pk': s.pk}))
        assert r.status_code in (200, 302)
        assert not Student.objects.filter(pk=s.pk).exists()


@pytest.mark.django_db
class TestStudentViews:
    def test_create_student_valid(self, client):
        make_user('op4','operator')
        client.login(username='op4', password='pass1234!')
        r = client.post(reverse('student_create'), {
            'first_name':'Fatma','last_name':'Chaibi',
            'date_of_birth':'2011-05-10','school':'Lycée Bardo',
            'grade':'7C','region':'tunis','status':'active',
        })
        assert r.status_code in (200, 302)
        assert Student.objects.filter(first_name='Fatma').exists()

    def test_create_student_invalid_future_dob(self, client):
        make_user('op5','operator')
        client.login(username='op5', password='pass1234!')
        r = client.post(reverse('student_create'), {
            'first_name':'Bad','last_name':'Kid',
            'date_of_birth':'2099-01-01','school':'X','grade':'1A',
            'region':'tunis','status':'active',
        })
        assert r.status_code == 200
        assert not Student.objects.filter(date_of_birth='2099-01-01').exists()

    def test_student_list_accessible(self, client):
        make_user('op6','operator')
        client.login(username='op6', password='pass1234!')
        r = client.get(reverse('student_list'))
        assert r.status_code == 200


@pytest.mark.django_db
class TestBulkUpload:
    def test_valid_csv_creates_students(self, client, tmp_path):
        make_user('op7','operator')
        client.login(username='op7', password='pass1234!')
        csv_content = (
            "first_name,last_name,date_of_birth,school,grade,region,status\n"
            "Omar,Nasri,2011-03-10,Lycée Test,8A,tunis,active\n"
            "Nour,Hamdi,2012-07-22,Collège Ariana,7B,ariana,active\n"
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("students.csv", csv_content.encode(), content_type="text/csv")
        r = client.post(reverse('bulk_upload'), {'csv_file': f})
        assert Student.objects.filter(first_name='Omar').exists()
        assert Student.objects.filter(first_name='Nour').exists()

    def test_malformed_csv_rejected(self, client):
        make_user('op8','operator')
        client.login(username='op8', password='pass1234!')
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("bad.csv", b"not,valid,headers\n???,!!,@@",
                               content_type="text/csv")
        r = client.post(reverse('bulk_upload'), {'csv_file': f})
        assert r.status_code == 200
        assert not Student.objects.filter(first_name='???').exists()
        assert AuditLog.objects.filter(action='bulk_upload_failed').exists()
