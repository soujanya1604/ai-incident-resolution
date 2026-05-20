# Incident Report 001 — Pool Exhaustion After Deployment

**Date:** 2024-11-12  
**Service:** payment-db  
**Severity:** High  
**Duration:** 47 minutes

## Summary

After deploying payment-service v2.4.0, `payment-db` began returning `FATAL: sorry, too many clients already` (SQLSTATE 53300). Checkout and billing were impacted.

## Timeline

- 14:02 UTC — Deploy payment-service v2.4.0 (replica count 4 → 8)
- 14:05 UTC — Alert `pg_connections_high` fired on payment-db
- 14:08 UTC — Engineers observed SQLAlchemy `QueuePool limit` errors in app logs
- 14:49 UTC — Mitigated by rolling back deploy and reducing pool_size 20 → 10

## Root Cause

New deployment doubled application instances without changing SQLAlchemy `pool_size`. Total potential connections: 8 × (20 + 40 overflow) = 480, exceeding RDS `max_connections` of 350 for the instance class.

## Resolution Steps (proven)

1. Rolled back payment-service to v2.3.9 (halved instance count)
2. Set `pool_size=10`, `max_overflow=15` in payment-service config
3. Enabled `pool_pre_ping=True`
4. Scheduled RDS instance upgrade for headroom

## Lessons Learned

Always calculate `replicas × (pool_size + max_overflow)` before scaling horizontally. Add deploy checklist gate for connection budget.
