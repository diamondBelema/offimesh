"""Celery application configuration."""
from __future__ import annotations

from celery import Celery

from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "offimesh",
    broker=settings.celery_broker_url,
    backend=settings.celery_broker_url,  # Use Redis as result backend too
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task routing
    task_routes={
        "app.workers.settlement_worker.*": {"queue": "settlement"},
        "app.workers.webhook_worker.*": {"queue": "webhook"},
        "app.workers.reconciliation_worker.*": {"queue": "reconciliation"},
    },

    # Task defaults
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,
    task_time_limit=300,  # 5 minutes hard limit
    task_soft_time_limit=240,  # 4 minutes soft limit

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour

    # Worker settings
    worker_prefetch_multiplier=1,  # One task per worker at a time
    worker_concurrency=4,

    # Beat schedule for periodic tasks
    beat_schedule={
        "expire-tokens-every-hour": {
            "task": "app.workers.token_expiry_worker.expire_tokens",
            "schedule": 3600.0,  # Every hour
        },
        "apply-spend-cutoffs": {
            "task": "app.workers.token_cutoff_worker.apply_spend_cutoffs",
            "schedule": 900.0,  # Every 15 minutes
        },
        "scan-for-blacklist-candidates": {
            "task": "app.workers.blacklist_worker.scan_for_blacklist_candidates",
            "schedule": 1800.0,  # Every 30 minutes
        },
        "recalculate-device-trust-scores": {
            "task": "app.workers.device_trust_recalc_worker.recalculate_all_trust_scores",
            "schedule": 86400.0,  # Every 24 hours
        },
        "reconciliation-nightly": {
            "task": "app.workers.reconciliation_worker.run_reconciliation",
            "schedule": 86400.0,  # Every 24 hours
            "args": (),
        },
        "retry-failed-settlements": {
            "task": "app.workers.settlement_worker.retry_failed_settlements",
            "schedule": 300.0,  # Every 5 minutes
        },
    },
)

# Autodiscover tasks
celery_app.autodiscover_tasks([
    "app.workers.settlement_worker",
    "app.workers.webhook_worker",
    "app.workers.reconciliation_worker",
    "app.workers.token_expiry_worker",
    "app.workers.token_cutoff_worker",
    "app.workers.blacklist_worker",
    "app.workers.device_trust_recalc_worker",
])
