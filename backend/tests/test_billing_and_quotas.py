"""Unit & Integration Tests for Billing, Quotas, and Webhook Idempotency."""

import hashlib
import hmac
import json
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import create_access_token
from app.config import settings
from app.services.billing_service import billing_service


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_access_token("usr-test-billing-123", email="billing-tester@example.com")
    return {"Authorization": f"Bearer {token}"}


class TestBillingAndQuotas:

    def test_get_billing_status(self, client, auth_headers):
        response = client.get("/api/v1/billing/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "usr-test-billing-123"
        assert data["subscription"]["plan"] == "free"
        assert data["quota"]["allowed"] is True
        assert "interviews_limit" in data["quota"]

    def test_create_checkout_session_validation(self, client, auth_headers):
        # Invalid plan
        resp_invalid = client.post(
            "/api/v1/billing/create-checkout-session",
            headers=auth_headers,
            json={"plan": "super-gold-ultra"}
        )
        assert resp_invalid.status_code == 400

        # Valid plan (pro)
        resp_valid = client.post(
            "/api/v1/billing/create-checkout-session",
            headers=auth_headers,
            json={"plan": "pro"}
        )
        assert resp_valid.status_code == 200
        data = resp_valid.json()
        assert data["plan"] == "pro"
        assert "checkout_url" in data

    def test_webhook_signature_verification(self):
        secret = "whsec_test_secret_key_12345"
        payload = json.dumps({"id": "evt_test_sig", "type": "checkout.session.completed"}).encode("utf-8")
        now = int(time.time())

        # Construct valid signature
        signed_payload = f"{now}.".encode("utf-8") + payload
        sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        sig_header = f"t={now},v1={sig}"

        # Valid
        assert billing_service.verify_stripe_signature(payload, sig_header, secret) is True

        # Tampered payload
        tampered = json.dumps({"id": "evt_tampered"}).encode("utf-8")
        assert billing_service.verify_stripe_signature(tampered, sig_header, secret) is False

        # Expired timestamp (replay attack)
        old_time = now - 600
        old_signed = f"{old_time}.".encode("utf-8") + payload
        old_sig = hmac.new(secret.encode("utf-8"), old_signed, hashlib.sha256).hexdigest()
        old_header = f"t={old_time},v1={old_sig}"
        assert billing_service.verify_stripe_signature(payload, old_header, secret, tolerance=300) is False

    def test_webhook_idempotency_guard(self, client):
        event_id = "evt_idempotent_test_001"
        payload = {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "usr-test-billing-123",
                    "metadata": {"user_id": "usr-test-billing-123", "plan": "pro"},
                    "customer": "cus_123456",
                    "subscription": "sub_987654",
                }
            }
        }

        # First call: should process and upgrade
        res1 = client.post("/api/v1/billing/webhook", json=payload)
        assert res1.status_code == 200
        assert res1.json()["status"] == "success"

        # Verify user is upgraded to pro
        sub = billing_service.get_user_subscription("usr-test-billing-123")
        assert sub["plan"] == "pro"
        assert sub["status"] == "active"

        # Second call with same event_id: IDEMPOTENCY GUARD returns cached success
        res2 = client.post("/api/v1/billing/webhook", json=payload)
        assert res2.status_code == 200
        assert res2.json()["status"] == "already_processed"
        assert res2.json()["event_id"] == event_id

    def test_webhook_subscription_cancellation(self, client):
        cancel_event = {
            "id": "evt_cancel_001",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_987654",
                    "metadata": {"user_id": "usr-test-billing-123"},
                }
            }
        }
        res = client.post("/api/v1/billing/webhook", json=cancel_event)
        assert res.status_code == 200

        sub = billing_service.get_user_subscription("usr-test-billing-123")
        assert sub["status"] == "canceled"

    def test_quota_limits_and_consumption(self):
        user_id = "usr-quota-limited-user"
        # Initial quota check
        q1 = billing_service.check_and_consume_quota(user_id, tokens=5000)
        assert q1["allowed"] is True
        assert q1["interviews_taken"] == 1
        assert q1["tokens_consumed"] == 5000

        # Simulate consuming until 5 interviews limit (free tier)
        for _ in range(4):
            billing_service.check_and_consume_quota(user_id, tokens=5000)

        # 6th attempt: should be blocked
        q_exceeded = billing_service.check_and_consume_quota(user_id, tokens=1000)
        assert q_exceeded["allowed"] is False
        assert "Daily quota limit reached" in q_exceeded["reason"]
