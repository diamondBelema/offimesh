"""Reconciliation Celery worker for nightly diff checks."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import structlog

from app.core.database import get_session_context
from app.core.logging import get_logger
from app.integrations.nomba import get_nomba_transactions_client
from app.repositories.settlement_repository import SettlementRepository
from app.repositories.token_repository import TokenRepository
from app.repositories.transaction_repository import TransactionRepository
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.reconciliation_worker.run_reconciliation",
    bind=True,
)
def run_reconciliation(self, days_back: int = 1) -> dict:
    """
    Nightly reconciliation job.

    Pulls transactions from Nomba for the date range and diffs
    against our local ledger by merchantTxRef.

    CRITICAL: This is the most important safeguard against silent money loss.
    """
    import asyncio

    async def _reconcile():
        async with get_session_context() as db:
            # Get date range
            end_date = date.today()
            start_date = end_date - timedelta(days=days_back)

            logger.info(
                "reconciliation_started",
                start_date=str(start_date),
                end_date=str(end_date),
            )

            # Get Nomba transactions
            nomba_client = get_nomba_transactions_client()
            nomba_txs, total = await nomba_client.list_transactions(
                date_from=start_date,
                date_to=end_date,
            )

            # Build lookup by our reference
            nomba_by_ref = {}
            for tx in nomba_txs:
                if tx.reference:  # merchantTxRef
                    nomba_by_ref[tx.reference] = tx

            # Get our local transactions for the period
            tx_repo = TransactionRepository(db)
            local_txs, _ = await tx_repo.list_all(
                page=1,
                page_size=1000,
                status=None,
            )

            # Diff findings
            missing_in_local = []  # In Nomba but not ours (shouldn't happen)
            missing_in_nomba = []  # In ours but not Nomba's
            status_mismatches = []  # Different status
            amount_mismatches = []  # Different amount

            # Build local lookup
            local_by_ref = {tx.tx_id: tx for tx in local_txs}

            # Check: Nomba transactions missing in local
            for ref, nomba_tx in nomba_by_ref.items():
                if ref not in local_by_ref:
                    missing_in_local.append({
                        "tx_id": ref,
                        "nomba_id": nomba_tx.transaction_id,
                        "amount": nomba_tx.amount,
                        "status": nomba_tx.status,
                    })

            # Check: Local transactions missing in Nomba
            for tx in local_txs:
                if tx.tx_id not in nomba_by_ref:
                    # Settlement might still be pending
                    if tx.status not in ("verified", "settling"):
                        missing_in_nomba.append({
                            "tx_id": tx.tx_id,
                            "status": tx.status,
                            "amount": tx.amount_kobo,
                        })
                else:
                    # Check for mismatches
                    nomba_tx = nomba_by_ref[tx.tx_id]
                    if tx.amount_kobo != nomba_tx.amount:
                        amount_mismatches.append({
                            "tx_id": tx.tx_id,
                            "local_amount": tx.amount_kobo,
                            "nomba_amount": nomba_tx.amount,
                        })

            result = {
                "date_range": f"{start_date} to {end_date}",
                "nomba_transactions": len(nomba_txs),
                "local_transactions": len(local_txs),
                "missing_in_local": missing_in_local,
                "missing_in_nomba": missing_in_nomba,
                "status_mismatches": status_mismatches,
                "amount_mismatches": amount_mismatches,
                "has_discrepancies": bool(
                    missing_in_local or missing_in_nomba or amount_mismatches
                ),
            }

            if result["has_discrepancies"]:
                logger.error("reconciliation_discrepancies_found", **result)
                # TODO: Send alert email/notification
            else:
                logger.info("reconciliation_passed", **result)

            return result

    return asyncio.run(_reconcile())


@celery_app.task(
    name="app.workers.reconciliation_worker.expire_tokens",
    bind=True,
)
def expire_tokens(self) -> int:
    """
    Mark expired offline tokens.

    Runs hourly to clean up tokens past their TTL.
    """
    import asyncio

    async def _expire():
        async with get_session_context() as db:
            token_repo = TokenRepository(db)
            count = await token_repo.expire_tokens()

            logger.info("tokens_expired", count=count)
            return count

    return asyncio.run(_expire())


@celery_app.task(
    name="app.workers.reconciliation_worker.check_stale_settlements",
    bind=True,
)
def check_stale_settlements(self, hours: int = 24) -> dict:
    """
    Check for transactions stuck in 'settling' state.

    These may need manual intervention or retry.
    """
    import asyncio

    async def _check():
        async with get_session_context() as db:
            tx_repo = TransactionRepository(db)
            settlement_repo = SettlementRepository(db)

            from datetime import datetime, timezone, timedelta

            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

            # Find transactions in 'settling' state older than cutoff
            from sqlalchemy import select
            from app.models.transaction import Transaction

            result = await db.execute(
                select(Transaction).where(
                    Transaction.status == "settling",
                    Transaction.updated_at < cutoff,
                )
            )
            stale = result.scalars().all()

            logger.warning("stale_settlements_found", count=len(stale), hours=hours)

            return {
                "stale_count": len(stale),
                "tx_ids": [tx.tx_id for tx in stale],
            }

    return asyncio.run(_check())


@celery_app.task(
    name="app.workers.reconciliation_worker.sync_transaction_status",
    bind=True,
)
def sync_transaction_status(self, tx_id: str) -> dict:
    """
    Sync transaction status from Nomba.

    Used for specific transaction status checks.
    """
    import asyncio

    async def _sync():
        async with get_session_context() as db:
            nomba_client = get_nomba_transactions_client()
            nomba_tx = await nomba_client.get_transaction(tx_id)

            if not nomba_tx:
                logger.warning("transaction_not_in_nomba", tx_id=tx_id)
                return {"found": False}

            tx_repo = TransactionRepository(db)
            local_tx = await tx_repo.get_by_tx_id(tx_id)

            if not local_tx:
                return {"found": False, "in_nomba": True}

            # Check if status needs updating
            if local_tx.status != nomba_tx.status:
                await tx_repo.update_status(tx_id, nomba_tx.status)
                logger.info(
                    "transaction_status_synced",
                    tx_id=tx_id,
                    old_status=local_tx.status,
                    new_status=nomba_tx.status,
                )

            return {
                "found": True,
                "local_status": local_tx.status,
                "nomba_status": nomba_tx.status,
            }

    return asyncio.run(_sync())
