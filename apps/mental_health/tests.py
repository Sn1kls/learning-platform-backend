"""Tests for the pre/post self-assessment subsystem (apps.mental_health).

Covers domain models (singleton survey, question ordering, attempt
uniqueness), the score-recalculation signal and the REST API endpoints
(retrieving the survey, submitting the "before start" / "after finish"
attempts and the access guards between them).
"""

import json

import pytest
from django.core.cache import cache
from django.db import IntegrityError
from django.test import Client
from ninja_jwt.tokens import RefreshToken

from apps.mental_health.models import (
    MentalHealth,
    MentalHealthAttempt,
    MentalHealthAttemptNumber,
    MentalHealthQuestion,
    UserMentalHealthResponse,
)
from apps.modules.models import ContentType, Lesson, Module, UserLessonProgress
from apps.users.models import User

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def survey():
    cache.clear()
    return MentalHealth.objects.create(
        title="Самооцінювання рівня знань",
        additional_content="<p>Оцініть свій рівень за шкалою 0–5</p>",
    )


@pytest.fixture
def user():
    u = User.objects.create_user(
        email="learner@example.com",
        password="Str0ng!Pass",
        first_name="Olha",
        last_name="Petrenko",
        phone="+380501112233",
    )
    u.has_approved_requirements = True
    u.save(update_fields=["has_approved_requirements"])
    return u


@pytest.fixture
def auth(user):
    token = str(RefreshToken.for_user(user).access_token)
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _post(client, url, payload, headers):
    return client.post(url, data=json.dumps(payload),
                       content_type="application/json", **headers)


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class MentalHealthModelTests:
    def test_survey_is_singleton(self):
        cache.clear()
        MentalHealth.objects.create(title="A", additional_content="a")
        MentalHealth.objects.create(title="B", additional_content="b")
        assert MentalHealth.objects.count() == 1
        assert MentalHealth.get_solo().title == "B"

    def test_question_auto_increments_order(self, survey):
        q1 = MentalHealthQuestion.objects.create(question="Q1")
        q2 = MentalHealthQuestion.objects.create(question="Q2")
        q3 = MentalHealthQuestion.objects.create(question="Q3")
        assert [q1.order, q2.order, q3.order] == [1, 2, 3]

    def test_question_is_bound_to_singleton_survey(self, survey):
        q = MentalHealthQuestion.objects.create(question="Q")
        assert q.mental_health_id == survey.id

    def test_question_default_scale_is_zero_to_five(self, survey):
        q = MentalHealthQuestion.objects.create(question="scale?")
        assert (q.min_score, q.max_score) == (0, 5)

    def test_attempt_number_choices(self):
        assert MentalHealthAttemptNumber.BEFORE_START.value == 1
        assert MentalHealthAttemptNumber.AFTER_FINISH.value == 2

    def test_attempt_is_unique_per_user_and_number(self, survey, user):
        MentalHealthAttempt.objects.create(
            number=MentalHealthAttemptNumber.BEFORE_START,
            user_fk=user, mental_health=survey,
        )
        with pytest.raises(IntegrityError):
            MentalHealthAttempt.objects.create(
                number=MentalHealthAttemptNumber.BEFORE_START,
                user_fk=user, mental_health=survey,
            )

    def test_before_and_after_attempts_coexist(self, survey, user):
        MentalHealthAttempt.objects.create(
            number=MentalHealthAttemptNumber.BEFORE_START,
            user_fk=user, mental_health=survey,
        )
        MentalHealthAttempt.objects.create(
            number=MentalHealthAttemptNumber.AFTER_FINISH,
            user_fk=user, mental_health=survey,
        )
        assert MentalHealthAttempt.objects.filter(user_fk=user).count() == 2


# --------------------------------------------------------------------------- #
# Signal: attempt score is kept in sync with the responses
# --------------------------------------------------------------------------- #
class MentalHealthSignalTests:
    def _attempt(self, survey, user, number=MentalHealthAttemptNumber.BEFORE_START):
        return MentalHealthAttempt.objects.create(
            number=number, user_fk=user, mental_health=survey,
        )

    def test_score_is_summed_on_response_save(self, survey, user):
        q1 = MentalHealthQuestion.objects.create(question="Q1")
        q2 = MentalHealthQuestion.objects.create(question="Q2")
        attempt = self._attempt(survey, user)
        UserMentalHealthResponse.objects.create(attempt_fk=attempt, question_fk=q1, response=3)
        UserMentalHealthResponse.objects.create(attempt_fk=attempt, question_fk=q2, response=5)
        attempt.refresh_from_db()
        assert attempt.score == 8

    def test_score_is_recomputed_on_response_delete(self, survey, user):
        q1 = MentalHealthQuestion.objects.create(question="Q1")
        attempt = self._attempt(survey, user, MentalHealthAttemptNumber.AFTER_FINISH)
        response = UserMentalHealthResponse.objects.create(
            attempt_fk=attempt, question_fk=q1, response=4,
        )
        attempt.refresh_from_db()
        assert attempt.score == 4
        response.delete()
        attempt.refresh_from_db()
        assert attempt.score == 0


# --------------------------------------------------------------------------- #
# REST API
# --------------------------------------------------------------------------- #
class MentalHealthApiTests:
    URL = "/api/mental-health/"
    ANSWERS = "/api/mental-health/answers"

    def test_get_survey_returns_questions(self, survey, auth):
        MentalHealthQuestion.objects.create(question="Q1")
        MentalHealthQuestion.objects.create(question="Q2")
        resp = Client().get(self.URL, **auth)
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == survey.title
        assert len(body["questions"]) == 2

    def test_get_survey_requires_auth(self, survey):
        assert Client().get(self.URL).status_code == 401

    def test_submit_before_start_attempt(self, survey, user, auth):
        q1 = MentalHealthQuestion.objects.create(question="Q1")
        q2 = MentalHealthQuestion.objects.create(question="Q2")
        payload = {
            "number": MentalHealthAttemptNumber.BEFORE_START.value,
            "answers": [
                {"question_id": q1.id, "response": 2},
                {"question_id": q2.id, "response": 4},
            ],
        }
        resp = _post(Client(), self.ANSWERS, payload, auth)
        assert resp.status_code == 201
        assert resp.json()["score"] == 6
        assert MentalHealthAttempt.objects.filter(
            user_fk=user, number=MentalHealthAttemptNumber.BEFORE_START,
        ).exists()

    def test_after_finish_requires_previous_attempt(self, survey, user, auth):
        q1 = MentalHealthQuestion.objects.create(question="Q1")
        payload = {
            "number": MentalHealthAttemptNumber.AFTER_FINISH.value,
            "answers": [{"question_id": q1.id, "response": 5}],
        }
        resp = _post(Client(), self.ANSWERS, payload, auth)
        assert resp.status_code == 403

    def test_after_finish_requires_completed_education(self, survey, user, auth):
        q1 = MentalHealthQuestion.objects.create(question="Q1")
        MentalHealthAttempt.objects.create(
            number=MentalHealthAttemptNumber.BEFORE_START,
            user_fk=user, mental_health=survey,
        )
        payload = {
            "number": MentalHealthAttemptNumber.AFTER_FINISH.value,
            "answers": [{"question_id": q1.id, "response": 5}],
        }
        resp = _post(Client(), self.ANSWERS, payload, auth)
        assert resp.status_code == 403

    def test_after_finish_succeeds_when_course_completed(self, survey, user, auth):
        q1 = MentalHealthQuestion.objects.create(question="Q1")
        MentalHealthAttempt.objects.create(
            number=MentalHealthAttemptNumber.BEFORE_START,
            user_fk=user, mental_health=survey,
        )
        module = Module.objects.create(name="Module 1")
        lesson = Lesson.objects.create(
            name="Final lesson", module_fk=module, content_type=ContentType.TEXT,
        )
        UserLessonProgress.objects.create(
            user_fk=user, lesson_fk=lesson, is_completed=True,
        )
        payload = {
            "number": MentalHealthAttemptNumber.AFTER_FINISH.value,
            "answers": [{"question_id": q1.id, "response": 5}],
        }
        resp = _post(Client(), self.ANSWERS, payload, auth)
        assert resp.status_code == 201
        assert resp.json()["score"] == 5

    def test_list_attempts_returns_only_own(self, survey, user, auth):
        MentalHealthAttempt.objects.create(
            number=MentalHealthAttemptNumber.BEFORE_START,
            user_fk=user, mental_health=survey,
        )
        resp = Client().get(self.ANSWERS, **auth)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
