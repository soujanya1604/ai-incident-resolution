# AWS RDS Proxy — When and How to Use It

## When to Use RDS Proxy
- Applications with many short-lived connections (Lambda, serverless)
- Connection count regularly approaches max_connections
- Frequent RDS failovers causing application connection drops
- Need for IAM-based authentication without password rotation complexity

## How It Works
RDS Proxy sits between your application and RDS. It maintains a warm 
connection pool to RDS and multiplexes thousands of application 
connections onto fewer database connections. Applications connect to 
the proxy endpoint instead of the RDS endpoint directly.

## Key Metrics to Watch in CloudWatch
- ProxyClientConnectionsReceived — total connections received by proxy
- ProxyClientConnectionsSetupSucceeded — successful connection setups
- DatabaseConnectionsCurrentlyBorrowed — active RDS connections in use
- DatabaseConnectionsCurrentlySessionPinned — pinned connections (watch for high values)

## Setup Checklist
1. Enable in RDS console → Proxies → Create proxy
2. Update application connection string to proxy endpoint (not RDS endpoint)
3. IAM authentication required — no plaintext password in connection string
4. Set connection borrow timeout appropriate for your workload
5. Monitor DatabaseConnectionsCurrentlyBorrowed vs RDS max_connections

## When RDS Proxy Reduces Connection Errors
- Lambda functions opening new connections per invocation → proxy pools them
- Deployment scaling events → proxy absorbs connection burst
- RDS failover → proxy retries transparently, app sees shorter outage

## Limitations
- Additional latency (~1ms) for connection borrow
- Does not support all PostgreSQL features (e.g. SET SESSION statements 
  may cause pinning)
- Extra cost — charged per vCPU of RDS instance per hour
