from django import forms
from earlywarning.models import Student, AbsenceRecord, InterventionPlan

WIDGET_ATTRS = {'class': 'form-control'}
SELECT_ATTRS = {'class': 'form-control form-select'}

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['first_name','last_name','date_of_birth','school','grade','region','status']
        widgets = {
            'first_name':    forms.TextInput(attrs=WIDGET_ATTRS),
            'last_name':     forms.TextInput(attrs=WIDGET_ATTRS),
            'date_of_birth': forms.DateInput(attrs={**WIDGET_ATTRS, 'type':'date'}),
            'school':        forms.TextInput(attrs=WIDGET_ATTRS),
            'grade':         forms.TextInput(attrs=WIDGET_ATTRS),
            'region':        forms.Select(attrs=SELECT_ATTRS),
            'status':        forms.Select(attrs=SELECT_ATTRS),
        }

class AbsenceForm(forms.ModelForm):
    class Meta:
        model = AbsenceRecord
        fields = ['student','date','justified','notes']
        widgets = {
            'student':   forms.Select(attrs=SELECT_ATTRS),
            'date':      forms.DateInput(attrs={**WIDGET_ATTRS, 'type':'date'}),
            'justified': forms.Select(attrs=SELECT_ATTRS, choices=[(True,'Yes — Justified'),(False,'No — Unjustified')]),
            'notes':     forms.Textarea(attrs={**WIDGET_ATTRS, 'rows':3}),
        }

class InterventionForm(forms.ModelForm):
    class Meta:
        model = InterventionPlan
        fields = ['description','state']
        widgets = {
            'description': forms.Textarea(attrs={**WIDGET_ATTRS, 'rows':4}),
            'state':       forms.Select(attrs=SELECT_ATTRS),
        }


class BulkUploadForm(forms.Form):
    csv_file = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'})
    )

class RiskThresholdForm(forms.Form):
    high_threshold   = forms.FloatField(
        min_value=0.0, max_value=1.0,
        widget=forms.NumberInput(attrs={**WIDGET_ATTRS, 'step': '0.01'})
    )
    medium_threshold = forms.FloatField(
        min_value=0.0, max_value=1.0,
        widget=forms.NumberInput(attrs={**WIDGET_ATTRS, 'step': '0.01'})
    )

class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={**WIDGET_ATTRS, 'placeholder': 'Username', 'autofocus': True})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={**WIDGET_ATTRS, 'placeholder': 'Password'})
    )
