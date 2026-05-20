# PgBouncer Pool Exhaustion Runbook

## Key Configuration (pgbouncer.ini)

| Setting | Purpose |
|---------|---------|
| `pool_mode` | `session`, `transaction`, or `statement` — transaction is common for web apps |
| `default_pool_size` | Server connections per user/database pair |
| `min_pool_size` | Minimum warm connections |
| `reserve_pool_size` | Extra connections under burst |
| `reserve_pool_timeout` | Seconds before reserve pool is used |
| `max_client_conn` | Max client connections to PgBouncer |
| `max_db_connections` | Cap per database across pools |

## Diagnosis Commands

```sql
SHOW POOLS;    -- cl_active, cl_waiting, sv_active, sv_idle
SHOW STATS;    -- totals per database
SHOW CLIENTS;  -- waiting clients
```

**cl_waiting > 0** for sustained periods indicates pool exhaustion at the bouncer layer.

## Common Causes

1. `default_pool_size` too low vs application instance count × pool_size
2. Long-running transactions holding server connections in transaction mode
3. Deploy increased app replicas without resizing PgBouncer pools
4. Missing `server_idle_timeout` causing stale server connections

## Remediation (advisory)

1. Increase `default_pool_size` incrementally (monitor RDS `DatabaseConnections`)
2. Enable `reserve_pool_size` for burst traffic
3. Fix application long transactions (set statement timeouts)
4. Restart PgBouncer only after config change — brief connection blip expected
