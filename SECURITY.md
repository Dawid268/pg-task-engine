# Security policy

## Supported scope

`pg-task-engine` is a pre-release library. The current release candidate
is `0.1.0a2`. API behavior, compatibility and security boundaries can
change until a stable release.

The library executes **trusted, locally registered Python task handlers**.
It must not execute code or import modules named by an untrusted job payload.
It is not a sandbox, authentication gateway or multi-tenant authorization
service. Operators must use TLS, least-privilege PostgreSQL credentials
and downstream idempotency for external effects.

## Reporting a vulnerability

Do not post credentials, exploit payloads containing sensitive data or
private database connection strings in public GitHub Issues. If enabled
for the repository, use GitHub's **private vulnerability reporting**:

https://github.com/Dawid268/pg-task-engine/security/advisories/new

If the private reporting feature is unavailable, contact the repository
maintainer privately through their GitHub profile before disclosing
security-sensitive details. No security response-time SLA is currently
promised.
