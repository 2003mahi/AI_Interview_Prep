"""Billing, Subscription, and Usage Quota Service.

Provides verified payment webhook handling with cryptographic signature verification,
idempotency protection against replay attacks, and usage quota enforcement.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional
from supabase import Client, create_client

from ..config import settings
from ..logger import logger


class BillingService:
    def __init__(self):
        self._is_live_client = False
        self._supabase: Optional[Client] = None
        # In-memory storage for test suites and offline resilience
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self._quotas: Dict[str, Dict[str, Any]] = {}
        self._processed_events: Dict[str, Dict[str, Any]] = {}

        auth_key = settings.supabase_service_role_key or settings.supabase_key
        if (
            settings.supabase_url
            and "placeholder" not in settings.supabase_url
            and auth_key
            and "placeholder" not in auth_key
        ):
            try:
                self._supabase = create_client(settings.supabase_url, auth_key)
                self._is_live_client = True
                logger.info("Initialized live Supabase DB client for Billing service")
            except Exception as e:
                logger.warning(f"Could not connect to live Supabase DB for Billing: {e}. Using in-memory store.")

    def verify_stripe_signature(self, payload: bytes, sig_header: str, secret: str, tolerance: int = 300) -> bool:
        """
        Verify Stripe webhook signature (v1 scheme) with HMAC SHA-256 and replay tolerance.
        """
        if not sig_header or not secret:
            return False

        try:
            # Parse signature header components (t=timestamp, v1=signature)
            elements = sig_header.split(",")
            timestamp = None
            signatures = []
            for element in elements:
                parts = element.strip().split("=", 1)
                if len(parts) == 2:
                    k, v = parts[0], parts[1]
                    if k == "t":
                        timestamp = int(v)
                    elif k == "v1":
                        signatures.append(v)

            if not timestamp or not signatures:
                return False

            # Check timestamp tolerance (prevent replay attacks)
            current_time = int(time.time())
            if abs(current_time - timestamp) > tolerance:
                logger.warning(f"Webhook signature timestamp out of tolerance: {timestamp} vs {current_time}")
                return False

            # Construct signed payload
            signed_payload = f"{timestamp}.".encode("utf-8") + payload
            computed_signature = hmac.new(
                secret.encode("utf-8"),
                signed_payload,
                hashlib.sha256
            ).hexdigest()

            # Constant-time comparison to prevent timing attacks
            match = any(hmac.compare_digest(computed_signature, sig) for sig in signatures)
            return match
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False

    def is_event_processed(self, event_id: str, idempotency_key: Optional[str] = None) -> bool:
        """Check if payment event was already processed (Idempotency Guard)."""
        if event_id in self._processed_events:
            return True
        if idempotency_key and idempotency_key in self._processed_events:
            return True

        if self._is_live_client and self._supabase:
            try:
                res = self._supabase.table("payment_events").select("id").eq("event_id", event_id).execute()
                if res.data and len(res.data) > 0:
                    return True
                if idempotency_key:
                    res_key = self._supabase.table("payment_events").select("id").eq("idempotency_key", idempotency_key).execute()
                    if res_key.data and len(res_key.data) > 0:
                        return True
            except Exception as e:
                logger.warning(f"Error checking payment event idempotency in Supabase: {e}")

        return False

    def record_payment_event(
        self,
        event_id: str,
        event_type: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        status: str = "processed"
    ) -> None:
        """Record processed payment event for auditability and idempotency."""
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "event_id": event_id,
            "idempotency_key": idempotency_key or event_id,
            "event_type": event_type,
            "payload": payload,
            "status": status,
            "processed_at": now,
            "created_at": now,
        }
        self._processed_events[event_id] = record
        if idempotency_key:
            self._processed_events[idempotency_key] = record

        if self._is_live_client and self._supabase:
            try:
                self._supabase.table("payment_events").insert(record).execute()
            except Exception as e:
                logger.warning(f"Error persisting payment event to Supabase: {e}")

    def update_subscription(
        self,
        user_id: str,
        plan: str,
        status: str = "active",
        stripe_customer_id: Optional[str] = None,
        stripe_subscription_id: Optional[str] = None,
        current_period_end: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update or create user subscription record."""
        now = datetime.now(timezone.utc).isoformat()
        sub_data = {
            "user_id": user_id,
            "plan": plan,
            "status": status,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "current_period_end": current_period_end,
            "updated_at": now,
        }
        self._subscriptions[user_id] = sub_data

        if self._is_live_client and self._supabase:
            try:
                self._supabase.table("subscriptions").upsert(
                    sub_data, on_conflict="user_id"
                ).execute()
            except Exception as e:
                logger.warning(f"Error persisting subscription to Supabase: {e}")

        return sub_data

    def get_user_subscription(self, user_id: str) -> Dict[str, Any]:
        """Get active user subscription plan."""
        if self._is_live_client and self._supabase:
            try:
                res = self._supabase.table("subscriptions").select("*").eq("user_id", user_id).execute()
                if res.data and len(res.data) > 0 and isinstance(res.data[0], dict):
                    return dict(res.data[0])
            except Exception as e:
                logger.warning(f"Error retrieving subscription from Supabase: {e}")

        return self._subscriptions.get(user_id, {
            "user_id": user_id,
            "plan": "free",
            "status": "active",
            "current_period_end": None,
        })

    def check_and_consume_quota(self, user_id: str, tokens: int = 0) -> Dict[str, Any]:
        """
        Enforce daily quota limits and atomically consume allowance.
        Free tier: 5 interviews, 50,000 tokens
        Pro tier: 100 interviews, 1,000,000 tokens
        """
        sub = self.get_user_subscription(user_id)
        plan = sub.get("plan", "free")
        status = sub.get("status", "active")

        if plan == "pro" and status == "active":
            interviews_limit = 100
            tokens_limit = 1000000
        elif plan == "enterprise" and status == "active":
            interviews_limit = 10000
            tokens_limit = 50000000
        else:
            interviews_limit = settings.default_free_interviews_limit
            tokens_limit = settings.default_free_tokens_limit

        # If live Supabase, call stored procedure check_and_increment_quota
        if self._is_live_client and self._supabase:
            try:
                rpc_res = self._supabase.rpc(
                    "check_and_increment_quota",
                    {"p_user_id": user_id, "p_tokens": tokens}
                ).execute()
                if isinstance(rpc_res.data, dict):
                    return dict(rpc_res.data)
            except Exception as e:
                logger.warning(f"Supabase RPC quota check fallback: {e}")

        # In-memory evaluation fallback
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        quota_key = f"{user_id}:{today}"
        quota = self._quotas.get(quota_key, {
            "user_id": user_id,
            "period_start": today,
            "interviews_taken": 0,
            "interviews_limit": interviews_limit,
            "tokens_consumed": 0,
            "tokens_limit": tokens_limit,
        })

        if quota["interviews_taken"] + 1 > interviews_limit or quota["tokens_consumed"] + tokens > tokens_limit:
            return {
                "allowed": False,
                "plan": plan,
                "reason": "Daily quota limit reached. Upgrade to Pro for unlimited access.",
                "interviews_taken": quota["interviews_taken"],
                "interviews_limit": interviews_limit,
                "tokens_consumed": quota["tokens_consumed"],
                "tokens_limit": tokens_limit,
            }

        quota["interviews_taken"] += 1
        quota["tokens_consumed"] += tokens
        quota["interviews_limit"] = interviews_limit
        quota["tokens_limit"] = tokens_limit
        self._quotas[quota_key] = quota

        return {
            "allowed": True,
            "plan": plan,
            "interviews_taken": quota["interviews_taken"],
            "interviews_limit": interviews_limit,
            "tokens_consumed": quota["tokens_consumed"],
            "tokens_limit": tokens_limit,
        }


billing_service = BillingService()
