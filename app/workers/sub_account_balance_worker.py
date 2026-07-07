"""Sub-account balance snapshot worker for treasury reconciliation."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, func

from app.core.database import get_session_context
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.ledger_balance import LedgerBalance
from app.models.nomba_sub_account import NombaSubAccount, SubAccountBalanceSnapshot
from app.repositories.audit_repository import AuditRepository
from app.integrations.nomba.sub_accounts import get_nomba_sub_accounts_client
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.sub_account_balance_worker.capture_balance_snapshot",
    bind=True,
)
def capture_balance_snapshot(self) -> dict:
    """
    Capture daily balance snapshot of Nomba sub-account for reconciliation.

    Compares Nomba's reported treasury balance against our internal
    ledger_balances sum to detect any drift.

    Runs daily via Celery Beat.
    """
    import asyncio

    async def _capture():
        async with get_session_context() as db:
            # Get our operational sub-account
            result = await db.execute(
                select(NombaSubAccount).where(
                    NombaSubAccount.purpose == "operational_treasury"
                )
            )
            sub_account = result.scalar_one_or_none()

            if not sub_account:
                logger.warning("no_treasury_sub_account_found")
                return {
                    "status": "skipped",
                    "reason": "No treasury sub-account configured",
                }

            # Get balance from Nomba
            nomba_client = get_nomba_sub_accounts_client()
            try:
                balance_data = await nomba_client.get_sub_account_balance(
                    sub_account.nomba_sub_account_id
                )
                nomba_balance_kobo = balance_data.get("balance", 0)
            except Exception as e:
                logger.error(
                    "nomba_balance_fetch_failed",
                    sub_account_id=str(sub_account.id),
                    error=str(e),
                )
                return {
                    "status": "failed",
                    "reason": f"Nomba API error: {str(e)}",
                }

            # Get our internal ledger total
            ledger_result = await db.execute(
                select(func.sum(LedgerBalance.available_balance_kobo))
            )
            ledger_total = ledger_result.scalar() or 0

            # Also get locked amounts
            locked_result = await db.execute(
                select(func.sum(LedgerBalance.locked_in_offline_tokens_kobo))
            )
            locked_total = locked_result.scalar() or 0

            internal_total = ledger_total + locked_total

            # Calculate discrepancy
            discrepancy = nomba_balance_kobo - internal_total

            # Create snapshot record
            snapshot = SubAccountBalanceSnapshot(
                sub_account_id=sub_account.id,
                balance_kobo=nomba_balance_kobo,
                ledger_total_kobo=internal_total,
                discrepancy_kobo=discrepancy,
            )
            db.add(snapshot)

            # Audit log
            audit_repo = AuditRepository(db)
            await audit_repo.create(AuditLog(
                actor_type="system",
                actor_id="balance_snapshot_worker",
                action="treasury.balance_snapshot",
                resource="sub_account_balance_snapshot",
                resource_id=str(snapshot.id),
                metadata={
                    "nomba_balance_kobo": nomba_balance_kobo,
                    "ledger_total_kobo": internal_total,
                    "discrepancy_kobo": discrepancy,
                },
            ))

            await db.commit()

            if discrepancy != 0:
                logger.warning(
                    "treasury_discrepancy_detected",
                    nomba_balance=nomba_balance_kobo,
                    ledger_total=internal_total,
                    discrepancy=discrepancy,
                )
            else:
                logger.info(
                    "treasury_balanced",
                    balance=nomba_balance_kobo,
                    ledger_total=internal_total,
                )

            return {
                "status": "success",
                "nomba_balance_kobo": nomba_balance_kobo,
                "ledger_total_kobo": internal_total,
                "discrepancy_kobo": discrepancy,
            }

    return asyncio.run(_capture())


@celery_app.task(
    name="app.workers.sub_account_balance_worker.ensure_treasury_sub_account",
    bind=True,
    max_retries=3,
)
def ensure_treasury_sub_account(self) -> dict:
    """
    Ensure the operational treasury sub-account exists.

    Creates it if it doesn't exist. Should be called on startup/deploy.
    """
    import asyncio

    async def _ensure():
        async with get_session_context() as db:
            # Check if sub-account already exists in DB
            result = await db.execute(
                select(NombaSubAccount).where(
                    NombaSubAccount.purpose == "operational_treasury"
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                return {
                    "status": "exists",
                    "sub_account_id": str(existing.id),
                    "account_ref": existing.account_ref,
                }

            # Need to create it
            account_ref = "offimesh_operational_treasury"
            account_name = "OffiMesh Operational Treasury"

            nomba_client = get_nomba_sub_accounts_client()
            try:
                nomba_data = await nomba_client.create_sub_account(
                    account_name=account_name,
                    account_ref=account_ref,
                )

                nomba_sub_account_id = nomba_data.get("id") or nomba_data.get("accountId")

                if not nomba_sub_account_id:
                    raise ValueError("No sub-account ID returned from Nomba")

                # Save to our database
                sub_account = NombaSubAccount(
                    nomba_sub_account_id=nomba_sub_account_id,
                    account_ref=account_ref,
                    account_name=account_name,
                    purpose="operational_treasury",
                )
                db.add(sub_account)

                # Audit log
                audit_repo = AuditRepository(db)
                await audit_repo.create(AuditLog(
                    actor_type="system",
                    actor_id="sub_account_setup",
                    action="treasury.sub_account_created",
                    resource="nomba_sub_account",
                    resource_id=str(sub_account.id),
                    metadata={
                        "nomba_id": nomba_sub_account_id,
                        "account_ref": account_ref,
                    },
                ))

                await db.commit()

                logger.info(
                    "treasury_sub_account_created",
                    sub_account_id=str(sub_account.id),
                    nomba_id=nomba_sub_account_id,
                )

                return {
                    "status": "created",
                    "sub_account_id": str(sub_account.id),
                    "nomba_sub_account_id": nomba_sub_account_id,
                    "account_ref": account_ref,
                }

            except Exception as e:
                logger.error(
                    "treasury_sub_account_creation_failed",
                    error=str(e),
                )
                raise

    try:
        return asyncio.run(_ensure())
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@celery_app.task(
    name="app.workers.sub_account_balance_worker.get_reconciliation_report",
    bind=True,
)
def get_reconciliation_report(self, days: int = 7) -> dict:
    """
    Get reconciliation report for the last N days.

    Shows trend of discrepancies between Nomba and internal ledger.
    """
    import asyncio
    from datetime import timedelta

    async def _report():
        async with get_session_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            result = await db.execute(
                select(SubAccountBalanceSnapshot)
                .where(SubAccountBalanceSnapshot.captured_at >= cutoff)
                .order_by(SubAccountBalanceSnapshot.captured_at.asc())
            )
            snapshots = result.scalars().all()

            if not snapshots:
                return {
                    "days": days,
                    "snapshots": [],
                    "total_discrepancy": 0,
                    "avg_discrepancy": 0,
                }

            discrepancies = [s.discrepancy_kobo or 0 for s in snapshots]

            return {
                "days": days,
                "snapshot_count": len(snapshots),
                "snapshots": [
                    {
                        "captured_at": s.captured_at.isoformat(),
                        "nomba_balance_kobo": s.balance_kobo,
                        "ledger_total_kobo": s.ledger_total_kobo,
                        "discrepancy_kobo": s.discrepancy_kobo,
                    }
                    for s in snapshots
                ],
                "total_discrepancy": discrepancies[-1] if discrepancies else 0,
                "avg_discrepancy": sum(discrepancies) // len(discrepancies) if discrepancies else 0,
                "has_discrepancies": any(d != 0 for d in discrepancies),
            }

    return asyncio.run(_report())
