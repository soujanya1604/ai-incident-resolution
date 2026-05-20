# Incident Report 002 — Timeout Cascade Under Traffic Spike

**Date:** 2025-01-28  
**Service:** checkout-db  
**Severity:** High  
**Duration:** 1h 12m

## Summary

During a marketing traffic spike, checkout service reported `database connection timeout on checkout` errors. Errors cascaded from PgBouncer wait queue to application pool timeouts.

## Timeline

- 18:00 UTC — Traffic 3× baseline
- 18:12 UTC — `cl_waiting` elevated on PgBouncer (checkout pool)
- 18:18 UTC — App logs: `connection timed out` after 30s pool_timeout
- 19:24 UTC — Stabilized after increasing PgBouncer `default_pool_size` and enabling rate limiting

## Root Cause

PgBouncer `default_pool_size=25` was insufficient for burst. Clients queued at bouncer; app pools exhausted waiting for bouncer connections. Long-running report queries (analytics job) held 12 server connections idle in transaction.

## Resolution Steps (proven)

1. Increased PgBouncer `default_pool_size` 25 → 40
2. Set `reserve_pool_size=10` for bursts
3. Moved analytics queries to read replica
4. Added `idle_in_transaction_session_timeout=60s` on checkout-db
5. Temporary rate limit at edge (removed after spike)

## Lessons Learned

Timeout errors often indicate queueing upstream (bouncer or DB), not just network. Check `SHOW POOLS` before scaling app pools blindly.
