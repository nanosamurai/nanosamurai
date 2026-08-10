# Authentication and bring-your-own Keycloak

The Nanosamurai Compose stack does not include or provision an identity
provider. Authentication is disabled in the default evaluator so that a
localhost-only checkout can be opened immediately. An authenticated deployment
must supply, configure, secure, and operate its own Keycloak instance.

Keycloak is the only identity provider supported end to end today. Parts of the
token-validation path use standard OpenID Connect (OIDC), so some other
providers can work in limited scenarios. See
[Using another identity provider](#using-another-identity-provider) before
assuming that a generic OIDC provider is a drop-in replacement.

## Authentication modes

The effective default in `docker-compose.yml` is:

```text
SAMURAIBFF_AUTH_REQUIRED=false
SAMURAIBFF_AUTH_GUEST_TENANT_ID=00000000-0000-0000-0000-000000000000
```

In this evaluator mode, SamuraiBFF accepts browser and API requests without a
token and assigns persisted sessions to the seeded development tenant. This is
safe only with the default `127.0.0.1` host binding and development data.

When `SAMURAIBFF_AUTH_REQUIRED=true`:

- Browser users sign in through `GET /auth/login`. SamuraiBFF uses OAuth 2.0
  Authorization Code with PKCE and stores the returned access token in an
  HttpOnly, SameSite=Lax cookie.
- REST clients send `Authorization: Bearer <access-token>`.
- `/ws/audio` and `/ws/events` authenticate before upgrading the connection.
  Browser connections can use the access-token cookie; non-browser clients can
  use a bearer header or the supported `token` query parameter.
- `/api/*` requests and WebSocket sessions are scoped to the tenant UUID in the
  token. A session created by one tenant cannot be opened by another tenant.
- Machine-to-machine (M2M) clients use OAuth 2.0 `client_credentials`. They can
  be provisioned externally or, with optional Keycloak Admin API credentials,
  managed through SamuraiBFF.

The token lookup order is bearer header, `token` query parameter, then cookie.
Avoid query-string tokens unless a client cannot set a header or use the
cookie: URLs are commonly retained in browser history, proxy logs, and access
logs.

`POST /auth/logout` clears the SamuraiBFF cookie only. It does not end the
Keycloak single-sign-on session or call an OIDC end-session endpoint.

## Keycloak provisioning checklist

The examples below use:

```text
Public Nanosamurai origin: https://nanosamurai.example.com
Keycloak issuer:           https://keycloak.example.com/realms/nanosamurai
Browser client ID:         bff-web
Tenant claim:              tenant_id
```

Replace all example hosts and UUIDs with values owned by your deployment.

### 1. Create the realm and browser client

Create a realm and note its exact issuer URL. The configured issuer must match
the `iss` claim in access tokens byte for byte, including any trailing slash.
SamuraiBFF removes a trailing slash only while constructing Keycloak endpoint
URLs; token issuer verification uses the configured value exactly.

Create an OpenID Connect browser client with these properties:

- Client ID `bff-web`, or another value used consistently for both the BFF
  client ID and expected audience.
- Client authentication off (a public client); SamuraiBFF does not send a
  browser client secret during the code exchange.
- Standard/authorization-code flow enabled.
- PKCE enabled or required with method S256.
- Valid redirect URI
  `https://nanosamurai.example.com/auth/callback`.
- Allowed web origin `https://nanosamurai.example.com`.
- Scopes `openid`, `email`, and `profile` available to the client.

Direct Access Grants and service accounts are not required for the browser
client.

SamuraiBFF currently builds the authorization and token URLs using Keycloak's
realm layout:

```text
{issuer}/protocol/openid-connect/auth
{issuer}/protocol/openid-connect/token
```

OIDC discovery and key retrieval use:

```text
{issuer}/.well-known/openid-configuration
```

The discovery document must contain `jwks_uri`, and the BFF container must be
able to reach both URLs over the deployment network.

### 2. Configure access-token claims

Every accepted access token must provide:

| Claim | Requirement |
| --- | --- |
| `iss` | Exactly the configured issuer. |
| `sub` | A non-empty subject identifying the user or service account. |
| `aud` or `azp` | `aud` contains the configured audience, or Keycloak `azp` equals it. |
| `tenant_id` | A string UUID identifying the Nanosamurai tenant. |

SamuraiBFF currently accepts only RS256-signed tokens. Configure a Keycloak
protocol mapper that copies the user's `tenant_id` attribute into the access
token as a string. Do not rely on the ID token: SamuraiBFF authorizes requests
with the access token.

Although `SAMURAIBFF_AUTH_TENANT_CLAIM` is configurable, the current HTTP and
WebSocket paths do not apply renamed claims consistently. Emit `tenant_id` in
all access tokens, including service-account tokens, for reliable REST and
WebSocket tenant isolation.

For a browser token, Keycloak normally sets `azp` to the browser client ID. You
can instead add an audience mapper so `aud` explicitly contains `bff-web`. For
an M2M client whose own client ID differs from `bff-web`, add an audience mapper
that includes `bff-web` in `aud`.

### 3. Provision matching database tenants

Authentication does not create tenant or user rows. Each UUID emitted as
`tenant_id` must already exist in PostgreSQL because `sessions.tenant_id` has a
foreign-key reference to `tenants.id`.

For example:

```sql
INSERT INTO tenants (id, name)
VALUES ('11111111-1111-4111-8111-a1b2c3d4e5f6', 'Example tenant')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
```

An `app_users` row is optional because `sessions.user_id` is nullable. When
present, set `app_users.external_id` to the token's `sub` and use the same
tenant UUID. SamuraiBFF looks up that row for attribution but does not create it
automatically.

## SamuraiBFF authentication settings

The values shown are the effective defaults of this repository's base Compose
stack. Defaults inside a standalone SamuraiBFF deployment can differ.

| Environment variable | Compose default | Purpose |
| --- | --- | --- |
| `SAMURAIBFF_AUTH_REQUIRED` | `false` | Enforce authentication for the API and WebSockets. Set `true` outside the localhost evaluator. |
| `SAMURAIBFF_AUTH_GUEST_TENANT_ID` | All-zero UUID | Tenant used only while authentication is disabled. |
| `SAMURAIBFF_AUTH_ISSUER` | `https://auth.nanosamur.ai/realms/nanosamurai` | Exact realm issuer used for discovery, signature verification, and Keycloak endpoint construction. The default is not a bundled identity service; set your own issuer when enabling auth. |
| `SAMURAIBFF_AUTH_AUDIENCE` | `bff-web` | Required `aud` value, with Keycloak `azp` accepted as a fallback. |
| `SAMURAIBFF_AUTH_CLIENT_ID` | `bff-web` | Public client used by browser Authorization Code with PKCE. Defaults to the audience inside SamuraiBFF if omitted. |
| `SAMURAIBFF_AUTH_COOKIE_NAME` | `access_token` | HttpOnly access-token cookie name. Not exposed by the base Compose file. |
| `SAMURAIBFF_AUTH_TENANT_CLAIM` | `tenant_id` | Preferred tenant-claim name for HTTP. Keep `tenant_id` because WebSocket handling is not fully configurable today. Not exposed by the base Compose file. |
| `SAMURAIBFF_ORIGIN_URI` | `http://localhost:8000` | Internal BFF origin and fallback browser origin. The base Compose file currently fixes this value. |
| `SAMURAIBFF_PUBLIC_ORIGIN_URI` | unset | Recommended external browser origin behind ingress or a reverse proxy. Takes precedence when constructing the callback URI. Not exposed by the base Compose file. |

When no public origin is configured, SamuraiBFF can derive it from
`Forwarded` or `X-Forwarded-Proto` and `X-Forwarded-Host`, then falls back to
`SAMURAIBFF_ORIGIN_URI`. Configure the public origin explicitly behind a load
balancer and make sure untrusted clients cannot forge proxy headers.

### Base `.env` values

The base Compose file already passes through the primary authentication
settings, so these values can be added to the uncommitted `.env` file:

```dotenv
SAMURAIBFF_AUTH_REQUIRED=true
SAMURAIBFF_AUTH_ISSUER=https://keycloak.example.com/realms/nanosamurai
SAMURAIBFF_AUTH_AUDIENCE=bff-web
SAMURAIBFF_AUTH_CLIENT_ID=bff-web
```

Do not commit `.env`, client secrets, admin tokens, or user access tokens.

### Compose override for advanced settings

The base Compose file intentionally keeps the evaluator small. It does not pass
through the cookie, configurable tenant claim, public origin, or Keycloak Admin
API settings, and it fixes `SAMURAIBFF_ORIGIN_URI` to localhost. Create a local
`docker-compose.auth.yml` override when those settings are needed:

```yaml
services:
  samuraibff:
    environment:
      SAMURAIBFF_ORIGIN_URI: ${SAMURAIBFF_ORIGIN_URI:-http://localhost:8000}
      SAMURAIBFF_PUBLIC_ORIGIN_URI: ${SAMURAIBFF_PUBLIC_ORIGIN_URI:-http://localhost:8000}
      SAMURAIBFF_AUTH_COOKIE_NAME: ${SAMURAIBFF_AUTH_COOKIE_NAME:-access_token}
      SAMURAIBFF_AUTH_TENANT_CLAIM: ${SAMURAIBFF_AUTH_TENANT_CLAIM:-tenant_id}
      SAMURAIBFF_KEYCLOAK_ADMIN_ISSUER: ${SAMURAIBFF_KEYCLOAK_ADMIN_ISSUER:-}
      SAMURAIBFF_KEYCLOAK_ADMIN_REALM: ${SAMURAIBFF_KEYCLOAK_ADMIN_REALM:-}
      SAMURAIBFF_KEYCLOAK_ADMIN_CLIENT_ID: ${SAMURAIBFF_KEYCLOAK_ADMIN_CLIENT_ID:-}
      SAMURAIBFF_KEYCLOAK_ADMIN_CLIENT_SECRET: ${SAMURAIBFF_KEYCLOAK_ADMIN_CLIENT_SECRET:-}
```

For a remote deployment, set at least:

```dotenv
SAMURAIBFF_ORIGIN_URI=https://nanosamurai.example.com
SAMURAIBFF_PUBLIC_ORIGIN_URI=https://nanosamurai.example.com
```

Render and start the merged configuration with:

```bash
docker compose -f docker-compose.yml -f docker-compose.auth.yml config
docker compose -f docker-compose.yml -f docker-compose.auth.yml up -d
```

This override does not change `COMPOSE_BIND_IP`; published ports remain bound
to `127.0.0.1` unless an operator explicitly changes that separate setting.
Use ingress or a reverse proxy with TLS instead of publishing the evaluator
directly on a LAN or WAN interface.

## Optional Keycloak-managed M2M credentials

The browser UI and bearer-token validation do not require Keycloak Admin API
access. Admin access is needed only for SamuraiBFF's tenant-scoped credential
management endpoints:

```text
GET    /api/api-credentials
POST   /api/api-credentials
POST   /api/api-credentials/{id}/rotate
DELETE /api/api-credentials/{id}
```

### Configure the Keycloak admin client

In the same realm as `bff-web`, create a separate confidential OpenID Connect
client, commonly named `bff-admin`. This client is SamuraiBFF's machine identity
for the Keycloak Admin API; it is not the browser client and must never be
exposed to browser users.

In the Keycloak Admin Console:

1. Go to **Clients**, choose **Create client**, select **OpenID Connect**, and
   set the client ID to `bff-admin`.
2. Turn **Client authentication** on.
3. Turn **Service accounts roles** on. Standard flow and Direct Access Grants
   are not required for this client.
4. Save the client and copy its secret from the **Credentials** tab into the
   deployment's secret store.
5. Open **Service account roles**, choose **Assign role**, expose client roles,
   and assign `realm-management` roles `view-clients` and `manage-clients`.

Those are the permissions used by the tested setup. They allow SamuraiBFF to
create and find clients, generate and rotate secrets, configure protocol
mappers, and disable clients. Do not grant broad realm-administration roles.

Pass the admin client to SamuraiBFF through the Compose override described
above:

```dotenv
SAMURAIBFF_KEYCLOAK_ADMIN_ISSUER=https://keycloak.example.com/realms/nanosamurai
SAMURAIBFF_KEYCLOAK_ADMIN_REALM=nanosamurai
SAMURAIBFF_KEYCLOAK_ADMIN_CLIENT_ID=bff-admin
SAMURAIBFF_KEYCLOAK_ADMIN_CLIENT_SECRET=<secret-from-your-secret-store>
```

Restart SamuraiBFF after changing these values. A correctly configured startup
logs `Keycloak admin client initialized`; missing values log that the admin
client is disabled.

### Create a credential in the BFF UI

The API Credentials page requires an authenticated deployment and a signed-in
human user whose access token contains a valid `tenant_id` matching a database
tenant.

1. Sign in to the Nanosamurai browser UI.
2. Choose **API Credentials** in the sidebar, or open
   `https://nanosamurai.example.com/api-credentials`.
3. Enter a descriptive name such as `reporting-sdk` and choose **Create**.
4. Copy both the displayed `client_id` and `client_secret` immediately and
   store them in a secret manager. Closing the dialog permanently removes the
   secret from the UI; if it is lost, rotate it.

SamuraiBFF uses `bff-admin` to create a new confidential Keycloak client with a
service account. It adds a hard-coded `tenant_id` claim for the signed-in
user's tenant and an audience mapper for `SAMURAIBFF_AUTH_AUDIENCE`. The new
client is therefore tenant-bound even though its token is obtained without a
human user.

The generated secret is returned only on creation or rotation. PostgreSQL
stores the Keycloak client ID and audit metadata, not the secret. Currently,
API credential management is tenant-scoped but not role-scoped: every
authenticated user in a tenant can list, create, rotate, and revoke that
tenant's credentials. Account for that boundary before granting users access
to a tenant.

### Exchange the credential for an API access token

The API Credentials page creates an OAuth client ID and secret; it does not
mint a long-lived Nanosamurai API key. Keycloak issues the actual short-lived
bearer access token through its token endpoint. Never send the client secret to
a SamuraiBFF `/api/*` endpoint.

Using Bash:

```bash
export NANOSAMURAI_ISSUER=https://keycloak.example.com/realms/nanosamurai
export NANOSAMURAI_CLIENT_ID='<client-id-copied-from-the-ui>'
export NANOSAMURAI_CLIENT_SECRET='<client-secret-copied-from-the-ui>'

curl --fail-with-body --request POST \
  "${NANOSAMURAI_ISSUER}/protocol/openid-connect/token" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=${NANOSAMURAI_CLIENT_ID}" \
  --data-urlencode "client_secret=${NANOSAMURAI_CLIENT_SECRET}"
```

The JSON response contains `access_token`, `expires_in`, and the token type.
Use the access token, not the client secret, to call SamuraiBFF:

```bash
export NANOSAMURAI_ACCESS_TOKEN='<access-token-from-keycloak>'

curl --fail-with-body \
  --header "Authorization: Bearer ${NANOSAMURAI_ACCESS_TOKEN}" \
  https://nanosamurai.example.com/api/me
```

Windows PowerShell:

```powershell
$env:NANOSAMURAI_ISSUER = "https://keycloak.example.com/realms/nanosamurai"
$env:NANOSAMURAI_CLIENT_ID = "<client-id-copied-from-the-ui>"
$env:NANOSAMURAI_CLIENT_SECRET = "<client-secret-copied-from-the-ui>"

$tokenResponse = Invoke-RestMethod -Method Post `
  -Uri "$env:NANOSAMURAI_ISSUER/protocol/openid-connect/token" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{
    grant_type = "client_credentials"
    client_id = $env:NANOSAMURAI_CLIENT_ID
    client_secret = $env:NANOSAMURAI_CLIENT_SECRET
  }

Invoke-RestMethod -Uri "https://nanosamurai.example.com/api/me" `
  -Headers @{Authorization = "Bearer $($tokenResponse.access_token)"}
```

The [Python SDK and CLI](apis-and-extension-points.md#python-sdk-and-cli)
perform discovery, obtain and cache the access token, and refresh it when
needed after receiving the same issuer, client ID, and client secret.

Inspect a newly issued token locally before distributing the credential. It
must contain the correct UUID `tenant_id`, the BFF audience in `aud`, and an
RS256 signature accepted by SamuraiBFF. Protocol-mapper creation is best effort
in the current implementation, so successful credential creation alone does
not prove the resulting token is usable.

### Rotate, revoke, and troubleshoot credentials

**Rotate** generates and displays a new secret; the old secret stops working.
Update consumers immediately. **Revoke** attempts to disable the Keycloak
client and marks the database record revoked.

If the admin configuration is absent, the server still starts: list operations
remain database-backed, while create and rotate return
`503 keycloak-admin-unavailable`. Revocation without a working admin client can
still mark the database row revoked without disabling the corresponding client
in Keycloak, so verify the client is disabled there during credential
containment. A `502 keycloak-admin-error` during creation normally indicates an
incorrect issuer, realm, secret, or missing client-management permissions.

## Validate an authenticated deployment

### Check OIDC discovery

```bash
curl --fail --show-error \
  https://keycloak.example.com/realms/nanosamurai/.well-known/openid-configuration
```

Confirm that the returned `issuer` matches
`SAMURAIBFF_AUTH_ISSUER` and that `jwks_uri` is reachable from the SamuraiBFF
container.

### Check the browser redirect

```bash
curl --include --max-redirs 0 \
  "http://127.0.0.1:8000/auth/login?next=%2Flive"
```

The `Location` header should point to the expected Keycloak realm and include
`client_id=bff-web`, an S256 PKCE challenge, and
`redirect_uri=https://nanosamurai.example.com/auth/callback` for the example
remote deployment.

### Check a bearer token

Inspect tokens locally; do not paste production tokens into public JWT tools.
Confirm `alg=RS256` and the required claims, then call:

```bash
curl --fail --show-error \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  https://nanosamurai.example.com/api/me
```

A successful response reports `authenticated: true`, the tenant ID, and basic
subject information. Then create a session and test both WebSocket upgrades;
HTTP success alone does not prove that a renamed tenant claim works on the
WebSocket path.

## Troubleshooting

### Keycloak reports an invalid redirect URI

Compare the callback in `/auth/login`'s `Location` header with the client's
Valid Redirect URIs. Check `SAMURAIBFF_PUBLIC_ORIGIN_URI`, forwarded scheme and
host headers, TLS termination, and the exact `/auth/callback` path.

### The BFF reports an invalid issuer or audience

- Compare the token's `iss` exactly with `SAMURAIBFF_AUTH_ISSUER`.
- Confirm `aud` contains `SAMURAIBFF_AUTH_AUDIENCE`, or that Keycloak `azp`
  equals it.
- For M2M clients, add an audience mapper for `bff-web`; the M2M client's own
  client ID is normally different.

### Login succeeds but API or WebSocket access fails

- Confirm the access token, rather than only the ID token, contains a string
  `tenant_id` UUID.
- Confirm the same tenant UUID exists in the `tenants` table.
- Keep the claim name `tenant_id`; custom names are not applied consistently by
  current WebSocket authentication.
- Verify that the token is RS256-signed and its signing key appears in the
  issuer's JWKS.

### Signing-key rotation causes token failures

SamuraiBFF caches discovery metadata and JWKS in process memory without a TTL.
Restart SamuraiBFF after a Keycloak signing-key rotation if it continues using
stale keys. Plan rotations so that old and new verification keys overlap.

### M2M management returns `503 keycloak-admin-unavailable`

Check that all four `SAMURAIBFF_KEYCLOAK_ADMIN_*` values reach the container.
The base Compose file does not pass them through without an override. Also
verify that the admin service account can obtain a token and has the required
realm-management client permissions.

## Using another identity provider

OIDC compatibility is partial. Keycloak remains the only supported end-to-end
configuration.

| Capability | Works without SamuraiBFF changes? | Conditions or required changes |
| --- | --- | --- |
| Externally minted bearer token for REST | Conditionally | The provider must expose discovery and JWKS, sign with RS256, and emit matching `iss`, `aud` or `azp`, non-empty `sub`, and UUID `tenant_id` claims. |
| Bearer or cookie token for WebSockets | Conditionally | The same token requirements apply. Emit `tenant_id`; a custom configured claim name is not reliably honored by WebSockets. |
| Externally provisioned M2M client used by the Python SDK | Conditionally | The provider's discovery document must advertise `token_endpoint`, support `client_credentials`, and issue a compatible BFF access token. The SDK discovers the token endpoint. |
| Browser login through `/auth/login` | Usually not | SamuraiBFF constructs Keycloak-specific `/protocol/openid-connect/auth` and `/token` URLs instead of using discovery endpoints. A non-Keycloak provider works unchanged only if it deliberately implements that URL layout and the same public-client PKCE behavior. |
| Create, rotate, or revoke M2M credentials through SamuraiBFF | No | These operations call the Keycloak Admin REST API and create Keycloak protocol mappers. Provision credentials externally or add a provider-specific admin adapter to SamuraiBFF. |

To support another provider as a first-class replacement, SamuraiBFF would need
changes to:

1. Use `authorization_endpoint` and `token_endpoint` from OIDC discovery for
   browser login and code exchange, and define provider-neutral logout behavior.
2. Apply `SAMURAIBFF_AUTH_TENANT_CLAIM` consistently to HTTP and WebSocket
   requests.
3. Introduce a provider-neutral credential-management interface, implement an
   adapter for the selected provider, and migrate Keycloak-specific persistence
   names if necessary; alternatively, disable the management endpoints and
   manage all M2M credentials externally.
4. Add an explicit, safe signing-algorithm allowlist if the provider cannot use
   RS256.
5. Add bounded discovery/JWKS refresh and retry on an unknown signing key.
6. Add provider integration tests for browser PKCE, bearer REST, WebSockets,
   tenant isolation, and M2M tokens before claiming support.

These are SamuraiBFF implementation changes, not settings that can be solved in
this Compose repository.

## Current security limitations

- Authentication is disabled by default for the localhost evaluator.
- Token verification accepts RS256 only.
- OIDC discovery and JWKS are cached for the life of the SamuraiBFF process.
- Logout clears only the local cookie.
- Custom tenant-claim configuration is not applied consistently to WebSockets.
- Authorization is tenant-scoped, not role- or per-user-scoped.
- Query-string tokens are supported but can leak through URL handling.

Before exposing Nanosamurai beyond localhost, also follow
[Deployment and security boundaries](deployment-and-security.md).
