# Network egress

`lindas-mcp` reaches exactly **one** external host. Egress is controlled on two
layers (SEC-021).

## Allow-listed hosts

| Host | Purpose |
|---|---|
| `lindas.admin.ch` | The LINDAS SPARQL 1.1 read endpoint (`/query`, HTTPS) |

Note: municipality and code URIs in the *data* often use the `ld.admin.ch`
namespace, but those are identifiers, not fetch targets — the client only ever
connects to `lindas.admin.ch`.

## Code layer

The allow-list is a `frozenset` in
[`src/lindas_mcp/lindas/client.py`](../src/lindas_mcp/lindas/client.py)
— **not** configurable via environment variables, so an operator mistake or a
tampered config cannot silently widen it:

```python
ALLOWED_HOSTS = frozenset({"lindas.admin.ch"})
```

- `assert_host_allowed()` runs before the HTTP client is built.
- The client is created with `follow_redirects=False`; a `3xx` response is
  surfaced as an error instead of being followed off the allow-listed host.
- Every request targets the fixed `ENDPOINT` — no tool accepts a user-supplied
  URL, so there is no SSRF surface at the client.

### One caveat: SPARQL federation via `run_sparql`

The `run_sparql` escape hatch forwards a raw SPARQL query to the read-only
`/query` endpoint. A `SERVICE <uri>` (federation) clause in that query is
executed by the **upstream LINDAS store**, not by this server, so the code-layer
allow-list does not constrain it. `lindas-mcp` itself never connects anywhere but
`lindas.admin.ch`. Any federation is bounded by the upstream store's own policy;
`run_sparql` stays capped (500 rows, 30 s) and marked advanced.

## Network layer

For hosted (SSE / streamable-http) deployments, add an egress control at the
platform layer as defense in depth:

- **Kubernetes:** a `NetworkPolicy` allowing egress only to `lindas.admin.ch`
  (plus DNS to the cluster resolver on UDP/TCP 53 — otherwise hostname
  resolution breaks).
- **Cloud (Render/Railway/etc.):** a security-group / firewall egress rule to the
  same host, or route outbound traffic through a filtering proxy.

## Changing the allow-list

Adding a host is a reviewed code change:

1. Add the hostname to `ALLOWED_HOSTS` in `client.py`.
2. Add a row to the table above.
3. Update the network-layer policy to match.
4. Note the change in `CHANGELOG.md`.
