# Connection Leak Detection and Resolution Runbook

## What is a Connection Leak
A connection is checked out from the application pool and never 
returned. Over time the pool fills completely and new requests 
time out waiting for a connection that never becomes available.

## How Leaks Differ From Pool Exhaustion
- Pool exhaustion: too many legitimate concurrent users
- Connection leak: connections checked out but not released, 
  often by a code path that exits without closing the session

## Signs of a Leak
- Pool errors increase gradually after a deployment, not immediately
- pg_stat_activity shows many idle connections from the same application
- Traffic is low but connection count is high
- Restarting the application temporarily fixes it (releases leaked connections)
- pool_size exhausted despite low active query count

## Detection Queries

### Check connection count by application and state
```sql
SELECT application_name, state, count(*) 
FROM pg_stat_activity 
GROUP BY application_name, state
ORDER BY count DESC;
```

### Find connections idle longer than 10 minutes
```sql
SELECT pid, application_name, state, 
       now() - state_change AS idle_duration,
       query
FROM pg_stat_activity
WHERE state = 'idle' 
AND now() - state_change > interval '10 minutes'
ORDER BY idle_duration DESC;
```

### Find connections idle in transaction (most dangerous)
```sql
SELECT pid, application_name, state,
       now() - state_change AS stuck_duration,
       left(query, 100) AS last_query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY stuck_duration DESC;
```

## Common Root Causes
1. Missing session.close() in exception handlers — try block exits 
   on error without reaching finally
2. Not using context managers — with Session() as session
3. ORM queries not closed in async code (async generators)
4. Long-running background jobs holding connections open
5. Missing pool_pre_ping — stale connections never detected

## Remediation Steps (advisory)
1. Set pool_pre_ping=True — detects and discards dead connections on checkout
2. Set pool_recycle=1800 — recycle connections every 30 minutes
3. Set idle_in_transaction_session_timeout=60s on RDS parameter group
4. Audit recent code changes for missing context managers
5. Set pool_timeout=10 to fail fast instead of queue building
6. Rolling restart of app pods releases all currently leaked connections

## Prevention Checklist
- Always use context managers: with db.session() as session
- Always close sessions in finally blocks
- Add pool_pre_ping=True to all SQLAlchemy engine configs
- Set idle_in_transaction_session_timeout on the database side
- Add pg_stat_activity monitoring alert for idle > 5 minutes
