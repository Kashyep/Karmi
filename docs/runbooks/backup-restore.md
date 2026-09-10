# Backup and restore runbook

This procedure is prepared but has not been executed against production infrastructure.

1. Quiesce writes or capture a transactionally consistent PostgreSQL backup plus an object-store
   inventory at the same release marker. Record schema revision and encryption/key references.
2. Create a new isolated database and private object prefix. Confirm the target names explicitly;
   never restore over the source.
3. Restore PostgreSQL, run `alembic current`, then restore referenced objects without public ACLs.
4. Start workers with outbound delivery, checkout, live models and WhatsApp disabled.
5. Verify synthetic ownership boundaries, tasks/reminders, reservations, inbox/outbox state and
   object references. Reconcile executing/unknown actions before enabling delivery.
6. Destroy the isolated restore only after evidence is saved under `docs/release-evidence/`.

Backup retention must respect deletion policy. Restoring an old backup must reapply deletion
tombstones before retrieval/indexing to prevent deleted content from reappearing.

