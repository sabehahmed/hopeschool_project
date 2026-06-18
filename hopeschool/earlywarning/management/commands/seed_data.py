import random
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from earlywarning.models import Student, AbsenceRecord, InterventionPlan
from earlywarning.services import RiskScoringService, AlertService

SCHOOLS = ["Lycée Carthage","Collège Ibn Khaldoun","Lycée Bardo","Collège Montfleury","Lycée Habib Thameur"]
GRADES  = ["6A","6B","7A","7B","8A","8B","9A","9B","10A","10B"]
REGIONS = ["tunis","sfax","sousse","bizerte","ariana","other"]
FNAMES  = ["Amira","Yassine","Fatma","Omar","Leila","Mohamed","Sarra","Khalil","Nour","Amine","Rim","Bilel"]
LNAMES  = ["Ben Ali","Trabelsi","Mahjoub","Chaibi","Nasri","Bouri","Chokri","Ferchichi","Hamdi","Miled"]

class Command(BaseCommand):
    help = "Seed demo data for HopeSchool"

    def handle(self, *args, **options):
        self.stdout.write("Seeding demo data...")
        for g in ['operator','supervisor','admin']:
            Group.objects.get_or_create(name=g)
        users = {}
        for username, password, group, staff in [
            ('operator','operator123','operator',False),
            ('supervisor','supervisor123','supervisor',False),
            ('admin','admin123','admin',True),
        ]:
            u, _ = User.objects.get_or_create(username=username)
            u.set_password(password); u.is_staff = staff; u.save()
            u.groups.set([Group.objects.get(name=group)])
            users[username] = u
            self.stdout.write(f"  User: {username}")

        if Student.objects.count() < 30:
            students = []
            for i in range(40):
                dob = date(random.randint(2007,2013), random.randint(1,12), random.randint(1,28))
                s = Student.objects.create(
                    first_name=random.choice(FNAMES), last_name=random.choice(LNAMES),
                    date_of_birth=dob, school=random.choice(SCHOOLS),
                    grade=random.choice(GRADES), region=random.choice(REGIONS), status='active',
                )
                students.append(s)
            self.stdout.write(f"  {len(students)} students created")
        else:
            students = list(Student.objects.all())

        AbsenceRecord.objects.all().delete()
        today = date.today()
        for s in students:
            count = random.choices([0,2,4,8,12], weights=[2,3,3,1,1])[0]
            used = set()
            for _ in range(count):
                d = today - timedelta(days=random.randint(0,29))
                if d not in used:
                    used.add(d)
                    AbsenceRecord.objects.create(
                        student=s, date=d,
                        justified=random.choice([True,False,False]),
                        recorded_by='operator',
                    )
        self.stdout.write("  Absences seeded")

        sup = users['supervisor']
        service = RiskScoringService()
        for s in students:
            service.compute(s, user=sup)
        AlertService().check_and_create_alerts(students)
        self.stdout.write("  Risk scores computed")

        for s in [x for x in students if x.current_risk_level == 'high'][:5]:
            if not s.interventions.exists():
                InterventionPlan.objects.create(
                    student=s, created_by=sup,
                    description="Schedule family meeting and weekly counseling check-in.",
                    state='active',
                )
        self.stdout.write(self.style.SUCCESS("""
Done! Accounts:  operator/operator123  supervisor/supervisor123  admin/admin123
Visit: http://127.0.0.1:8000/login/
"""))
