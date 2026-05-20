# Database Connection Monitoring Checklist

## CloudWatch Metrics (RDS) — Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| DatabaseConnections | >70% of max_connections | >90% of max_connections | Check pg_stat_activity |
| CPUUtilization | >70% | >90% | Check slow queries |
| FreeableMemory | <1 GB | <500 MB | Scale instance |
| ReadLatency | >20ms | >100ms | Check index usage |
| WriteLatency | >10ms | >50ms | Check IOPS limits |
| SwapUsage | >256 MB | >512 MB | Reduce work_mem |

## Step 1 — Run These Queries First

### Current connection count vs limit
```sql
SELECT count(*) AS current_connections,
       setting::int AS max_connections,
       round(count(*) * 100.0 / setting::int, 1) AS pct_used
FROM pg_stat_activity,
     pg_settings
WHERE pg_settings.name = 'max_connections'
GROUP BY setting;
```

### Who is connected and what are they doing
```sql
SELECT application_name, 
       client_addr, 
       state, 
       count(*) AS connections
FROM pg_stat_activity 
GROUP BY 1, 2, 3
ORDER BY 4 DESC;
```

### Long-running queries (potential blockers)
```sql
SELECT pid,
       now() - query_start AS duration,
       state,
       left(query, 120) AS query_preview
FROM pg_stat_activity
WHERE state != 'idle'
AND now() - query_start > interval '30 seconds'
ORDER BY duration DESC;
```

## Step 2 — PgBouncer Health Check

```sql
SHOW POOLS;    -- cl_waiting > 0 means clients are queuing
SHOW STATS;    -- total_wait_time rising means bouncer is the bottleneck  
SHOW SERVERS;  -- sv_idle vs sv_active ratio
SHOW CLIENTS;  -- total clients connected to bouncer
```

### What to look for in SHOW POOLS
| Column | Concern |
|--------|---------|
| cl_waiting > 0 | Clients queuing — pool too small |
| sv_idle = 0 | All server connections in use |
| sv_login > 0 for long time | New connections being created slowly |

## Step 3 — Escalation Decision Tree

```
cl_waiting > 0 sustained 5+ min
  → Increase PgBouncer default_pool_size incrementally

max_connections usage > 90%
  → Page DBA, consider RDS Proxy or vertical scale

reserved_slots error (SQLSTATE 53300 non-superuser)
  → Critical, DBA only, do not attempt self-service fix

Multiple services failing simultaneously
  → RDS or network issue, not application config
  → Check RDS console, CloudWatch, VPC security groups

Connection count stable but queries slow
  → Not a connection issue — check slow query log, indexes
```

## Step 4 — After Incident Verification

1. `DatabaseConnections` CloudWatch back below 50% of max
2. `cl_waiting = 0` in PgBouncer SHOW POOLS
3. No new `QueuePool limit` errors in application logs for 10 minutes
4. `pg_stat_activity` idle connection count back to baseline
5. Confirm fix steps were documented in incident report
