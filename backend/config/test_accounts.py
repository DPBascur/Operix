from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.events.test_pair_events import pair_payload
from .access import OPERATOR_GROUP

USERS = "/api/v1/users/"
AUTH = "/api/v1/auth/"
TEST_PASSWORD = "A long local testing phrase with punctuation #405"
NEW_PASSWORD = "Another local testing phrase with punctuation #671"


class AccountDirectoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.root = users.create_superuser("root-admin", password=TEST_PASSWORD)
        cls.legacy = users.create_user("legacy-user", password=TEST_PASSWORD)
        cls.legacy.groups.add(Group.objects.get_or_create(name=OPERATOR_GROUP)[0])

    def signed_in(self, user, password=TEST_PASSWORD):
        client = APIClient(enforce_csrf_checks=True)
        token = client.get(AUTH + "session/").json()["csrf_token"]
        response = client.post(AUTH + "login/", {
            "username": user.username, "password": password
        }, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.json())
        client.credentials(HTTP_X_CSRFTOKEN=response.json()["csrf_token"])
        return client

    def add(self, client, username, role, **fields):
        return client.post(USERS, {
            "username": username, "display_name": "Cuenta de prueba",
            "role": role, "is_active": True, "password": TEST_PASSWORD, **fields
        }, format="json")

    def test_create_each_role_and_scope_credentials(self):
        admin = self.signed_in(self.root)
        for role in ("administrator", "safety_lead", "viewer"):
            response = self.add(admin, role, role)
            self.assertEqual(response.status_code, 201, response.json())
            self.assertNotIn(TEST_PASSWORD, response.content.decode())
            user = get_user_model().objects.get(username=role)
            self.assertFalse(user.is_superuser)
            self.assertFalse(user.is_staff)
            self.assertTrue(user.check_password(TEST_PASSWORD))
            browser = self.signed_in(user)
            self.assertEqual(browser.get(AUTH + "session/").json()["user"]["role"], role)
            self.assertEqual(browser.get(USERS).status_code, 200 if role == "administrator" else 403)
            if role != "administrator":
                self.assertEqual(self.add(browser, "unauthorized", "administrator").status_code, 403)
        self.assertEqual(APIClient().get(USERS).status_code, 401)
        self.assertEqual(self.add(admin, "VIEWER", "viewer").status_code, 409)
        self.assertEqual(self.add(admin, "weak", "viewer", password="password").status_code, 400)
        self.assertEqual(self.add(admin, "too-long", "viewer", password="a" * 257).status_code, 400)
        self.assertEqual(self.add(admin, "malformed", "viewer", is_active="true").status_code, 400)
        self.assertEqual(self.add(admin, "unexpected", "viewer", is_superuser=True).status_code, 400)
        admin.credentials()
        self.assertEqual(self.add(admin, "csrf", "viewer").status_code, 403)

    def test_legacy_permissions_and_explicit_reassignment(self):
        admin = self.signed_in(self.root)
        viewer = self.signed_in(self.legacy)
        self.assertTrue(viewer.get(AUTH + "session/").json()["user"]["role_review_required"])
        listed = next(row for row in admin.get(USERS).json()["accounts"] if row["id"] == self.legacy.pk)
        self.assertTrue(listed["role_review_required"])
        for url in ("/api/v1/events/", "/api/v1/events/frequencies/", "/api/v1/analysis/sessions/"):
            self.assertEqual(viewer.get(url).status_code, 403)
        self.assertEqual(viewer.post("/api/v1/analysis/sessions/", {}, format="json").status_code, 403)
        response = admin.patch(USERS + f"{self.legacy.pk}/", {
            "role": "safety_lead", "is_active": True,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.json())
        self.assertFalse(response.json()["role_review_required"])
        self.legacy.refresh_from_db()
        self.assertTrue(self.legacy.check_password(TEST_PASSWORD))
        self.assertEqual(viewer.get("/api/v1/events/").status_code, 200)

    def test_admin_protection_disable_and_reset(self):
        admin = self.signed_in(self.root)
        body = {"role": "viewer", "is_active": False}
        self.assertEqual(admin.patch(USERS + f"{self.root.pk}/", body, format="json").status_code, 409)
        managed = self.add(admin, "operix-admin", "administrator").json()
        other_admin = self.signed_in(get_user_model().objects.get(pk=managed["id"]))
        self.assertEqual(other_admin.patch(USERS + f"{self.root.pk}/", body, format="json").status_code, 409)
        self.assertEqual(other_admin.post(USERS + f"{self.root.pk}/password/", {
            "password": NEW_PASSWORD
        }, format="json").status_code, 409)
        actor = self.signed_in(self.legacy)
        url = USERS + f"{self.legacy.pk}/"
        self.assertEqual(admin.post(url + "password/", {"password": NEW_PASSWORD}, format="json").status_code, 200)
        self.assertEqual(actor.get("/api/v1/indicators/shared/").status_code, 401)
        fresh = self.signed_in(self.legacy, NEW_PASSWORD)
        self.assertEqual(admin.patch(url, body, format="json").status_code, 200)
        self.assertEqual(fresh.get("/api/v1/indicators/shared/").status_code, 401)

    def test_shared_indicators_omit_private_fields_and_demos(self):
        from apps.events.serializers import EventSerializer
        from uuid import uuid4
        from django.utils.timezone import now

        for kind in ("manual", "demo"):
            data = pair_payload()
            data["analysis_run_id"] = str(uuid4())
            data["occurred_at"] = now().isoformat()
            data["source"] = {"kind": kind}
            serializer = EventSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        viewer = self.signed_in(self.legacy)
        url = "/api/v1/indicators/shared/"
        self.assertEqual(APIClient().get(url).status_code, 401)
        response = viewer.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(set(response.json()), {"total", "timezone", "period", "by_period", "by_type"})
        self.assertEqual(viewer.get(url, {"source_sha256": "a" * 64}).status_code, 400)
        self.assertEqual(viewer.get(url, {"source_kind": "demo"}).status_code, 400)
        self.assertEqual(viewer.get(url, {"occurred_after": now().isoformat()}).status_code, 400)
        self.assertEqual(viewer.get(url, {"month": "2025-02"}).json()["total"], 0)
