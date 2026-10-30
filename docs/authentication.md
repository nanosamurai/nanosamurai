# Sign-in and access control

Nanosamurai starts in **local mode**: no sign-in, one user, everything on
`127.0.0.1`. You can turn on sign-in later with your own OpenID Connect
(OIDC) identity provider. This repository does not include or run an identity
provider for you.

- [Local mode (default)](#local-mode-default)
- [Roles and sharing](#roles-and-sharing)
- [Turn on sign-in](#turn-on-sign-in)
- [API keys](#api-keys)
- [Keycloak setup](#keycloak-setup)
- [Other identity providers](#other-identity-providers)
- [Check your setup](#check-your-setup)
- [Troubleshooting](#troubleshooting)
- [Limits](#limits)

## Local mode (default)

`docker compose up -d` starts with:

```text
SAMURAIBFF_AUTH_REQUIRED=false
SAMURAIBFF_AUTH_GUEST_TENANT_ID=00000000-0000-0000-0000-000000000000
```

Open <http://127.0.0.1:8000/live> and record. There is no login page. The top
bar shows **Local mode** and **Sign-in is off**.

In local mode you are the Admin of one local organization:

- You record, open, play and delete your sessions.
- You manage speakers, workflows, webhooks and defaults (where enabled).
- Sharing, the colleague list, **People** and **API Credentials** are hidden.
  There is nobody to share with, and the API needs no key.

The database seed creates this local user (the "guest"). Every request without
a token runs as the guest. Its issuer, `urn:nanosamurai:guest`, is not a URL,
so no provider token can resolve to it. Sharing, **People** and
**API Credentials** return 403 in local mode. If the guest row is missing,
requests fail with 503; they never fall back to another identity.

This is safe only on `127.0.0.1` with development data. Never expose local
mode on a LAN or the internet.

### Upgrading an existing install

`db_migrate` applies new migrations on the next `docker compose up -d`.
Migrations `022` and `024` add access control; `020` and `021` add track
binding and the Sessions page index. There is no `023`. Your existing sessions stay
visible and you manage them as before. No action is needed.

If you later turn sign-in on, sessions recorded before the upgrade stay
visible to everyone in the organization, as they were. See
[Sessions recorded before access control](#sessions-recorded-before-access-control).

## Roles and sharing

These rules apply when sign-in is on.

| Role | Can |
| --- | --- |
| Member | Record with all settings, share own sessions, use published workflows and webhooks. |
| Builder | Member rights, plus personal workflows, webhooks and personal API keys. |
| Admin | Builder rights, plus **People**, publishing, organization defaults and all API keys. |

- Every new session has one owner. Nobody reads another person's private
  session, not even an Admin.
- The owner chooses who can see a session: **Private** (default), **Selected
  people** or **Everyone in the organization**. Shared access is read-only.
- A person belongs to one organization (tenant).
- Roles and suspension are stored in PostgreSQL, not in the identity provider.
  A valid login alone gives no access: an Admin or operator must add the
  person first.

### Sessions recorded before access control

Older versions did not store who recorded a session, and every signed-in
person could read every session of their organization. On upgrade:

- All existing sessions stay visible to everyone in their organization.
- Sessions without a known owner show **Owner unknown**. Admins manage them:
  rename, delete, share or make them Private (then only Admins read them).
- An Admin can assign an owner in **Share** (an active person, or
  themselves). After that the session behaves like any other.

`legacy-report` counts sessions without an owner per organization.

## Turn on sign-in

### 1. Check that your provider fits

Any OIDC provider works if it offers the items in this table. Keycloak is the
provider we test end to end.

| Need | Detail |
| --- | --- |
| Discovery | `{issuer}/.well-known/openid-configuration` with the same `issuer`, plus `jwks_uri`, `authorization_endpoint` and `token_endpoint`. `end_session_endpoint` is optional; without it, sign-out only clears the Nanosamurai cookie. |
| Browser client | A public client (no secret) with Authorization Code + PKCE (S256). Redirect URI `<origin>/auth/callback`. Post-logout redirect URI `<origin>/`. Scopes `openid email profile`. |
| Access tokens | JWT signed with RS256, with `iss`, `sub`, `exp` and the audience (`bff-web` by default) in `aud` or `azp`. |
| Tenant claim | A string UUID in `tenant_id` (or the claim you set in `SAMURAIBFF_AUTH_TENANT_CLAIM`) on every access token. |
| API keys (optional) | The `client_credentials` grant, with the client id in `azp` (or the claim you set in `SAMURAIBFF_AUTH_CLIENT_CLAIM`). |

Nanosamurai reads the login, token and logout URLs from discovery. It does not
assume Keycloak's URL layout.

Make the tenant claim an attribute that only administrators can change.

### 2. Configure Nanosamurai

Add your values to the uncommitted `.env` file:

```dotenv
SAMURAIBFF_AUTH_ISSUER=https://id.example.com/realms/acme
SAMURAIBFF_AUTH_AUDIENCE=bff-web
SAMURAIBFF_AUTH_CLIENT_ID=bff-web
SAMURAIBFF_PUBLIC_ORIGIN_URI=http://localhost:8000
```

Start the stack with the sign-in override:

```bash
docker compose -f docker-compose.yml -f docker-compose.sign-in.yml up -d
```

[`docker-compose.sign-in.yml`](../docker-compose.sign-in.yml) turns sign-in on
and passes these settings to SamuraiBFF:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SAMURAIBFF_AUTH_ISSUER` | none (required) | Exact issuer URL, including any trailing slash. |
| `SAMURAIBFF_AUTH_AUDIENCE` | `bff-web` | Audience every access token must carry. |
| `SAMURAIBFF_AUTH_CLIENT_ID` | `bff-web` | Browser client id. |
| `SAMURAIBFF_AUTH_TENANT_CLAIM` | `tenant_id` | Claim with the tenant UUID. |
| `SAMURAIBFF_AUTH_CLIENT_CLAIM` | `azp` | Claim with the client id of machine tokens (Okta: `cid`). |
| `SAMURAIBFF_PUBLIC_ORIGIN_URI` | `http://localhost:8000` | Browser origin for the callback and sign-out redirects. |
| `SAMURAIBFF_AUTH_ALLOWED_ORIGINS` | empty | Extra browser origins, comma-separated. |
| `SAMURAIBFF_WS_MAX_DURATION_S` | `14400` (4 h) | Longest time a recording WebSocket may stay open. |
| `SAMURAIBFF_ACCESS_RECHECK_INTERVAL_S` | `30` | How often open sockets are re-checked, in one batched query cycle. |
| `SAMURAIBFF_ACCESS_RECHECK_GRACE_S` | `120` | How long sockets stay open while the database cannot answer. |
| `SAMURAIBFF_ACCESS_RECHECK_TIMEOUT_S` | `5` | Statement timeout of each re-check query. |
| `SAMURAIBFF_KEYCLOAK_ADMIN_*` | empty | Optional Keycloak adapter for API keys. See [Keycloak setup](#keycloak-setup). |
| `SAMURAIBFF_KEYCLOAK_USER_ADMIN_*` | off | Optional Keycloak adapter for **Add person**. See [Keycloak setup](#keycloak-setup). |

The override does not change `COMPOSE_BIND_IP`. Ports stay on `127.0.0.1`.
For remote access, put a reverse proxy with TLS in front, and set
`SAMURAIBFF_PUBLIC_ORIGIN_URI` to the public `https://` origin.

Do not commit `.env`, client secrets, admin tokens or user tokens.

### 3. Create the organization and the first Admin

Nanosamurai never makes the first login an Admin and never matches accounts by
email. Create the first Admin with the operator command. You need:

- the tenant UUID that your provider puts in the tenant claim,
- the person's subject (`sub` claim) at your provider.

```bash
docker compose exec samuraibff java -cp /app/samuraibff.jar clojure.main \
  -m samuraibff.tools.principals provision \
  --tenant 11111111-4111-8111-a111-111111111111 --tenant-name "Acme" \
  --issuer https://id.example.com/realms/acme --subject <sub> \
  --role admin --name "Ada Admin" --email ada@example.com
```

On Windows, run it in PowerShell (use a backtick instead of `\` to continue
lines), or in Git Bash with `MSYS_NO_PATHCONV=1` in front, so the jar path is
not rewritten.

`--issuer` must equal `SAMURAIBFF_AUTH_ISSUER` exactly. `--tenant-name`
also creates the tenant if it does not exist. The command prints ids and
roles, never emails or secrets, and writes an audit event.

Other commands: `set-role`, `set-status`, `list`, `register-key` (see
[API keys](#api-keys)), `legacy-report` and `assign-owner` (see
[Sessions recorded before access control](#sessions-recorded-before-access-control)).

### 4. Add more people

- **With the Keycloak user adapter:** an Admin opens **Administration →
  People → Add person**. Keycloak sends a setup email. The person becomes
  active after their first login with a verified email.
- **With any provider:** create the account at your provider, then run
  `provision` with its `sub` (usually with `--role member`). In the app,
  **Add person** is off and tells the Admin to ask the operator.

Admins change roles and suspend or reactivate people in **People** with any
provider. A suspended person loses access on their next request. With a
provider other than Keycloak, suspension does not disable their account at the
provider.

### 5. Stay signed in, and sign out

While you use the app, it refreshes your session in the background with the
provider's refresh token (kept in an HttpOnly cookie that only the refresh
endpoint receives). Your provider's session settings decide how long you stay
signed in. If the provider issues no refresh token, the app signs you in again
when the access token expires, silently while the provider session lasts.

A recording keeps running when the access token expires: the token is checked
only when the recording starts. Nanosamurai re-checks open recordings against
its database and stops them when your access is removed, or after
`SAMURAIBFF_WS_MAX_DURATION_S` (4 hours by default). The app then tells you
why.

**Sign out** clears the Nanosamurai cookies. When discovery lists an
`end_session_endpoint`, it also ends the session at your provider. The browser
client must allow `<origin>/` as a post-logout redirect URI; otherwise the
provider shows an error page.

## API keys

API keys let scripts and the [Python SDK](apis-and-extension-points.md#python-sdk-and-cli)
call Nanosamurai. A key is an OAuth client at your provider (client id and
secret). The SDK exchanges it for short-lived access tokens with the
`client_credentials` grant. Nanosamurai never stores the secret.

| | Personal key | Organization key |
| --- | --- | --- |
| Who creates it | Builder or Admin, for themselves | Admin |
| Acts as | Its owner | Itself |
| Sessions it records | Belong to the owner, marked "via API key" | Belong to the key; visible to its manager, or to everyone, as set on the key |
| Reads | Only the sessions it recorded (default), or everything the owner can read | Only its own sessions |
| Managed in the UI by | The owner | The key's manager, or Admins |

In **API Credentials**, Admins see every key of the organization, Builders
the keys they manage, and Members none.

Keys never manage people, keys, publishing or defaults. When an owner loses the
Builder role, their personal keys stop working, and the organization keys they
managed pass to the Admins.

How you create a key depends on the provider:

- **With the Keycloak admin adapter:** **API Credentials → Create** creates
  the Keycloak client and shows the secret once. **Rotate** and **Revoke**
  work in the app.
- **With any provider:** at your provider, create a confidential client with
  the `client_credentials` grant, the tenant claim and the BFF audience. Then
  register it as an organization key:

  ```bash
  docker compose exec samuraibff java -cp /app/samuraibff.jar clojure.main \
    -m samuraibff.tools.principals register-key \
    --tenant <tenant UUID> --issuer https://id.example.com/realms/acme \
    --subject <client's sub> --client-id <client id> --name "Reporting" \
    --audience tenant
  ```

  `--audience` is `tenant` (everyone in the organization) or `private` (only
  the manager). Add `--manager <person id>` to make a Builder or Admin the
  manager; without it, Admins manage the key. Admins then see the key in
  **API Credentials**, can change its manager and audience, and can revoke it.
  Rotate the secret at your provider. **Revoke** blocks the key in
  Nanosamurai at once; also disable the client at your provider.

Use the access token, never the client secret, to call the API:

```bash
curl --fail-with-body \
  --header "Authorization: Bearer ${NANOSAMURAI_ACCESS_TOKEN}" \
  http://127.0.0.1:8000/api/me
```

Get the token from your provider's `token_endpoint` (listed in discovery). The
SDK does this for you from the issuer, client id and secret.

## Keycloak setup

Keycloak is optional. Use this checklist if you choose it. Replace the example
hosts and UUIDs with your own.

1. **Realm.** Create a realm. The issuer is
   `https://keycloak.example.com/realms/<realm>`.
2. **Browser client `bff-web`.** OpenID Connect, client authentication off,
   standard flow on, PKCE S256. Valid redirect URI
   `https://nanosamurai.example.com/auth/callback`, valid post-logout redirect
   URI `https://nanosamurai.example.com/` (or `+`), web origin
   `https://nanosamurai.example.com`.
3. **Tenant claim.** Give each user a `tenant_id` attribute that only
   administrators can edit. Add a protocol mapper that copies it into the
   access token as a string.
4. **Audience.** Browser tokens carry `azp=bff-web`. For machine clients, add
   an audience mapper that puts `bff-web` in `aud`.
5. **Optional: API keys in the app.** Create a confidential client
   `bff-admin` with service accounts on. Give its service account only the
   `realm-management` roles `view-clients` and `manage-clients`. Set:

   ```dotenv
   SAMURAIBFF_KEYCLOAK_ADMIN_ISSUER=https://keycloak.example.com/realms/<realm>
   SAMURAIBFF_KEYCLOAK_ADMIN_REALM=<realm>
   SAMURAIBFF_KEYCLOAK_ADMIN_CLIENT_ID=bff-admin
   SAMURAIBFF_KEYCLOAK_ADMIN_CLIENT_SECRET=<from your secret store>
   ```

6. **Optional: Add person in the app.** Create a separate confidential client
   (for example `bff-user-admin`) limited to user management in this realm,
   and configure SMTP for the realm. Set
   `SAMURAIBFF_KEYCLOAK_USER_ADMIN_ENABLED=true` and the matching
   `SAMURAIBFF_KEYCLOAK_USER_ADMIN_ISSUER`, `_REALM`, `_CLIENT_ID`,
   `_CLIENT_SECRET`, `_SETUP_CLIENT_ID` (`bff-web`) and
   `_SETUP_REDIRECT_URI` (`<origin>/`).

Restart SamuraiBFF after you change these values. Without step 5 or 6, that
feature is off, and the app tells the user to ask the operator.

## Other identity providers

Nanosamurai uses standard OIDC for sign-in, sign-out, REST and WebSockets.
Check these points for your provider:

- **Tenant claim.** Most providers need a custom claim or attribute mapping
  for `tenant_id`. Use `SAMURAIBFF_AUTH_TENANT_CLAIM` if your claim has
  another name. The value must be a UUID string.
- **Audience.** Configure the provider to put the BFF audience in `aud`, or set
  `SAMURAIBFF_AUTH_AUDIENCE` to the audience it issues. SamuraiBFF never
  accepts an ID token as a credential. It recognizes Keycloak ID tokens by
  their `typ` claim. Many other providers do not mark ID tokens, so give access
  tokens their own API audience (not the browser client id) and set
  `SAMURAIBFF_AUTH_AUDIENCE` to it and `SAMURAIBFF_AUTH_CLIENT_ID` to the
  browser client id.
- **Machine client id.** If machine tokens do not carry `azp`, set
  `SAMURAIBFF_AUTH_CLIENT_CLAIM` (for example `cid` for Okta).
- **Signing.** Tokens must use RS256.
- **People and API keys.** Use `provision` and `register-key`. The in-app
  **Add person** and **Create** key buttons need the Keycloak adapters.

We have not tested every provider. Run the checks below before you invite
users.

## Check your setup

1. Discovery:

   ```bash
   curl --fail --show-error https://id.example.com/realms/acme/.well-known/openid-configuration
   ```

   `issuer` must equal `SAMURAIBFF_AUTH_ISSUER`.

2. Login redirect:

   ```bash
   curl --include --max-redirs 0 "http://127.0.0.1:8000/auth/login?next=%2Flive"
   ```

   `Location` must point to your provider's `authorization_endpoint` with
   `client_id=bff-web`, `code_challenge_method=S256` and your callback URL.
   `503 identity-provider-unavailable` means the BFF cannot read discovery.

3. Sign in as the first Admin. The top bar shows your name and role. Record a
   session, then open **People**.

4. Check a token. Inspect tokens locally; never paste production tokens into
   public JWT tools.

   ```bash
   curl --fail --show-error -H "Authorization: Bearer ${ACCESS_TOKEN}" \
     http://127.0.0.1:8000/api/me
   ```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| The provider rejects the redirect URI | The callback in the `Location` header of `/auth/login` must match the client's redirect URIs. Check `SAMURAIBFF_PUBLIC_ORIGIN_URI` and proxy headers. |
| `/auth/login` returns 503 | The BFF container cannot reach `{issuer}/.well-known/openid-configuration`, or its `issuer` differs from `SAMURAIBFF_AUTH_ISSUER`. |
| Signed in, but "Your account is not set up" | `/api/me` shows the access state `not_provisioned`: no person matches this issuer and `sub`, or the tenant claim does not match their tenant. Run `provision`. |
| "Finish setting up your account" | The person was added with **Add person** and has not verified their email yet. |
| An API key gets `403 access-not-provisioned` | Register the client with `register-key`, and check that its client id is in `azp` (or in `SAMURAIBFF_AUTH_CLIENT_CLAIM`). |
| Sign-out ends on a provider error page | Add `<origin>/` as a post-logout redirect URI. |
| Tokens fail after a signing-key rotation | Keys are cached for up to five minutes. Keep the old and new keys published together during rotation. |

## Limits

- Local mode has no sign-in. Use it only on `127.0.0.1`.
- Tokens must be RS256 JWTs. Nanosamurai checks them locally; it does not ask
  the provider whether a token was revoked. Use short token lifetimes.
- The API reads a token from the `Authorization: Bearer` header, then from the
  HttpOnly cookie, never from a query parameter. It allows 30 seconds of clock
  skew.
- To end someone's access, suspend them in **People**. That stops their open
  recordings within about a minute. Disabling them only at the provider stops
  new sign-ins, but an open recording continues until the maximum duration.
- Electron sign-out clears only the Nanosamurai cookie.
- In-app **Add person**, and creating and rotating keys in the app, need the
  Keycloak adapters.

Before you expose Nanosamurai beyond localhost, also read
[Deployment and security boundaries](deployment-and-security.md).
