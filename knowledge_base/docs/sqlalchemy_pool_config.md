# SQLAlchemy Connection Pool Configuration

Reference: SQLAlchemy 2.x pooling (`create_engine` pool parameters).

## Core Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `pool_size` | 5 | Persistent connections kept open |
| `max_overflow` | 10 | Extra connections beyond pool_size under load |
| `pool_timeout` | 30 | Seconds to wait for a connection before error |
| `pool_recycle` | -1 | Recycle connections after N seconds (avoid stale) |
| `pool_pre_ping` | False | Test connection health before checkout |

**Max connections per process** ≈ `pool_size + max_overflow`.

## Timeout Errors

`QueuePool limit of size X overflow Y reached, connection timed out` means:

- All `pool_size + max_overflow` connections are checked out
- Wait exceeded `pool_timeout` seconds
- Often correlated with slow queries or connection leaks (not returned to pool)

## Recommended Production Settings

```python
create_engine(
    url,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)
```

## After Deploy Checklist

1. Count app replicas × (pool_size + max_overflow) vs database max_connections
2. Verify sessions are closed (`session.close()` / context managers)
3. Enable `pool_pre_ping` after network blips or RDS failover events
