# JWT authentication scenarios

Use these scenarios to inspect JWT authentication through the lint server's HTTP API. Each numbered script sends exactly one request and prints the request and response, following the main [demo walkthrough](../README.md).

## Setup

Follow the root README's [setup](../README.md#setup), then start the demo in the first terminal:

```shell
./demo.sh start
```

Run the scenario commands below from the **repository root**, in a second terminal. They reuse the existing server address, TLS trust, JWKS fixture, issuer, audience, and scope configuration. No additional Python packages or GitHub token are needed for these auth-only scenarios.

The `terminaloutput` blocks below are **expected output templates**, not captured live responses. They use the default HTTP address. For HTTPS, start with `./demo.sh start --https`; the address becomes `https://localhost:8443` and the status line may use HTTP/2. Header casing/order, Content-Length, and charset parameters may vary. JSON field order is insignificant. Run-specific values use typed placeholders, as in the root README; repeated request-id placeholders within one scenario must match.

Tokens are generated just before each request. Keys remain under ignored `.demo-state/`. Printed Authorization headers contain local demo tokens; do not use these keys outside the demo. Individual scenario scripts display expectations but do not assert them; use the runner below for automatic checks.

Every scenario sends the body from `requests/lint-batch.json`. Rejections must happen before config loading, spec fetching, or Insights submission. The valid-token control deliberately suppresses Content-Type and stops at HTTP 415, avoiding those downstream operations as well. Its printed empty `Content-Type:` line tells curl to omit the header; it is not an empty header sent to the server.

## Scenarios

### 1. Valid JWT reaches request validation

**Request:** A correctly signed RS256 token with the trusted issuer, expected audience, and both required scope values. Content-Type is deliberately omitted.

```shell
./jwt-auth-scenarios/01-valid-token-reaches-validation.sh
```

```terminaloutput
Scenario: valid
Expected: HTTP 415, JSON code=UNSUPPORTED_MEDIA_TYPE; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type:

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 415 Unsupported Media Type
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"UNSUPPORTED_MEDIA_TYPE","message":"The request Content-Type must be application/json.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 415 with UNSUPPORTED_MEDIA_TYPE. Authentication succeeded; request validation stops the request before loading config, fetching specs, or submitting reports.

### 2. Bad signature

**Request:** The trusted issuer, expected audience, required scopes, and published kid, but signed using a different RSA private key.

```shell
./jwt-auth-scenarios/02-bad-signature.sh
```

```terminaloutput
Scenario: bad-signature
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. Matching claims and kid must not bypass signature verification.

### 3. Wrong audience

**Request:** A correctly signed JWT with aud=another-api instead of skeptic-lint-demo.

```shell
./jwt-auth-scenarios/03-wrong-audience.sh
```

```terminaloutput
Scenario: wrong-audience
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. A token for another API must be rejected.

### 4. Expired token

**Request:** A correctly signed JWT whose exp is two minutes in the past, beyond the 30-second clock-skew allowance.

```shell
./jwt-auth-scenarios/04-expired-token.sh
```

```terminaloutput
Scenario: expired
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. Expired credentials must be rejected.

### 5. Unknown key ID

**Request:** A correctly signed JWT with kid=unpublished-key, absent from the served JWKS.

```shell
./jwt-auth-scenarios/05-unknown-key-id.sh
```

```terminaloutput
Scenario: unknown-key
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. An available JWKS without the requested key is an invalid token, not a JWKS outage.

### 6. Unknown issuer

**Request:** A JWT with iss=https://untrusted.example/issuer. Its signing key and other claims match the demo.

```shell
./jwt-auth-scenarios/06-unknown-issuer.sh
```

```terminaloutput
Scenario: unknown-issuer
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. An untrusted issuer must be rejected, with a JSON error and correlation ID.

### 7. Missing token

**Request:** The valid batch body without an Authorization header.

```shell
./jwt-auth-scenarios/07-missing-token.sh
```

```terminaloutput
Scenario: no-token
Expected: HTTP 401, JSON code=AUTHENTICATION_REQUIRED; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"AUTHENTICATION_REQUIRED","message":"A Bearer token is required.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with AUTHENTICATION_REQUIRED. No Bearer token was supplied.

### 8. Missing required scope value

**Request:** A valid JWT with scope=lint:run, omitting the configured reports:read scope value.

```shell
./jwt-auth-scenarios/08-wrong-scope.sh
```

```terminaloutput
Scenario: wrong-scope
Expected: HTTP 403, JSON code=ACCESS_DENIED; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 403 Forbidden
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"ACCESS_DENIED","message":"JWT does not satisfy the configured claim values.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 403 with ACCESS_DENIED. Authentication passed, but authorization failed.

### 9. Missing scope claim

**Request:** A valid JWT without the scope claim.

```shell
./jwt-auth-scenarios/09-missing-scope.sh
```

```terminaloutput
Scenario: missing-scope
Expected: HTTP 403, JSON code=ACCESS_DENIED; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 403 Forbidden
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"ACCESS_DENIED","message":"JWT does not satisfy the configured claim values.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 403 with ACCESS_DENIED. The required authorization claim must be present.

### 10. Missing expiry claim

**Request:** An otherwise valid JWT without exp.

```shell
./jwt-auth-scenarios/10-missing-expiry.sh
```

```terminaloutput
Scenario: missing-expiry
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. The server requires an expiry even when the signature and other claims match.

### 11. Missing issuer claim

**Request:** A signed JWT without iss.

```shell
./jwt-auth-scenarios/11-missing-issuer.sh
```

```terminaloutput
Scenario: missing-issuer
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. A token without a trusted issuer cannot authenticate.

### 12. Missing audience claim

**Request:** An otherwise valid JWT without aud.

```shell
./jwt-auth-scenarios/12-missing-audience.sh
```

```terminaloutput
Scenario: missing-audience
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. The expected API audience must be present.

### 13. Missing key ID

**Request:** An otherwise valid JWT without kid in its header.

```shell
./jwt-auth-scenarios/13-missing-key-id.sh
```

```terminaloutput
Scenario: missing-key-id
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. The verification key must be identifiable from the JWT header.

### 14. Token not yet valid

**Request:** A correctly signed JWT with nbf five minutes in the future, beyond the 30-second clock-skew allowance.

```shell
./jwt-auth-scenarios/14-not-yet-valid.sh
```

```terminaloutput
Scenario: not-yet-valid
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. The token must not authenticate before its validity window.

### 15. Unsigned token

**Request:** A JWT using alg=none with an empty signature, but otherwise matching claims.

```shell
./jwt-auth-scenarios/15-unsigned-token.sh
```

```terminaloutput
Scenario: unsigned
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: unsigned JWT, base64url.base64url.>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. Matching claims must never allow an unsigned token.

### 16. HS256 token

**Request:** A JWT signed with HS256 using a demo secret, rather than the required RS256 algorithm.

```shell
./jwt-auth-scenarios/16-hs256-token.sh
```

```terminaloutput
Scenario: hs256
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: HS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. An HMAC token must not authenticate against the RSA JWKS.

### 17. RSA384 token

**Request:** A JWT signed with the trusted RSA key using RS384 rather than RS256.

```shell
./jwt-auth-scenarios/17-rsa384-token.sh
```

```terminaloutput
Scenario: rsa384
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer <bearer-token: RS384 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. A trusted key must not allow an unsupported signing algorithm.

### 18. Malformed JWT

**Request:** Authorization: Bearer not-a-jwt with the valid batch body.

```shell
./jwt-auth-scenarios/18-malformed-token.sh
```

```terminaloutput
Scenario: malformed
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer not-a-jwt
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. Invalid JWT syntax must still produce a structured error.

### 19. Bearer header without a token

**Request:** Authorization: Bearer with no token value.

```shell
./jwt-auth-scenarios/19-empty-bearer.sh
```

```terminaloutput
Scenario: empty-bearer
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. A present but unusable Authorization header is distinct from an absent header.

### 20. Unsupported Basic authentication

**Request:** Authorization: Basic dXNlcjpwYXNz rather than a Bearer token.

```shell
./jwt-auth-scenarios/20-basic-auth.sh
```

```terminaloutput
Scenario: basic-auth
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Basic dXNlcjpwYXNz
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. Basic authentication cannot authorize the lint endpoint.

### 21. Malformed Authorization header

**Request:** Authorization: Bearer token extra, containing extra whitespace-separated data.

```shell
./jwt-auth-scenarios/21-malformed-header.sh
```

```terminaloutput
Scenario: malformed-header
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.
Expected response requestId: <request-id: UUID>

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: <request-id: UUID>
Authorization: Bearer token extra
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. Header parsing errors must not become bare responses or HTTP 500 errors.

### 22. Server-generated request ID

**Request:** A bad-signature JWT and valid batch body, with no X-Request-Id header.

```shell
./jwt-auth-scenarios/22-generated-request-id.sh
```

```terminaloutput
Scenario: bad-signature
Expected: HTTP 401, JSON code=INVALID_TOKEN; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_TOKEN","message":"The Bearer token is invalid or expired.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401 with INVALID_TOKEN. The server generates a UUID and returns the same value in the JSON body, X-Request-Id response header, and failure log.

### 23. Malformed request ID with an invalid JWT

**Request:** A bad-signature JWT and valid batch body with X-Request-Id: not-a-uuid.

```shell
./jwt-auth-scenarios/23-malformed-request-id.sh
```

```terminaloutput
Scenario: bad-signature
Expected: HTTP 400, JSON code=INVALID_REQUEST; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.

=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
X-Request-Id: not-a-uuid
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json

<request-body: JSON object from requests/lint-batch.json>

=== Response ===
HTTP/1.1 400 Bad Request
www-authenticate: Bearer realm="Skeptic Server"
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_REQUEST","message":"X-Request-Id must be a valid UUID.","details":[{"field":"X-Request-Id","message":"Supply a UUID or omit the header."}],"requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 400 with INVALID_REQUEST. Request-ID validation takes precedence; the response contains a new UUID and identifies X-Request-Id in details.

## Correlate a failure with server logs

Each supplied request ID must be preserved in the response body and header. Find the same ID in the server's `request.failed` log. Server logs must not contain the bearer token.

To supply a known UUID:

```shell
DEMO_REQUEST_ID=12345678-1234-4234-8234-123456789abc ./jwt-auth-scenarios/02-bad-signature.sh
```

Expect HTTP 401 with INVALID_TOKEN and requestId `12345678-1234-4234-8234-123456789abc` in the JSON body and X-Request-Id response header. Scenario 22 deliberately omits the ID; scenario 23 supplies a malformed value, so both expect server-generated UUIDs instead.

## Verify request isolation

Run against the same server without restarting:

```shell
./jwt-auth-scenarios/01-valid-token-reaches-validation.sh
./jwt-auth-scenarios/02-bad-signature.sh
./jwt-auth-scenarios/01-valid-token-reaches-validation.sh
```

**Expected:** 415 → 401 → 415, with a fresh requestId each time. The invalid request must not inherit the first request's authentication, and its rejection must not poison the next valid request. Individual request/response templates appear in scenarios 1 and 2 above.

## Run all scenarios with assertions

With the demo server and fixtures already running:

```shell
python3 -B jwt-auth-scenarios/run_all.py
```

**Expected:** PASS/FAIL for all 23 scenarios, followed by the three isolation requests. When all expectations hold, the final summary reports `26 passed; 0 failed` and a response directory under `.demo-state/jwt-auth-results/<run>/`. Any request/assertion failure produces a nonzero exit code. The runner starts no services.

Assertions check status, exact JSON code/message, UUID requestId, body/header correlation, supplied-ID preservation, fresh IDs across requests, JSON Content-Type, Cache-Control, malformed-ID details, and the Bearer realm for verifier rejections. Headers and bodies are saved for diagnosis; raw Authorization headers are not saved. Automated runs generate their own request IDs and ignore DEMO_REQUEST_ID.

Log correlation and absence of downstream work still require inspecting server/fixture logs; the runner checks HTTP responses only. Successful linting and SARIF responses remain covered by the root README's batch scenarios; those require private config access and publish reports.

## Check the runner and token fixtures

```shell
python3 -B -m unittest discover -s jwt-auth-scenarios/tests -v
```

**Expected:** Seven tests pass. These check signatures, deliberate claim changes, response assertions, and runner exit behavior using temporary files and keys. They do not start services or validate live server responses.
