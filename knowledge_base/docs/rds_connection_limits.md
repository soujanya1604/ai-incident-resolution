# AWS RDS PostgreSQL Connection Limits

## max_connections Formula

RDS sets `max_connections` based on instance memory:

```
LEAST({DBInstanceClassMemory/9531392}, 5000)
```

Larger instances allow more connections but each connection consumes RAM (~10MB per connection on average).

## Reserved Connections

PostgreSQL reserves some slots for superusers (`superuser_reserved_connections`, default 3).
Replication connections also consume slots. When you see:

```
FATAL: remaining connection slots are reserved for roles with the SUPERUSER attribute
```

Non-superuser application roles cannot obtain new connections. This is **critical** severity.

## RDS-Specific Checks

1. CloudWatch: `DatabaseConnections`, `CPUUtilization`, `FreeableMemory`
2. Parameter group: `max_connections`, `idle_in_transaction_session_timeout`
3. Read replicas: each replica has its own connection limit
4. RDS Proxy: use when many short-lived clients connect to RDS

## Scaling Guidance

- Vertical scale (larger instance) increases `max_connections`
- RDS Proxy + PgBouncer for connection multiplexing
- Reduce per-app `pool_size` × number of app instances
- Kill idle connections: `pg_terminate_backend(pid)` for `idle` > 30 min (with approval)
