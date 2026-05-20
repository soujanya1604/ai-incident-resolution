# PostgreSQL Connection Error Codes

## SQLSTATE Class 08 — Connection Exception

| Code | Name | Meaning |
|------|------|---------|
| 08000 | connection_exception | General connection failure |
| 08003 | connection_does_not_exist | Connection no longer valid |
| 08006 | connection_failure | Could not establish connection |
| 08001 | sqlclient_unable_to_establish_sqlconnection | Client cannot connect |
| 08004 | sqlserver_rejected_establishment_of_sqlconnection | Server rejected connection |
| 08007 | transaction_resolution_unknown | Connection lost during transaction |

## SQLSTATE Class 53 — Insufficient Resources

| Code | Name | Meaning |
|------|------|---------|
| 53300 | too_many_connections | `max_connections` exceeded |
| 53400 | configuration_limit_exceeded | Config limit hit |
| 53100 | disk_full | Disk space exhausted |
| 53200 | out_of_memory | Memory exhausted |

## Common FATAL Messages

- **too many clients already** — maps to 53300; all connection slots in use.
- **remaining connection slots are reserved** — non-superuser slots exhausted; replication/superuser slots remain.
- **cannot connect now** (57P03) — database in recovery or startup; retry with backoff.

## First Actions

1. Check `SELECT count(*) FROM pg_stat_activity;` vs `SHOW max_connections;`
2. Identify idle vs active connections by `state`, `application_name`, `client_addr`
3. Check for connection leaks in app pool config after recent deploy
