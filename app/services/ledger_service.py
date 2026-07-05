"""Ledger service for double-entry bookkeeping."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import InsufficientFundsError, ValidationError
from app.models.audit import AuditLog
from app.models.ledger_balance import LedgerBalance
from app.models.ledger_entry import EntryType, ReferenceType
from app.models.ledger_entry import LedgerEntry as LedgerEntryModel
from app.repositories.audit_repository import AuditRepository

logger = structlog.get_logger(__name__)


class LedgerService:
    """
    Double-entry ledger service for all money movements.

    CRITICAL: Every balance change goes through this service.
    All operations are atomic - nothing partial happens.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit_repo = AuditRepository(db)

    async def get_or_create_balance(self, user_id: uuid.UUID) -> LedgerBalance:
        """Get or create ledger balance for user."""
        result = await self.db.execute(
            select(LedgerBalance).where(LedgerBalance.user_id == user_id)
        )
        balance = result.scalar_one_or_none()

        if not balance:
            balance = LedgerBalance(
                user_id=user_id,
                available_balance_kobo=0,
                locked_in_offline_tokens_kobo=0,
            )
            self.db.add(balance)
            await self.db.flush()

        return balance

    async def credit(
        self,
        user_id: uuid.UUID,
        amount_kobo: int,
        reference_type: str,
        reference_id: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
        correlation_id: str | None = None,
    ) -> LedgerBalance:
        """
        Credit (add money) to a user's balance.

        Writes both the balance update AND a ledger entry.
        """
        if amount_kobo <= 0:
            raise ValidationError("Amount must be positive")

        balance = await self.get_or_create_balance(user_id)

        # Update balance
        balance.available_balance_kobo += amount_kobo
        balance.updated_at = datetime.now(timezone.utc)

        # Create ledger entry
        entry = LedgerEntryModel(
            user_id=user_id,
            entry_type=EntryType.credit.value,
            amount_kobo=amount_kobo,
            reference_type=reference_type,
            reference_id=reference_id,
            balance_after_kobo=balance.available_balance_kobo,
            description=description,
            metadata=metadata,
        )
        self.db.add(entry)

        await self.db.flush()

        logger.info(
            "ledger_credit",
            user_id=str(user_id),
            amount_kobo=amount_kobo,
            reference_type=reference_type,
            balance_after=balance.available_balance_kobo,
        )

        return balance

    async def debit(
        self,
        user_id: uuid.UUID,
        amount_kobo: int,
        reference_type: str,
        reference_id: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
        allow_overdraft: bool = False,
        correlation_id: str | None = None,
    ) -> LedgerBalance:
        """
        Debit (subtract money) from a user's balance.

        Raises InsufficientFundsError if not enough balance.
        """
        if amount_kobo <= 0:
            raise ValidationError("Amount must be positive")

        balance = await self.get_or_create_balance(user_id)

        if not allow_overdraft and balance.available_balance_kobo < amount_kobo:
            raise InsufficientFundsError(
                required=amount_kobo,
                available=balance.available_balance_kobo,
            )

        # Update balance
        balance.available_balance_kobo -= amount_kobo
        balance.updated_at = datetime.now(timezone.utc)

        # Create ledger entry
        entry = LedgerEntryModel(
            user_id=user_id,
            entry_type=EntryType.debit.value,
            amount_kobo=amount_kobo,
            reference_type=reference_type,
            reference_id=reference_id,
            balance_after_kobo=balance.available_balance_kobo,
            description=description,
            metadata=metadata,
        )
        self.db.add(entry)

        await self.db.flush()

        logger.info(
            "ledger_debit",
            user_id=str(user_id),
            amount_kobo=amount_kobo,
            reference_type=reference_type,
            balance_after=balance.available_balance_kobo,
        )

        return balance

    async def transfer(
        self,
        from_user_id: uuid.UUID,
        to_user_id: uuid.UUID,
        amount_kobo: int,
        reference_type: str,
        reference_id: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
        correlation_id: str | None = None,
    ) -> tuple[LedgerBalance, LedgerBalance]:
        """
        Transfer money between users atomically.

        Used for P2P settlements - debits one user, credits another.
        All in a single transaction.
        """
        if amount_kobo <= 0:
            raise ValidationError("Amount must be positive")

        # Both operations happen in this transaction
        from_balance = await self.debit(
            user_id=from_user_id,
            amount_kobo=amount_kobo,
            reference_type=reference_type,
            reference_id=reference_id,
            description=f"Transfer to {to_user_id}: {description}",
            metadata=metadata,
            correlation_id=correlation_id,
        )

        to_balance = await self.credit(
            user_id=to_user_id,
            amount_kobo=amount_kobo,
            reference_type=reference_type,
            reference_id=reference_id,
            description=f"Transfer from {from_user_id}: {description}",
            metadata=metadata,
            correlation_id=correlation_id,
        )

        logger.info(
            "ledger_transfer",
            from_user=str(from_user_id),
            to_user=str(to_user_id),
            amount_kobo=amount_kobo,
            reference_type=reference_type,
        )

        return from_balance, to_balance

    async def lock_for_offline_token(
        self,
        user_id: uuid.UUID,
        amount_kobo: int,
        token_id: str,
        correlation_id: str | None = None,
    ) -> LedgerBalance:
        """
        Lock funds for offline token issuance.

        Moves from available to locked_in_offline_tokens.
        """
        if amount_kobo <= 0:
            raise ValidationError("Amount must be positive")

        balance = await self.get_or_create_balance(user_id)

        if balance.available_balance_kobo < amount_kobo:
            raise InsufficientFundsError(
                required=amount_kobo,
                available=balance.available_balance_kobo,
            )

        # Move from available to locked
        balance.available_balance_kobo -= amount_kobo
        balance.locked_in_offline_tokens_kobo += amount_kobo
        balance.updated_at = datetime.now(timezone.utc)

        # Create ledger entry
        entry = LedgerEntryModel(
            user_id=user_id,
            entry_type=EntryType.debit.value,
            amount_kobo=amount_kobo,
            reference_type=ReferenceType.offline_token_issue.value,
            reference_id=token_id,
            balance_after_kobo=balance.available_balance_kobo,
            description="Locked for offline token",
        )
        self.db.add(entry)

        await self.db.flush()

        logger.info(
            "ledger_lock_offline",
            user_id=str(user_id),
            amount_kobo=amount_kobo,
            token_id=token_id,
            available=balance.available_balance_kobo,
            locked=balance.locked_in_offline_tokens_kobo,
        )

        return balance

    async def unlock_and_refund(
        self,
        user_id: uuid.UUID,
        amount_kobo: int,
        token_id: str,
        correlation_id: str | None = None,
    ) -> LedgerBalance:
        """
        Refund unused offline token balance to user.

        Moves from locked_in_offline_tokens back to available.
        """
        if amount_kobo <= 0:
            return await self.get_or_create_balance(user_id)

        balance = await self.get_or_create_balance(user_id)

        # Move from locked to available
        refund_amount = min(amount_kobo, balance.locked_in_offline_tokens_kobo)
        balance.locked_in_offline_tokens_kobo -= refund_amount
        balance.available_balance_kobo += refund_amount
        balance.updated_at = datetime.now(timezone.utc)

        # Create ledger entry
        entry = LedgerEntryModel(
            user_id=user_id,
            entry_type=EntryType.credit.value,
            amount_kobo=refund_amount,
            reference_type=ReferenceType.offline_token_refund.value,
            reference_id=token_id,
            balance_after_kobo=balance.available_balance_kobo,
            description="Refund from expired offline token",
        )
        self.db.add(entry)

        await self.db.flush()

        logger.info(
            "ledger_refund_offline",
            user_id=str(user_id),
            amount_kobo=refund_amount,
            token_id=token_id,
            available=balance.available_balance_kobo,
            locked=balance.locked_in_offline_tokens_kobo,
        )

        return balance

    async def get_balance(self, user_id: uuid.UUID) -> dict:
        """Get user's current balance."""
        balance = await self.get_or_create_balance(user_id)
        return {
            "available_kobo": balance.available_balance_kobo,
            "locked_kobo": balance.locked_in_offline_tokens_kobo,
            "total_kobo": balance.total_balance_kobo,
        }

    async def verify_balance_integrity(self, user_id: uuid.UUID) -> bool:
        """
        Verify that balance matches sum of entries.

        This is the reconciliation safety net.
        """
        balance = await self.get_or_create_balance(user_id)

        # Sum all credit entries
        credit_result = await self.db.execute(
            select(LedgerEntryModel).where(
                LedgerEntryModel.user_id == user_id,
                LedgerEntryModel.entry_type == EntryType.credit.value,
            )
        )
        total_credits = sum(e.amount_kobo for e in credit_result.scalars().all())

        # Sum all debit entries
        debit_result = await self.db.execute(
            select(LedgerEntryModel).where(
                LedgerEntryModel.user_id == user_id,
                LedgerEntryModel.entry_type == EntryType.debit.value,
            )
        )
        total_debits = sum(e.amount_kobo for e in debit_result.scalars().all())

        calculated = total_credits - total_debits
        expected = balance.available_balance_kobo + balance.locked_in_offline_tokens_kobo

        if calculated != expected:
            logger.error(
                "ledger_integrity_mismatch",
                user_id=str(user_id),
                calculated=calculated,
                expected=expected,
                credits=total_credits,
                debits=total_debits,
            )
            return False

        return True
