-- V3-0119: exact and atomic MojaPOS callback reconciliation.
-- Apply during a payment-free maintenance window and resolve any duplicate
-- non-null references before creating the two unique indexes.

ALTER TABLE transactions ADD COLUMN gateway_transaction_id VARCHAR(255);
ALTER TABLE transactions ADD COLUMN currency VARCHAR(3) DEFAULT 'SZL';
ALTER TABLE transactions ADD COLUMN payment_environment VARCHAR(20);
ALTER TABLE transactions ADD COLUMN reconciled_at DATETIME;
ALTER TABLE transactions ADD COLUMN reconciliation_code VARCHAR(40);

CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_external_ref_id
    ON transactions (external_ref_id)
    WHERE external_ref_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_gateway_transaction_id
    ON transactions (gateway_transaction_id)
    WHERE gateway_transaction_id IS NOT NULL;
