from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import close_old_connections
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from rest_framework.test import APIClient

from apps.events.test_pair_events import pair_payload
from apps.analysis.models import SpatialConfiguration
from .access import ADMIN_GROUP, OPERATOR_GROUP
from .models import AccountRetirement

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

    def test_retirement_preserves_history_and_revokes_access(self):
        admin = self.signed_in(self.root)
        managed = self.add(admin, "retirement-target", "safety_lead").json()
        user = get_user_model().objects.get(pk=managed["id"])
        session = self.signed_in(user)
        config = SpatialConfiguration.objects.create(
            owner=user, source_sha256="f" * 64, revision=1, document={"zones": []},
        )
        detail = USERS + f"{user.pk}/"
        response = admin.post(detail + "retire/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["retired"])
        self.assertFalse(response.json()["is_active"])
        self.assertEqual(AccountRetirement.objects.get(account=user).actor, self.root)
        config.refresh_from_db()
        self.assertEqual(config.owner_id, user.pk)
        user.refresh_from_db()
        self.assertFalse(user.has_usable_password())
        self.assertEqual(session.get("/api/v1/events/").status_code, 401)
        self.assertEqual(session.get("/api/v1/analysis/sessions/").status_code, 401)
        self.assertIsNone(session.get(AUTH + "session/").json()["user"])
        anonymous = APIClient()
        self.assertNotEqual(anonymous.post(AUTH + "login/", {
            "username": user.username, "password": TEST_PASSWORD,
        }, format="json").status_code, 200)
        self.assertEqual(admin.patch(detail, {"role": "viewer", "is_active": True}, format="json").status_code, 409)
        self.assertEqual(admin.post(detail + "password/", {"password": NEW_PASSWORD}, format="json").status_code, 409)
        self.assertEqual(admin.post(detail + "retire/").status_code, 409)
        with self.assertRaises(ProtectedError):
            user.delete()

    def test_retirement_requires_admin_and_csrf(self):
        admin = self.signed_in(self.root)
        managed = self.add(admin, "retirement-target", "safety_lead").json()
        url = USERS + f"{managed['id']}/retire/"
        lead = self.signed_in(get_user_model().objects.get(pk=managed["id"]))
        viewer = self.signed_in(self.legacy)
        self.assertEqual(APIClient().post(url).status_code, 401)
        self.assertEqual(lead.post(url).status_code, 403)
        self.assertEqual(viewer.post(url).status_code, 403)
        self.assertEqual(admin.post(USERS + "99999/retire/").status_code, 404)
        self.assertEqual(admin.post(USERS + f"{self.root.pk}/retire/").status_code, 409)
        self.assertEqual(admin.delete(USERS + f"{managed['id']}/").status_code, 405)
        admin.credentials()
        self.assertEqual(admin.post(url).status_code, 403)
        self.assertFalse(AccountRetirement.objects.exists())

    def test_reactivation_preserves_role_and_never_restores_old_sessions(self):
        admin = self.signed_in(self.root)
        managed = self.add(admin, "reactivation-target", "safety_lead").json()
        user = get_user_model().objects.get(pk=managed["id"])
        old_session = self.signed_in(user)
        url = USERS + f"{user.pk}/"
        disabled = {"role": "safety_lead", "is_active": False}
        self.assertEqual(admin.patch(url, disabled, format="json").status_code, 200)
        self.assertEqual(admin.patch(url, {"role": "administrator", "is_active": True}, format="json").status_code, 409)
        self.assertEqual(admin.post(url + "reactivate/", {"password": TEST_PASSWORD}, format="json").status_code, 400)
        self.assertEqual(admin.post(url + "reactivate/", {"password": NEW_PASSWORD, "role": "administrator"}, format="json").status_code, 400)
        response = admin.post(url + "reactivate/", {"password": NEW_PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()["role"], "safety_lead")
        self.assertEqual(old_session.get("/api/v1/events/").status_code, 401)
        self.assertEqual(self.signed_in(user, NEW_PASSWORD).get("/api/v1/events/").status_code, 200)


class AccountRetirementConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_two_administrators_cannot_retire_each_other(self):
        group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        users = [get_user_model().objects.create_user(name) for name in ("first-admin", "second-admin")]
        for user in users:
            user.groups.add(group)
        barrier = Barrier(2, timeout=10)

        def retire(actor, target):
            close_old_connections()
            try:
                client = APIClient()
                client.force_login(actor)
                barrier.wait()
                return client.post(USERS + f"{target.pk}/retire/").status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(retire, *users)
            second = workers.submit(retire, *reversed(users))
            statuses = sorted((first.result(), second.result()))
        self.assertEqual(statuses[0], 200)
        self.assertIn(statuses[1], (401, 403, 409))
        self.assertEqual(get_user_model().objects.filter(is_active=True, groups=group).count(), 1)
        self.assertEqual(AccountRetirement.objects.count(), 1)
