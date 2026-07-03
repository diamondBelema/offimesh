"""Wallet and virtual account service."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.integrations.nomba import get_nomba_virtual_accounts_client
from app.models.audit import AuditLog
from app.models.virtual_account import VirtualAccount
from app.repositories.audit_repository import AuditRepository
from app.repositories.user_repository import UserRepository
from app.repositories.virtual_account_repository import VirtualAccountRepository

logger = structlog.get_logger(__name__)


class WalletService:
    """Service for wallet funding and balance management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.virtual_account_repo = VirtualAccountRepository(db)
        self.audit_repo = AuditRepository(db)

    async def create_funding_account(
        self,
        user_id: str,
        expected_amount_kobo: int | None = None,
        correlation_id: str | None = None,
    ) -> VirtualAccount:
        """
        Create a virtual NUBAN account for wallet funding.

        User can transfer to this NUBAN from any Nigerian bank.
        """
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        # Generate unique account reference
        account_ref = f"user_{user_id}_{int(datetime.now(timezone.utc).timestamp())}"
        account_name = f"OffiMesh - {user.name or 'User'}"

        # Create virtual account with Nomba
        nomba_client = get_nomba_virtual_accounts_client()
        nomba_account = await nomba_client.create_virtual_account(
            account_ref=account_ref,
            account_name=account_name,
            amount=expected_amount_kobo,
        )

        # Store in our database
        virtual_account = VirtualAccount(
            user_id=user.id,
            nomba_account_id=nomba_account.account_id,
            account_ref=account_ref,
            nuban=nomba_account.account_number,
            account_name=nomba_account.account_name,
            bank_name=nomba_account.bank_name,
            expected_amount_kobo=expected_amount_kobo,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        await self.virtual_account_repo.create(virtual_account)

        # Link to user
        await self.user_repo.set_nomba_account(user.id, nomba_account.account_id)

        # Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="user",
            actor_id=user_id,
            action="wallet.funding_account_created",
            resource="virtual_account",
            resource_id=str(virtual_account.id),
            correlation_id=correlation_id,
        ))

        logger.info(
            "virtual_account_created",
            user_id=user_id,
            nuban=nomba_account.account_number,
        )

        return virtual_account

    async def get_funding_account(self, account_id: str) -> VirtualAccount | None:
        """Get virtual account by ID."""
        return await self.virtual_account_repo.get_by_id(uuid.UUID(account_id))

    async def process_funding(
        self,
        nomba_account_id: str,
        amount_received_kobo: int,
        transaction_reference: str,
        correlation_id: str | None = None,
    ) -> dict:
        """
        Process wallet funding from virtual_account.funded webhook.

        Handles over-payment, under-payment, and expected amount matching.
        """
        virtual_account = await self.virtual_account_repo.get_by_nomba_account_id(
            nomba_account_id
        )
        if not virtual_account:
            logger.warning(
                "funding_account_not_found",
                nomba_account_id=nomba_account_id,
            )
            return {"status": "ignored", "reason": "account_not_found"}

        user = await self.user_repo.get_by_id(virtual_account.user_id)
        if not user:
            return {"status": "ignored", "reason": "user_not_found"}

        expected = virtual_account.expected_amount_kobo
        received = amount_received_kobo

        # Determine funding status
        funding_status = "funded"
        if expected:
            if received < expected:
                funding_status = "underpaid"
                logger.warning(
                    "wallet_underpaid",
                    user_id=str(user.id),
                    expected=expected,
                    received=received,
                )
            elif received > expected:
                funding_status = "overpaid"
                logger.info(
                    "wallet_overpaid",
                    user_id=str(user.id),
                    expected=expected,
                    received=received,
                )

        # Update virtual account
        await self.virtual_account_repo.mark_funded(
            virtual_account.id,
            received,
            funding_status,
        )

        # Credit user wallet
        user.balance_kobo += received
        await self.user_repo.update(user)

        # Audit log
        await self.audit_repo.create(AuditLog(
            actor_type="system",
            actor_id="nomba_webhook",
            action="wallet.funded",
            resource="user",
            resource_id=str(user.id),
            metadata={
                "amount_kobo": received,
                "nomba_account_id": nomba_account_id,
                "transaction_reference": transaction_reference,
                "funding_status": funding_status,
            },
            correlation_id=correlation_id,
        ))

        logger.info(
            "wallet_credited",
            user_id=str(user.id),
            amount_kobo=received,
            new_balance=user.balance_kobo,
        )

        return {
            "status": "credited",
            "user_id": str(user.id),
            "amount_kobo": received,
            "funding_status": funding_status,
            "new_balance_kobo": user.balance_kobo,
        }

    async def get_balance(self, user_id: str) -> dict:
        """Get user wallet balance."""
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")

        return {
            "balance_kobo": user.balance_kobo,
            "available_kobo": user.balance_kobo,  # Could deduct pending settlements
            "pending_kobo": 0,
        }
