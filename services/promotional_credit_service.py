"""Transactional promotional-credit operations for the Version 3 pilot."""

from database import (
    Transaction,
    TX_PROMOTIONAL_ENTRY,
    TX_PROMOTIONAL_ENTRY_REVERSAL,
    db,
)


def _entry_reference(player_id, tournament_id):
    return f'pilot-entry:{tournament_id}:{player_id}'


def debit_tournament_entry(player, amount, tournament_id):
    """Debit one pilot entry without committing the surrounding transaction."""
    amount = round(float(amount), 2)
    reference = _entry_reference(player.id, tournament_id)
    existing = Transaction.query.filter_by(
        external_ref_id=reference,
        transaction_type=TX_PROMOTIONAL_ENTRY,
        status='completed',
    ).first()
    if existing is not None:
        return {
            'debited': False,
            'transaction': existing,
            'balance': float(player.promotional_credit_balance or 0.0),
        }

    if amount <= 0:
        raise ValueError('Pilot tournament entry cost must be greater than zero')
    if not player.has_active_promotional_credits():
        raise ValueError('Promotional credits have expired')

    balance_before = round(float(player.promotional_credit_balance or 0.0), 2)
    if balance_before < amount:
        raise ValueError('Insufficient promotional credit')

    player.promotional_credit_balance = round(balance_before - amount, 2)
    transaction = Transaction(
        player_id=player.id,
        external_ref_id=reference,
        status='completed',
        transaction_type=TX_PROMOTIONAL_ENTRY,
        amount=amount,
        balance_type='promotional',
        balance_before=balance_before,
        balance_after=player.promotional_credit_balance,
        tournament_id=tournament_id,
        description=f'Pilot tournament entry #{tournament_id}',
    )
    db.session.add(transaction)
    db.session.flush()
    return {
        'debited': True,
        'transaction': transaction,
        'balance': player.promotional_credit_balance,
    }


def reverse_tournament_entry(player, amount, tournament_id):
    """Reverse a promotional entry once, without changing its original expiry."""
    amount = round(float(amount), 2)
    entry_reference = _entry_reference(player.id, tournament_id)
    reversal_reference = f'pilot-reversal:{tournament_id}:{player.id}'
    original = Transaction.query.filter_by(
        external_ref_id=entry_reference,
        transaction_type=TX_PROMOTIONAL_ENTRY,
        status='completed',
    ).first()
    existing = Transaction.query.filter_by(
        external_ref_id=reversal_reference,
        transaction_type=TX_PROMOTIONAL_ENTRY_REVERSAL,
        status='completed',
    ).first()
    if original is None or existing is not None:
        return False

    balance_before = round(float(player.promotional_credit_balance or 0.0), 2)
    player.promotional_credit_balance = round(balance_before + amount, 2)
    db.session.add(Transaction(
        player_id=player.id,
        external_ref_id=reversal_reference,
        status='completed',
        transaction_type=TX_PROMOTIONAL_ENTRY_REVERSAL,
        amount=amount,
        balance_type='promotional',
        balance_before=balance_before,
        balance_after=player.promotional_credit_balance,
        tournament_id=tournament_id,
        description=f'Pilot tournament entry reversal #{tournament_id}',
    ))
    db.session.flush()
    return True
