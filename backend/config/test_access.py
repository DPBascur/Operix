from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analysis.sessions import remove_session
from apps.events.test_pair_events import pair_payload
from config.access import OPERATOR_GROUP, SAFETY_GROUP
from uuid import UUID

AUTH = "/api/v1/auth/"
EVENTS = "/api/v1/events/"
ANALYSIS = "/api/v1/analysis/"
PASSWORD = "TEST_ONLY_a_passphrase_37!"


@override_settings(EVENT_POST_ENABLED=True)
class AccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        operator = Group.objects.create(name=OPERATOR_GROUP)
        reviewer = Group.objects.create(name=SAFETY_GROUP)
        for name, group in (("operator", operator), ("other", operator), ("reviewer", reviewer)):
            users.create_user(username=name, password=PASSWORD).groups.add(group)
        users.create_superuser(username="admin", password=PASSWORD)
        users.create_user(username="unassigned", password=PASSWORD)

    def sign_in(self, client, username):
        token = client.get(AUTH + "session/").json()["csrf_token"]
        return client.post(AUTH + "login/", {"username": username, "password": PASSWORD},
                           format="json", HTTP_X_CSRFTOKEN=token)

    def test_login_csrf_expiration_logout_and_password_is_not_returned(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertIsNone(client.get(AUTH + "session/").json()["user"])
        self.assertEqual(client.post(AUTH + "login/", {}, format="json").status_code, 403)
        token = client.get(AUTH + "session/").json()["csrf_token"]
        credentials = {"username": "reviewer", "password": PASSWORD}
        self.assertEqual(client.post(AUTH + "login/", credentials, format="json",
            HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://untrusted.example").status_code, 403)
        self.assertEqual(client.post(AUTH + "login/", {**credentials, "password": "wrong"}, format="json",
            HTTP_X_CSRFTOKEN=token).status_code, 401)
        logged = self.sign_in(client, "reviewer")
        self.assertEqual(logged.status_code, 200)
        self.assertEqual(logged.json()["user"], {"username": "reviewer", "role": "safety_lead"})
        self.assertNotIn(PASSWORD, logged.content.decode())
        self.assertNotIn(settings.OPERIX_EVENT_PUBLISH_TOKEN, logged.content.decode())
        cookie = logged.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(client.get(EVENTS).status_code, 200)
        self.assertEqual(client.post(AUTH + "logout/").status_code, 403)
        Session.objects.filter(session_key=cookie.value).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertEqual(client.get(EVENTS).status_code, 401)
        recovered = self.sign_in(client, "reviewer")
        self.assertEqual(recovered.status_code, 200)
        saved_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertEqual(client.post(AUTH + "logout/", HTTP_X_CSRFTOKEN=recovered.json()["csrf_token"]).status_code, 200)
        client.cookies[settings.SESSION_COOKIE_NAME] = saved_cookie
        self.assertEqual(client.get(EVENTS).status_code, 401)

    def test_roles_and_token_are_separate(self):
        publisher = APIClient()
        publisher.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.OPERIX_EVENT_PUBLISH_TOKEN}")
        created = publisher.post(EVENTS, pair_payload(), format="json")
        self.assertEqual(created.status_code, 201)
        detail = f"{EVENTS}{created.data['id']}/"
        for name, expected in ((None, 401), ("operator", 403), ("reviewer", 200), ("admin", 200)):
            client = APIClient(enforce_csrf_checks=True)
            if name:
                self.assertEqual(self.sign_in(client, name).status_code, 200)
            for url in (EVENTS, EVENTS + "frequencies/", detail):
                self.assertEqual(client.get(url).status_code, expected)
            self.assertEqual(client.get(detail + "evidence/").status_code, 404 if expected == 200 else expected)
            self.assertEqual(client.post(EVENTS, pair_payload(), format="json").status_code, 403)
            self.assertEqual(client.post(detail + "evidence/").status_code, 403)
        self.assertEqual(publisher.get(EVENTS).status_code, 401)
        self.assertEqual(self.sign_in(APIClient(enforce_csrf_checks=True), "unassigned").status_code, 401)
        reviewer = APIClient()
        self.sign_in(reviewer, "reviewer")
        get_user_model().objects.get(username="reviewer").groups.clear()
        self.assertEqual(reviewer.get(EVENTS).status_code, 403)

    def test_analysis_isolation_on_all_routes(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        owner = APIClient(enforce_csrf_checks=True)
        token = self.sign_in(owner, "operator").json()["csrf_token"]
        collection = ANALYSIS + "sessions/"
        self.assertEqual(owner.post(collection, {}, format="json").status_code, 403)
        created = owner.post(collection, {
            "profile": "A", "video": SimpleUploadedFile("fixture.mp4", b"\x00\x00\x00\x10ftypisomvideo"),
        }, format="multipart", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(created.status_code, 201, created.data)
        self.addCleanup(remove_session, UUID(created.data["id"]))
        url = collection + created.data["id"] + "/"
        other = APIClient()
        self.sign_in(other, "other")
        self.assertEqual(owner.get(url + "source/", HTTP_RANGE="bytes=0-3").status_code, 206)
        for suffix in ("status/", "source/", "result/", "stream/"):
            self.assertEqual(other.get(url + suffix).status_code, 404)
            self.assertEqual(APIClient().get(url + suffix).status_code, 401)
        for suffix in ("start/", "stop/", "persistence/retry/"):
            self.assertEqual(other.post(url + suffix).status_code, 404)
        self.assertEqual(other.put(url + "zone/", {"profile": "B"}, format="json").status_code, 404)
        self.assertEqual(other.delete(url).status_code, 404)
        reviewer = APIClient()
        self.sign_in(reviewer, "reviewer")
        self.assertEqual(reviewer.get(url + "source/").status_code, 403)
        self.assertEqual(owner.get(url + "status/").status_code, 200)
