"""
Business logic layer — keeps views thin and logic testable.
"""
import os
import json
import urllib.request
import urllib.error
from datetime import date, timedelta
from earlywarning.models import RiskScore, Alert, AuditLog


class RiskScoringService:
    """
    Rule-based, fully explainable risk scoring.
    No black-box decisions — every score comes with a text explanation.
    """

    def __init__(self, high_risk_threshold=0.65, medium_risk_threshold=0.35):
        self.high_threshold   = high_risk_threshold
        self.medium_threshold = medium_risk_threshold

    def compute(self, student, user=None):
        today   = date.today()
        cutoff  = today - timedelta(days=30)
        absences = student.absences.filter(date__gte=cutoff)

        total       = absences.count()
        unjustified = absences.filter(justified=False).count()
        justified   = total - unjustified

        # Score formula: unjustified weight 1.0, justified weight 0.3, max cap at 15
        raw   = (unjustified * 1.0 + justified * 0.3) / 15.0
        score = min(raw, 1.0)

        if score >= self.high_threshold:
            level = 'high'
        elif score >= self.medium_threshold:
            level = 'medium'
        else:
            level = 'low'

        explanation = (
            f"In the last 30 days: {total} total absence(s) — "
            f"{unjustified} unjustified, {justified} justified. "
            f"Weighted score: {score:.2f} (threshold high={self.high_threshold}, "
            f"medium={self.medium_threshold}). Risk level: {level.upper()}."
        )

        rs = RiskScore.objects.create(
            student=student, score=round(score, 4),
            level=level, explanation=explanation,
            computed_at=today, computed_by=user,
        )
        AuditLog.log('risk_computed', user=user, student=student,
                     detail=f"level={level} score={score:.4f}")
        return rs

    def compute_bulk(self, students, user=None):
        return [self.compute(s, user=user) for s in students]


class AlertService:
    """Creates alerts for high/medium risk students."""

    def check_and_create_alerts(self, students):
        created = []
        for student in students:
            latest = student.risk_scores.order_by('-computed_at').first()
            if not latest or latest.level == 'low':
                continue
            # Avoid duplicate alerts on same day
            already = student.alerts.filter(
                resolved=False,
                created_at__date=date.today(),
            ).exists()
            if already:
                continue
            alert = Alert.objects.create(
                student=student,
                level=latest.level,
                message=(
                    f"Student {student} flagged as {latest.level.upper()} risk. "
                    f"{latest.explanation}"
                ),
            )
            AuditLog.log('alert_created', student=student,
                         detail=f"level={latest.level}")
            created.append(alert)
        return created


class LLMService:
    """
    Calls the Grok (xAI) API to generate:
    - A narrative profile summary of the student (for supervisors)
    - A personalised intervention plan with concrete action steps

    Groq uses the OpenAI-compatible chat completions format.
    Fallback to rule-based text if API key is missing or request fails.
    """

    MODEL = "llama-3.3-70b-versatile"
    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")

    def _build_student_context(self, student):
        """Assembles a structured student profile for the LLM prompt."""
        today = date.today()
        cutoff = today - timedelta(days=30)

        absences_30d = student.absences.filter(date__gte=cutoff)
        total_abs = absences_30d.count()
        unjustified_abs = absences_30d.filter(justified=False).count()
        justified_abs = total_abs - unjustified_abs

        # Last 3 risk scores
        risk_history = list(
            student.risk_scores.order_by('-computed_at')
            .values('level', 'score', 'computed_at', 'explanation')[:3]
        )

        # Active interventions
        active_plans = list(
            student.interventions.exclude(state='closed')
            .values('description', 'state', 'created_at')[:3]
        )

        return {
            "name": f"{student.first_name} {student.last_name}",
            "age": student.age,
            "school": student.school,
            "grade": student.grade,
            "region": student.region,
            "status": student.status,
            "absences_last_30_days": {
                "total": total_abs,
                "unjustified": unjustified_abs,
                "justified": justified_abs,
            },
            "current_risk_level": student.current_risk_level,
            "risk_score_history": [
                {
                    "level": r["level"],
                    "score": r["score"],
                    "date": str(r["computed_at"]),
                    "explanation": r["explanation"],
                }
                for r in risk_history
            ],
            "active_intervention_plans": [
                {
                    "description": p["description"],
                    "state": p["state"],
                    "created_at": str(p["created_at"]),
                }
                for p in active_plans
            ],
        }

    def _call_api(self, messages, max_tokens=800):
        """Raw HTTP call to Grok xAI API (OpenAI-compatible format)."""
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not set.")

        payload = json.dumps({
            "model": self.MODEL,
            "max_tokens": max_tokens,
            "messages": messages,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # OpenAI-compatible response format
        return data["choices"][0]["message"]["content"].strip()

    # ── Public methods ────────────────────────────────────────────────────────

    def generate_narrative(self, student):
        """
        Returns a short human-readable narrative summary of the student's profile
        suitable for display in the supervisor panel.
        """
        ctx = self._build_student_context(student)

        prompt = f"""You are an educational welfare assistant helping school supervisors in Tunisia.
Given the following student profile, write a concise 3-4 sentence narrative summary in English.
Highlight the key risk signals, any positive elements (e.g. justified absences), and the overall trend.
Do NOT give recommendations here — only describe the situation factually and empathetically.

Student profile (JSON):
{json.dumps(ctx, indent=2, default=str)}

Write the narrative now:"""

        try:
            return self._call_api([{"role": "user", "content": prompt}], max_tokens=300)
        except Exception as exc:
            # Graceful fallback
            level = ctx["current_risk_level"].upper()
            total = ctx["absences_last_30_days"]["total"]
            unjustified = ctx["absences_last_30_days"]["unjustified"]
            return (
                f"{ctx['name']} is a {ctx['age']}-year-old student at {ctx['school']} "
                f"(Grade {ctx['grade']}, {ctx['region'].title()}). "
                f"Over the past 30 days, they recorded {total} absence(s), "
                f"of which {unjustified} were unjustified. "
                f"Current risk level: {level}. "
                f"[LLM unavailable: {exc}]"
            )

    def generate_intervention_plan(self, student):
        """
        Returns a structured, personalised intervention plan with concrete steps.
        Response is a dict: { 'summary': str, 'actions': list[dict] }
        """
        ctx = self._build_student_context(student)

        level = ctx["current_risk_level"]
        unjustified = ctx["absences_last_30_days"]["unjustified"]
        total_abs = ctx["absences_last_30_days"]["total"]

        # Instructions spécifiques selon le niveau de risque
        if level == 'high':
            risk_instructions = """
RISK LEVEL: HIGH — This student is in CRITICAL situation.
Rules you MUST follow:
- urgency must be "immediate"
- follow_up_frequency must be "daily"
- Minimum 5 action steps
- Step 1 MUST be a face-to-face meeting with the student within 24-48 hours
- Step 2 MUST involve contacting the family urgently (phone call, not just a letter)
- Must include a step for Admin to evaluate if social services referral is needed
- Must include daily attendance monitoring by the teacher
- Tone: urgent, mobilizing all actors simultaneously
"""
        elif level == 'medium':
            risk_instructions = """
RISK LEVEL: MEDIUM — This student shows warning signs that need attention.
Rules you MUST follow:
- urgency must be "short_term"
- follow_up_frequency must be "weekly"
- 3 to 4 action steps
- Step 1 MUST be a one-on-one check-in with the teacher within the week
- Must include family communication (letter or phone)
- Must include weekly monitoring by counselor
- Tone: attentive but not alarmist, preventive approach
"""
        else:
            risk_instructions = """
RISK LEVEL: LOW — This student is currently stable but should be monitored.
Rules you MUST follow:
- urgency must be "monitoring"
- follow_up_frequency must be "monthly"
- 2 action steps maximum
- Focus on routine monitoring and positive reinforcement
- No need to involve family unless absence increases
- Tone: calm, preventive, encouraging
"""

        prompt = f"""You are an expert educational intervention specialist for Tunisian schools.
Based on the student profile below, generate a personalised intervention plan.

{risk_instructions}

Respond ONLY with valid JSON, no markdown, no extra text. Structure:
{{
  "risk_level": "{level}",
  "summary": "One sentence overview tailored to the {level} risk level.",
  "urgency": "immediate | short_term | monitoring",
  "actions": [
    {{
      "step": 1,
      "actor": "Teacher | Counselor | Family | Admin",
      "action": "Concrete action description",
      "deadline": "Within X days/weeks"
    }}
  ],
  "follow_up_frequency": "daily | weekly | monthly",
  "success_indicators": ["indicator 1", "indicator 2"],
  "risk_context": "One sentence explaining why this risk level was assigned based on the absence data."
}}

Be specific, realistic, and culturally appropriate for Tunisia.
Consider any existing intervention plans to avoid duplication.
The student has {unjustified} unjustified absences and {total_abs} total absences in the last 30 days.

Student profile (JSON):
{json.dumps(ctx, indent=2, default=str)}"""

        try:
            raw = self._call_api([{"role": "user", "content": prompt}], max_tokens=600)
            # Strip markdown fences if present
            clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(clean)
        except json.JSONDecodeError:
            # Return raw text wrapped in expected structure
            return {
                "summary": raw if 'raw' in dir() else "LLM response could not be parsed.",
                "urgency": "short_term",
                "actions": [],
                "follow_up_frequency": "weekly",
                "success_indicators": [],
                "parse_error": True,
            }
        except Exception as exc:
            # Rule-based fallback
            level = ctx["current_risk_level"]
            unjustified = ctx["absences_last_30_days"]["unjustified"]

            if level == 'high':
                actions = [
                    {"step": 1, "actor": "Counselor", "action": "Schedule urgent individual meeting with student.", "deadline": "Within 2 days"},
                    {"step": 2, "actor": "Family", "action": "Contact parents/guardians for an emergency meeting.", "deadline": "Within 3 days"},
                    {"step": 3, "actor": "Teacher", "action": "Implement daily attendance check-in.", "deadline": "Starting immediately"},
                    {"step": 4, "actor": "Admin", "action": "Review case and consider referral to social services if needed.", "deadline": "Within 1 week"},
                ]
                urgency = "immediate"
            elif level == 'medium':
                actions = [
                    {"step": 1, "actor": "Teacher", "action": "Schedule one-on-one check-in with student.", "deadline": "Within 1 week"},
                    {"step": 2, "actor": "Family", "action": "Send attendance report and request family feedback.", "deadline": "Within 1 week"},
                    {"step": 3, "actor": "Counselor", "action": "Monitor weekly attendance and provide support.", "deadline": "Ongoing"},
                ]
                urgency = "short_term"
            else:
                actions = [
                    {"step": 1, "actor": "Teacher", "action": "Continue routine monitoring of attendance.", "deadline": "Monthly"},
                ]
                urgency = "monitoring"

            return {
                "summary": f"Rule-based fallback plan for {level} risk student with {unjustified} unjustified absences.",
                "urgency": urgency,
                "actions": actions,
                "follow_up_frequency": "weekly" if level in ('high', 'medium') else "monthly",
                "success_indicators": [
                    "Zero unjustified absences in next 30 days",
                    "Student engagement improves in class",
                ],
                "fallback": True,
                "llm_error": str(exc),
            }
