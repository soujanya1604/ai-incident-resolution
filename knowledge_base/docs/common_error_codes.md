# Quick Reference — PostgreSQL Connection Error Codes

## Class 08xxx — Connection Exceptions

| Code | Short | First Action |
|------|-------|--------------|
| 08006 | connection_failure | Check network, security groups, RDS status |
| 08001 | unable_to_establish | Verify host, port, credentials, SSL mode |
| 08003 | connection_does_not_exist | Pool may be returning dead connections; enable pre-ping |
| 08004 | server_rejected | Check `pg_hba.conf` / RDS security group |
| 57P03 | cannot_connect_now | Database starting or in recovery; retry with backoff |

## Class 53xxx — Insufficient Resources

| Code | Short | First Action |
|------|-------|--------------|
| 53300 | too_many_connections | Pool exhaustion — see connection_pool_playbook |
| 53400 | config_limit_exceeded | Review parameter group limits |
| 53100 | disk_full | Expand storage, vacuum, archive logs |
| 53200 | out_of_memory | Scale instance, reduce work_mem / connections |

## Message → error_type Mapping

| User / Log Message | Canonical error_type |
|--------------------|----------------------|
| too many clients | pool_exhaustion |
| connection timed out | timeout |
| remaining connection slots are reserved | reserved_slots |
| connection refused | connection_refused |
| QueuePool limit | pool_exhaustion |
