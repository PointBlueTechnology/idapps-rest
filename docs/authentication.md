# Authenticating to the Identity Applications REST API

Identity Applications (the User Application, or RBPM) accepts an OAuth 2 bearer token from its own authorization
server, OSP (One SSO Provider). This page covers:

1. how to get a token;
2. how to keep using it without signing in again;
3. what OSP's settings mean for scripts and agents;
4. the trap that locks a user out.

Everything here was checked on a lab running Identity Manager 4.10, in October 2026, unless it says otherwise.

## In short

1. Sign the person in **once** with OSP's password grant, using a client that has a secret (normally `rbpmrest`).
2. Keep the **refresh token**. Get access tokens from it as they expire (two minutes, by default).
3. Send `Authorization: Bearer <access token>` on every call.
4. **Never sign in once per call.** Each password sign-in writes to the user's `oidpInstanceData`, and when it is full
   that user can no longer sign in anywhere ([below](#the-oidpinstancedata-trap)).

## The token endpoint

```
POST https://<apps host>/osp/a/idm/auth/oauth2/token
Authorization: Basic base64(<client id>:<client secret>)
Content-Type: application/x-www-form-urlencoded
Accept: application/json
```

The client credentials go in the `Authorization` header (HTTP Basic), never in the body.

### Clients

OSP's clients are configured with the Identity Applications (the client ids are per installation; these are the usual
ones):

| Client id | What it is |
|---|---|
| `rbpmrest` | the client meant for REST calls; use it for scripts and agents |
| `rbpm` | the dashboard's own client; it also worked for REST calls on the lab |

Use a client **with a secret** (a confidential client). OSP keeps the refresh tokens of public clients for a much
shorter time ([lifetimes](#lifetimes)), and the refresh grant needs the secret.

## Signing in: the password grant

```bash
curl -s https://apps.example.com/osp/a/idm/auth/oauth2/token \
  -u "rbpmrest:$CLIENT_SECRET" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode grant_type=password \
  --data-urlencode "username=$APPS_USER" \
  --data-urlencode "password=$APPS_PASSWORD"
```

| Field | Required | Value |
|---|---|---|
| `grant_type` | yes | `password` |
| `username` | yes | the person's login name, or their full DN (`cn=jsmith,ou=users,o=data`); both worked |
| `password` | yes | the person's password |

The answer, with lifetimes in seconds:

```json
{"access_token": "eyJ…", "token_type": "bearer", "expires_in": 120, "refresh_token": "eyJ…"}
```

- **Token format:** the tokens were JWTs on the lab (`com.netiq.idm.osp.oauth.access-token-format.format = jwt`). Treat them as opaque; don't
  depend on their claims.
- **Whose name:** the token stands for the person, and the applications record their actions under the person's DN.
  The client id appears nowhere in a request's history.

## Keeping going: the refresh grant

```bash
curl -s https://apps.example.com/osp/a/idm/auth/oauth2/token \
  -u "rbpmrest:$CLIENT_SECRET" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode grant_type=refresh_token \
  --data-urlencode "refresh_token=$REFRESH_TOKEN"
```

The answer is a new access token only: `{"access_token", "token_type", "expires_in"}`.

- **No rotation:** OSP does not rotate the refresh token, so the same one works again for the next refresh.
- **The secret is needed:** a refresh with a wrong client secret was refused with 401 (`invalid_request`). A refresh
  token on its own is not enough.
- **Outlives the session:** a refresh token still worked 60 minutes after the sign-in, past OSP's session timeout (45
  minutes on the lab). An idle script can come back within the refresh token's lifetime without signing in again.
- **Writes nothing:** a refresh adds nothing to `oidpInstanceData`.

## Calling the API

Send the access token on every call:

```bash
curl -s "https://apps.example.com/IDMProv/rest/access/tasks/list?size=10" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Accept: application/json'
```

- **Renew early:** renew the access token a little before `expires_in` runs out; 20 seconds early works well.
- **A refused token:** an expired or invalid access token is refused with 401.
- **A refresh token that stops working** (expired, or revoked) gets an error from the token endpoint. Then the person
  has to sign in with their password again. Its exact status was not checked on the lab.

## Lifetimes

OSP's settings live in its `ism-configuration.properties`. The values below are the lab's, and match the usual
defaults:

| Setting | Lab value | Meaning |
|---|---|---|
| `com.netiq.idm.osp.oauth.accessTokenTTL` | 120 | access token, seconds |
| `com.netiq.idm.osp.oauth.refreshTokenTTL` | 2592000 (30 days) | refresh token of a client with a secret |
| `com.netiq.idm.osp.oauth.public.refreshTokenTTL` | 2700 (45 minutes) | refresh token of a public client |
| `com.netiq.idm.osp.sessionTTL` | 2700 | OSP's session, seconds |

A script that keeps a refresh token therefore needs the person's password at most every 30 days, if it keeps using the
refresh token within that time.

## The oidpInstanceData trap

OSP writes to the signed-in user's `oidpInstanceData` attribute on every **password** sign-in. On the lab each one
added about 280 bytes. At about 32 KB eDirectory refuses the write (`-649`, insufficient buffer), and from then on
every sign-in for that user fails:

- **The token endpoint answers** HTTP 500 `{"error": "server_error", "error_description": "Unexpected error.",
  "sub_error": "exception"}`.
- **OSP's log reads** "Error writing instance data for '<user DN>'".
- **How it happened on the lab:** after two days of a script that signed in once per call.

**To avoid it:** sign in once, and keep and refresh the tokens.

**To recover:** delete the value of the user's `oidpInstanceData` (with LDAP, as an administrator). OSP starts it
afresh, and the user's OSP sessions end.

## Keeping tokens safe

- **Never log or print a token.** To show that you have one, print its length and expiry instead.
- **Store refresh tokens encrypted.** A refresh token stands for the person for up to 30 days, with the client secret.
- **Keep the client secret like a password,** apart from the refresh tokens.
- **Each person signs in as themselves.** Their own rights then apply, and the applications record actions under their
  name.
