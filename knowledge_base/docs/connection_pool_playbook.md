# Connection Pool Exhaustion Playbook

## Prometheus / postgres_exporter Alerts

| Alert | Likely Cause |
|-------|----------------|
| `pg_stat_activity_count near max_connections` | Pool exhaustion or connection leak |
| `pg_stat_activity_max_tx_duration high` | Long transactions holding connections |
| `pgbouncer_pools_cl_waiting > 0` | Bouncer queue buildup |
| Deploy marker + connection spike | New code or replica count increased pool demand |

## Triage Flow

1. **Confirm scope** — single service vs all clients?
2. **Timeline** — correlate with deploy, traffic spike, or maintenance?
3. **Where is the queue?** — app pool, PgBouncer, or PostgreSQL directly?
4. **Who holds connections?** — `pg_stat_activity` grouped by `application_name`, `state`

## Safe Immediate Actions

- Scale read traffic away if read replicas available
- Reduce traffic via load balancer rate limit (reversible)
- Restart **stateless** app pods one at a time (rolling) to release leaked connections
- Do NOT run `DROP` or mass `pg_terminate_backend` without approval

## Escalation Criteria

- `reserved_slots` / superuser-only slots remaining → **critical**, page DBA
- Multiple services failing simultaneously → possible RDS or network issue
- Data corruption risk if killing backends in `active` state during writes
