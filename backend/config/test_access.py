from datetime import timedelta
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.db import close_old_connections
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analysis.sessions import remove_session
from apps.events.test_pair_events import pair_payload
from config.access import OPERATOR_GROUP, SAFETY_GROUP, login_peer, login_retry_after
from config.models import LoginBucket
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
        self.assertIn("no-store", client.get(EVENTS)["Cache-Control"])
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

    @override_settings(OPERIX_LOGIN_WINDOW_SECONDS=60)
    def test_login_limit_blocks_password_verification_and_ignores_forwarded_ip(self):
        client = APIClient(enforce_csrf_checks=True)
        token = client.get(AUTH + "session/").json()["csrf_token"]
        with patch("config.access.LOGIN_ACCOUNT_LIMIT", 2), patch("config.access.LOGIN_PEER_LIMIT", 4), (
            patch("config.access.time", return_value=121)
        ) as clock:
            def attempt(username, ip):
                return client.post(AUTH + "login/", {"username": username, "password": "wrong"},
                                   format="json", HTTP_X_CSRFTOKEN=token, HTTP_X_FORWARDED_FOR=ip)

            self.assertEqual(attempt("operator", "192.0.2.1").status_code, 401)
            self.assertEqual(attempt("operator", "192.0.2.2").status_code, 401)
            with patch("config.access.authenticate") as authenticate:
                blocked = attempt("OPERATOR", "192.0.2.3")
                self.assertEqual(blocked.status_code, 429)
                self.assertEqual(blocked["Retry-After"], "59")
                authenticate.assert_not_called()
            self.assertEqual(attempt("other", "192.0.2.4").status_code, 401)
            self.assertEqual(attempt("unknown", "192.0.2.5").status_code, 429)
            clock.return_value = 180
            self.assertEqual(self.sign_in(client, "operator").status_code, 200)

    def test_login_bad_inputs_are_rejected_without_account_disclosure(self):
        client = APIClient()
        get_user_model().objects.filter(username="other").update(is_active=False)
        errors = []
        for name in ("operator", "other", "unknown", "' OR 1=1 --", "<script>"):
            response = client.post(AUTH + "login/", {"username": name, "password": "wrong"}, format="json")
            self.assertEqual(response.status_code, 401)
            errors.append(response.json()["detail"])
        self.assertEqual(len(set(errors)), 1)
        for payload in (b"{", b"null", b"[]", b'{"username": 7, "password": []}'):
            self.assertEqual(client.generic("POST", AUTH + "login/", payload, "application/json").status_code, 400)
        self.assertEqual(client.post(AUTH + "login/", {"username": "u"*151, "password": "x"}, format="json").status_code, 400)
        self.assertEqual(client.post(AUTH + "login/", {"username": "u", "password": "x"*4097}, format="json").status_code, 400)
        self.assertEqual(client.generic("POST", AUTH + "login/", b"x"*32769, "application/json").status_code, 413)
        for username in ("nul\0name", "\ud800"):
            payload = json.dumps({"username": username, "password": "x"}).encode()
            self.assertEqual(client.generic("POST", AUTH + "login/", payload, "application/json").status_code, 400)

    @override_settings(OPERIX_TRUSTED_LOGIN_PROXIES=["192.0.2.2"])
    def test_only_the_explicit_proxy_can_supply_the_last_forwarded_ip(self):
        factory = RequestFactory()
        headers = {"HTTP_X_FORWARDED_FOR": "203.0.113.99, 198.51.100.7"}
        self.assertEqual(login_peer(factory.post("/", REMOTE_ADDR="192.0.2.1", **headers)), "192.0.2.1")
        self.assertEqual(login_peer(factory.post("/", REMOTE_ADDR="192.0.2.2", **headers)), "198.51.100.7")

    def test_admin_cannot_bypass_the_api_login_budget(self):
        client = APIClient()
        with patch("config.access.LOGIN_ACCOUNT_LIMIT", 1):
            response = client.post(AUTH + "login/", {"username": "admin", "password": "bad"}, format="json")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(client.post("/admin/login/", {"username": "admin", "password": PASSWORD}).status_code, 429)

    def test_admin_password_route_requires_staff(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.get("/admin/password_change/").status_code, 302)
        token = self.sign_in(client, "operator").json()["csrf_token"]
        self.assertEqual(client.get("/admin/password_change/").status_code, 302)
        self.assertEqual(client.post("/admin/password_change/", {
            "old_password": PASSWORD, "new_password1": PASSWORD, "new_password2": PASSWORD,
        }, HTTP_X_CSRFTOKEN=token).status_code, 302)
        self.sign_in(client, "admin")
        self.assertEqual(client.get("/admin/password_change/").status_code, 200)

    def test_password_change_rotates_current_session_and_revokes_the_other(self):
        current = APIClient(enforce_csrf_checks=True)
        other = APIClient(enforce_csrf_checks=True)
        token = self.sign_in(current, "reviewer").json()["csrf_token"]
        self.sign_in(other, "reviewer")
        old_session = current.cookies[settings.SESSION_COOKIE_NAME].value
        url = AUTH + "password/"
        new = "Passphrase de evaluación con símbolos # y espacios " + "á"*30
        data = {"old_password": PASSWORD, "new_password1": new, "new_password2": new}
        self.assertEqual(current.get(url).status_code, 405)
        self.assertEqual(current.post(url, data, format="json").status_code, 403)
        self.assertEqual(APIClient().post(url, data, format="json").status_code, 401)
        for invalid in ({"old_password": "bad"}, {"new_password2": "different"},
                        {"new_password1": "weak", "new_password2": "weak"},
                        {"new_password1": "a"*257, "new_password2": "a"*257}, {"user_id": 9}):
            response = current.post(url, {**data, **invalid}, format="json", HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 400)
        changed = current.post(url, data, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(changed.status_code, 200, changed.json())
        self.assertNotEqual(current.cookies[settings.SESSION_COOKIE_NAME].value, old_session)
        self.assertEqual(current.get(EVENTS).status_code, 200)
        self.assertEqual(other.get(EVENTS).status_code, 401)
        user = get_user_model().objects.get(username="reviewer")
        self.assertTrue(user.check_password(new))
        self.assertFalse(user.check_password(PASSWORD))

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


class LoginConcurrencyTests(TransactionTestCase):
    def test_expired_identities_are_removed_instead_of_accumulating(self):
        request = RequestFactory().post("/")
        with patch("config.access.time", return_value=1):
            self.assertIsNone(login_retry_after(request, "old-account"))
        with patch("config.access.time", return_value=10000):
            self.assertIsNone(login_retry_after(request, "new-account"))
        self.assertEqual(LoginBucket.objects.count(), 4)

    def test_rotating_ips_cannot_bypass_the_account_budget(self):
        with patch("config.access.LOGIN_DISTRIBUTED_LIMIT", 3):
            results = [login_retry_after(RequestFactory().post("/", REMOTE_ADDR=f"192.0.2.{n}"), "same")
                       for n in range(1, 6)]
        self.assertEqual(results.count(None), 3)

    def test_workers_share_a_single_attempt_budget(self):
        def attempt(_):
            close_old_connections()
            try:
                request = RequestFactory().post("/api/v1/auth/login/")
                return login_retry_after(request, "same-account")
            finally:
                close_old_connections()

        with patch("config.access.time", return_value=121), ThreadPoolExecutor(4) as pool:
            outcomes = list(pool.map(attempt, range(12)))
        self.assertEqual(outcomes.count(None), 8)
