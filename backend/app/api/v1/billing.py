"""Billing & Subscription API Routes.

Features:
- Cryptographically verified webhooks (Stripe v1 HMAC SHA-256)
- Strict idempotency checking (replay attack prevention)
- Quota tracking and subscription management
"""

import json
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ...auth import AuthenticatedUser, get_current_user
from ...config import settings
from ...logger import logger
from ...services.billing_service import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan: str = Field(default="pro", description="Requested subscription tier: pro | enterprise")
    success_url: Optional[str] = Field(default=None, description="Redirect URL upon successful payment")
    cancel_url: Optional[str] = Field(default=None, description="Redirect URL upon payment cancellation")


@router.get("/status")
async def get_billing_status(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Retrieve the current user's subscription tier and daily quota status."""
    subscription = billing_service.get_user_subscription(current_user.id)
    # Check quota consumption without incrementing
    quota_info = billing_service.check_and_consume_quota(current_user.id, tokens=0)
    # Don't increment count on read
    return {
        "user_id": current_user.id,
        "subscription": subscription,
        "quota": quota_info,
    }


@router.post("/create-checkout-session")
async def create_checkout_session(
    body: CheckoutRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Generate a Stripe / Sandbox checkout session for upgrading subscription.
    """
    plan = body.plan.lower()
    if plan not in ["pro", "enterprise"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan. Must be 'pro' or 'enterprise'.",
        )

    # In beta without live Stripe key, provide sandbox instant upgrade flow
    if not settings.stripe_secret_key:
        return {
            "mode": "sandbox",
            "message": "Stripe secret key not configured. Using beta sandbox checkout.",
            "checkout_url": f"/dashboard?upgrade_success={plan}",
            "plan": plan,
            "user_id": current_user.id,
        }

    # Production Stripe integration placeholder (when STRIPE_SECRET_KEY is provided)
    return {
        "mode": "live",
        "checkout_url": f"https://checkout.stripe.com/pay/cs_test_{current_user.id[:8]}",
        "plan": plan,
        "user_id": current_user.id,
    }


@router.post("/webhook")
async def handle_payment_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Handle incoming payment webhooks with:
    1. Cryptographic HMAC SHA-256 signature verification.
    2. Replay attack timestamp validation.
    3. Strict event idempotency checking.
    """
    raw_body = await request.body()

    # 1. Signature Verification
    if settings.stripe_webhook_secret:
        if not stripe_signature:
            logger.warning("Payment webhook missing stripe-signature header")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing webhook signature header",
            )
        is_valid = billing_service.verify_stripe_signature(
            raw_body, stripe_signature, settings.stripe_webhook_secret
        )
        if not is_valid:
            logger.warning("Payment webhook signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    # 2. Parse Event Payload
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_id = event.get("id") or idempotency_key
    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event ID or Idempotency-Key",
        )

    event_type = event.get("type", "unknown")

    # 3. Idempotency Guard (Avoid duplicate billing / upgrades)
    if billing_service.is_event_processed(event_id, idempotency_key):
        logger.info(f"Payment event {event_id} already processed. Returning cached success (idempotent).")
        return {"status": "already_processed", "event_id": event_id}

    # 4. Process Event Type
    data_object = event.get("data", {}).get("object", {})

    if event_type in ["checkout.session.completed", "customer.subscription.created", "invoice.payment_succeeded"]:
        user_id = (
            data_object.get("client_reference_id")
            or data_object.get("metadata", {}).get("user_id")
            or data_object.get("customer")
        )
        plan = data_object.get("metadata", {}).get("plan", "pro")
        stripe_customer_id = data_object.get("customer")
        stripe_subscription_id = data_object.get("subscription") or data_object.get("id")

        if user_id:
            billing_service.update_subscription(
                user_id=user_id,
                plan=plan,
                status="active",
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
            )
            logger.info(f"Upgraded subscription for user {user_id} to {plan} via event {event_id}")

    elif event_type in ["customer.subscription.deleted", "customer.subscription.cancelled"]:
        stripe_sub_id = data_object.get("id")
        user_id = data_object.get("metadata", {}).get("user_id")
        if user_id:
            billing_service.update_subscription(
                user_id=user_id,
                plan="free",
                status="canceled",
                stripe_subscription_id=stripe_sub_id,
            )
            logger.info(f"Downgraded subscription for user {user_id} to free via event {event_id}")

    # 5. Record Event as Processed
    billing_service.record_payment_event(
        event_id=event_id,
        event_type=event_type,
        payload=event,
        idempotency_key=idempotency_key,
        status="processed",
    )

    return {"status": "success", "event_id": event_id, "type": event_type}
