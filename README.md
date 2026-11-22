# Specmatic Lint Server demo

This demo uses local API-spec and JWKS fixtures plus the private central configuration repository. Each numbered scenario makes one HTTP request to the lint server. Run scenarios individually to inspect the response and server logs. Scenarios show request metadata; large-spec scenarios redact credentialed request bodies.

The `terminaloutput` blocks are output templates. Run-specific values use `<name: type or format>`, for example `<request-id: UUID>` or `<timestamp: ISO 8601 date-time, UTC>`. Repeated placeholder names refer to the same value within one request; each request generates new values. Integer placeholders are unquoted, so these templates are illustrative rather than literal JSON. Request bodies are abbreviated as typed placeholders; credentials are represented by placeholders. Scenario responses were checked against the running HTTPS server; HTTP runs use HTTP/1.1 status lines. Setup, startup, and Insights recovery output is representative. Finding counts and maturity depend on the configuration revision.

## Setup

Requirements: Docker, Python 3, Git, GitHub CLI, curl, OpenSSL, netcat, and a Specmatic Enterprise service-account licence.

Lint server and spec-source mock run using `specmatic/enterprise-snapshots:1.29.3`. Start Docker before running the demo. The demo uses bridge networking and publishes lint server on `127.0.0.1:8000` (HTTP) or `127.0.0.1:8443` (HTTPS); Docker Desktop host networking is not required. Lint server reaches JWKS fixtures through `host.docker.internal:8765` and Specmatic spec-source mock through `host.docker.internal:8766`. An explicit host-gateway mapping also supports Docker Engine on Linux. Fixture server binds to `0.0.0.0:8765`; it serves demo public keys and existing small specs.

Large YAML fixtures live in `specs/`: 5 MiB for the smaller check, exactly 25 MiB (26,214,400 ASCII code points) for acceptance, and 25 MiB + 1 code point for rejection. Fixtures are static files. The fixture server serves both boundary files directly.

Pull the image before starting:

```shell
docker pull specmatic/enterprise-snapshots:1.29.3
```

```terminaloutput
1.29.3: Pulling from specmatic/enterprise-snapshots
```

To use a specific image tag, set `SPECMATIC_ENTERPRISE_IMAGE=specmatic/enterprise:<tag>` when running `./demo.sh start`.

The startup script mounts `~/.specmatic/specmatic-license.txt` read-only into the container. If the licence is elsewhere, set `SPECMATIC_LICENSE_PATH` to its file before starting the server. `SPECMATIC_LICENSE_CONTENT` is passed through when supplied and takes precedence over the file. Each session directory is mounted into the container for cache and TLS files. Pressing Ctrl-C stops the container and fixture server.

Sign in to GitHub CLI using an account with read access to `specmatic/private-central-linter-config`:

```shell
gh auth login --hostname github.com
```

```terminaloutput
✓ Authentication complete.
```

Batch scenarios retrieve your token with `gh auth token --hostname github.com` and place it in the config repository URL. Keep generated authenticated request files private. Scenarios 16 and 17 suppress the credentialed body in terminal output.

## Demonstrate a missing licence

Before starting the server, point to a licence file that does not exist:

```shell
SPECMATIC_LICENSE_PATH=/does-not-exist/specmatic-license.txt ./demo.sh start
```

```terminaloutput
SPECMATIC_LICENSE_PATH does not point to a file.
```

**Expected:** The startup script exits with code 1 before starting the server.

This override applies only to this command. For normal startup below, use a valid licence at the default location or set `SPECMATIC_LICENSE_PATH` to its file.

## Demonstrate invalid licence content

You can also supply the licence directly through `SPECMATIC_LICENSE_CONTENT`. To demonstrate the server rejecting invalid content, run:

```shell
SPECMATIC_LICENSE_CONTENT='this-is-not-a-valid-license' ./demo.sh start
```

```terminaloutput
{"timestamp":"<timestamp: ISO 8601 date-time, UTC>","level":"INFO","service":"lint-server","component":"server","event":"server.start_failed","outcome":"failure","exceptionType":"io.specmatic.license.core.LicenseLoadException","errorMessage":"Unable to parse license key. Please ensure it is a valid Specmatic license key."}
```

**Expected:** The server rejects the licence during startup and exits with code 1.

## Start the server

Start with HTTP:

```shell
./demo.sh start
```

```terminaloutput
Starting the lint server on http://127.0.0.1:8000
Run one scenario at a time from a second terminal. Press Ctrl-C here when done.
Running command: docker run --rm --name skeptic-lint-demo-<process-id: positive integer> --publish 127.0.0.1:8000:8000 --mount type=bind\,source=<demo-directory: absolute path>/.demo-state/session-<session-time: yyyyMMdd-HHmmss>-<process-id: positive integer>\,target=/demo --workdir /demo --add-host host.docker.internal:host-gateway --mount type=bind\,source=<license-file: absolute path>\,target=/specmatic-license.txt\,readonly --env SPECMATIC_LICENSE_PATH=/specmatic-license.txt specmatic/enterprise:latest lint-server --port=8000 --jwt-issuer=http://127.0.0.1:8765/demo-issuer --jwt-jwks-url=http://host.docker.internal:8765/jwks.json --jwt-audience=skeptic-lint-demo --jwt-match=scope=\"lint:run\ reports:read\" --allowed-config-repo-url=https://github.com/specmatic/private-central-linter-config.git --allowed-spec-download-host=host.docker.internal
{"timestamp":"<timestamp: ISO 8601 date-time, UTC>","level":"INFO","service":"lint-server","component":"server","event":"server.started","port":8000,"scheme":"http"}
```

Or start with HTTPS:

```shell
./demo.sh start --https
```

```terminaloutput
Starting the lint server on https://localhost:8443
Run one scenario at a time from a second terminal. Press Ctrl-C here when done.
Running command: docker run --rm --name skeptic-lint-demo-<process-id: positive integer> --publish 127.0.0.1:8000:8000 --mount type=bind\,source=<demo-directory: absolute path>/.demo-state/session-<session-time: yyyyMMdd-HHmmss>-<process-id: positive integer>\,target=/demo --workdir /demo --add-host host.docker.internal:host-gateway --mount type=bind\,source=<license-file: absolute path>\,target=/specmatic-license.txt\,readonly --env SPECMATIC_LICENSE_PATH=/specmatic-license.txt specmatic/enterprise:latest lint-server --port=8000 --jwt-issuer=http://127.0.0.1:8765/demo-issuer --jwt-jwks-url=http://host.docker.internal:8765/jwks.json --jwt-audience=skeptic-lint-demo --jwt-match=scope=\"lint:run\ reports:read\" --allowed-config-repo-url=https://github.com/specmatic/private-central-linter-config.git --allowed-spec-download-host=host.docker.internal
{"timestamp":"<timestamp: ISO 8601 date-time, UTC>","level":"INFO","service":"lint-server","component":"server","event":"server.started","port":8443,"scheme":"https"}
```

HTTPS mode creates a local certificate and PKCS#12 keystore under `.demo-state/`, then starts the lint server at `https://localhost:8443`. The scenario scripts trust this certificate automatically, so they verify TLS without disabling certificate checks. The JWKS and specification fixtures remain local HTTP services; HTTPS covers the client connection to the lint server.

### Start with valid licence content

To demonstrate successful startup using `SPECMATIC_LICENSE_CONTENT`, load the valid service-account licence from your local file:

Start with HTTP:

```shell
SPECMATIC_LICENSE_CONTENT="$(cat ~/.specmatic/specmatic-license.txt)" ./demo.sh start
```

```terminaloutput
Starting the lint server on http://127.0.0.1:8000
Run one scenario at a time from a second terminal. Press Ctrl-C here when done.
Running command: docker run --rm --name skeptic-lint-demo-<process-id: positive integer> --publish 127.0.0.1:8000:8000 --mount type=bind\,source=<demo-directory: absolute path>/.demo-state/session-<session-time: yyyyMMdd-HHmmss>-<process-id: positive integer>\,target=/demo --workdir /demo --add-host host.docker.internal:host-gateway --mount type=bind\,source=<license-file: absolute path>\,target=/specmatic-license.txt\,readonly --env SPECMATIC_LICENSE_PATH=/specmatic-license.txt specmatic/enterprise:latest lint-server --port=8000 --jwt-issuer=http://127.0.0.1:8765/demo-issuer --jwt-jwks-url=http://host.docker.internal:8765/jwks.json --jwt-audience=skeptic-lint-demo --jwt-match=scope=\"lint:run\ reports:read\" --allowed-config-repo-url=https://github.com/specmatic/private-central-linter-config.git --allowed-spec-download-host=host.docker.internal
{"timestamp":"<timestamp: ISO 8601 date-time, UTC>","level":"INFO","service":"lint-server","component":"server","event":"server.started","port":8000,"scheme":"http"}
```

Or start with HTTPS:

```shell
SPECMATIC_LICENSE_CONTENT="$(cat ~/.specmatic/specmatic-license.txt)" ./demo.sh start --https
```

```terminaloutput
Starting the lint server on https://localhost:8443
Run one scenario at a time from a second terminal. Press Ctrl-C here when done.
Running command: docker run --rm --name skeptic-lint-demo-<process-id: positive integer> --publish 127.0.0.1:8000:8000 --mount type=bind\,source=<demo-directory: absolute path>/.demo-state/session-<session-time: yyyyMMdd-HHmmss>-<process-id: positive integer>\,target=/demo --workdir /demo --add-host host.docker.internal:host-gateway --mount type=bind\,source=<license-file: absolute path>\,target=/specmatic-license.txt\,readonly --env SPECMATIC_LICENSE_PATH=/specmatic-license.txt specmatic/enterprise:latest lint-server --port=8000 --jwt-issuer=http://127.0.0.1:8765/demo-issuer --jwt-jwks-url=http://host.docker.internal:8765/jwks.json --jwt-audience=skeptic-lint-demo --jwt-match=scope=\"lint:run\ reports:read\" --allowed-config-repo-url=https://github.com/specmatic/private-central-linter-config.git --allowed-spec-download-host=host.docker.internal
{"timestamp":"<timestamp: ISO 8601 date-time, UTC>","level":"INFO","service":"lint-server","component":"server","event":"server.started","port":8443,"scheme":"https"}
```

**Expected:** The server accepts the licence and stays running. The licence content is read from the file without printing it to the terminal. This override applies only to the selected command.

Use either startup command above, then continue with the scenarios.

In a second terminal, change to this demo directory and run the scenarios below, one at a time. Press Ctrl-C in the first terminal to stop the server.

## Scenarios

### 1. Health

**Request:** `GET /health` (no authentication)

```shell
./scenarios/01-health.sh
```

```terminaloutput
=== Request ===
GET https://localhost:8443/health

=== Response ===
HTTP/2 200
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"status":"up"}
```

**Expected:** HTTP 200 with `{"status":"up"}`. This confirms the server is responding over the selected protocol.

### 2. Readiness

**Request:** `GET /readiness` (no authentication)

```shell
./scenarios/02-readiness.sh
```

```terminaloutput
=== Request ===
GET https://localhost:8443/readiness

=== Response ===
HTTP/2 200
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"status":"ready"}
```

**Expected:** HTTP 200 with `{"status":"ready"}`. This reports whether the server can currently accept lint work.

### 3. Missing JWT

**Request:** `POST /skeptic/lint/reports` with the batch body from `requests/lint-batch.json` and no Authorization header.

```shell
./scenarios/03-no-token-401.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Content-Type: application/json
X-Request-Id: <request-id: UUID>

[credentialed request body omitted]

=== Response ===
HTTP/2 401
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"AUTHENTICATION_REQUIRED","message":"A Bearer token is required.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 401. The server rejects the request before loading configuration or fetching specs.

### 4. JWT scope mismatch

**Request:** The same batch POST, with a demo-generated RS256 JWT. Its signature, issuer, and audience are valid. The token's `scope` is `lint:run`; the configured exact value is `lint:run reports:read`.

```shell
./scenarios/04-wrong-scope-403.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP/2 403
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"ACCESS_DENIED","message":"JWT does not satisfy the configured claim values.","requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 403 because the token does not satisfy the exact claim match.

### 5. Status before linting

**Request:** `GET /status` (no authentication). Run this before the batch request.

```shell
./scenarios/05-status-before-lint.sh
```

```terminaloutput
=== Request ===
GET https://localhost:8443/status

=== Response ===
HTTP/2 200
{
  "status": "ready",
  "linterVersion": "1.29.0",
  "instanceId": "<instance-id: UUID>",
  "startedAt": "<started-at: ISO 8601 date-time, UTC>",
  "license": {
    "expiresAt": "<license-expiry: ISO 8601 date-time, UTC>",
    "status": "valid"
  },
  "insights": {
    "state": "healthy",
    "publishedReportCount": 0,
    "publishedBatchCount": 0,
    "unpublishedReports": []
  },
  "configs": []
}
```

**Expected:** HTTP 200. On a fresh server run, Insights is healthy with no published reports, and the config list is empty.

### 6. Batch lint

**Request:** `POST /skeptic/lint/reports` with two specs, a self-contained credentialed config Git URL, and a demo-generated RS256 JWT containing the required scope. The scenario retrieves the GitHub token just in time with `gh auth token --hostname github.com`, builds the request from `requests/lint-batch.json`, then saves it under `.demo-state/`.

```shell
./scenarios/06-batch-lint.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 200
Batch lint response:
  result: failure
  orders-api: failure, 13 finding(s), maturity=baseline
  payments-api: failure, 15 finding(s), maturity=baseline
  full response saved: .demo-state/lint-response.json
```

**Expected:** HTTP 200 with one report per spec. The lint `result` is `failure` because the small sample specs intentionally produce findings. The full response is saved to `.demo-state/lint-response.json`. The server queues each report for background Insights publishing and returns without waiting for that work.

### 7. Status after linting

**Request:** `GET /status` (no authentication). The script waits five seconds after the batch before making this request.

```shell
./scenarios/07-status-after-lint.sh
```

```terminaloutput
=== Request ===
GET https://localhost:8443/status

=== Response ===
HTTP/2 200
{
  "status": "ready",
  "linterVersion": "1.29.0",
  "instanceId": "<instance-id: UUID>",
  "startedAt": "<started-at: ISO 8601 date-time, UTC>",
  "license": {
    "expiresAt": "<license-expiry: ISO 8601 date-time, UTC>",
    "status": "valid"
  },
  "insights": {
    "state": "healthy",
    "lastDeliveredAt": "<last-delivered-at: ISO 8601 date-time, UTC>",
    "publishedReportCount": 2,
    "publishedBatchCount": 1,
    "unpublishedReports": []
  },
  "configs": [
    {
      "repoUrl": "https://github.com/specmatic/private-central-linter-config.git",
      "branch": "main",
      "commitSha": "<commit-sha: 40 hexadecimal characters>",
      "configPath": "specmatic-linter.yaml",
      "stale": false
    }
  ]
}
```

**Expected:** HTTP 200. The config snapshot shows the loaded branch and commit. After both pushes succeed, `publishedReportCount` should be 2 and the queue should be empty. The counter reflects successful Insights responses; any report still queued has not succeeded yet.

### 8. Invalid config repository token

**Request:** The batch POST with a valid demo JWT but a deliberately invalid GitHub token in the config repository URL. This demonstrates a bad central config credential without setting `CENTRAL_CONFIG_REPO_TOKEN` or changing your GitHub CLI login.

```shell
./scenarios/08-invalid-config-token.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
{"code":"CONFIG_UNAVAILABLE","message":"Configuration source is temporarily unavailable.","requestId":"<request-id: UUID>"}
HTTP 503
```

**Expected:** HTTP 503 with error code `CONFIG_UNAVAILABLE` and message `Configuration source is temporarily unavailable.` The JWT passes authentication, but the server cannot fetch the private configuration with the invalid GitHub token. No lint reports are produced. The generated request is saved to `.demo-state/lint-batch-invalid-config-token.json`.


To demonstrate a failed credential replacement with a warm cache, start a fresh server and run these three scenarios in sequence within five minutes. Use the same GitHub CLI login for both valid requests.

```shell
./scenarios/06-batch-lint.sh
./scenarios/08-invalid-config-token.sh
./scenarios/06-batch-lint.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 200
Batch lint response:
  result: failure
  orders-api: failure, 13 finding(s), maturity=baseline
  payments-api: failure, 15 finding(s), maturity=baseline
  full response saved: .demo-state/lint-response.json

=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
{"code":"CONFIG_UNAVAILABLE","message":"Configuration source is temporarily unavailable.","requestId":"<request-id: UUID>"}
HTTP 503

=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 200
Batch lint response:
  result: failure
  orders-api: failure, 13 finding(s), maturity=baseline
  payments-api: failure, 15 finding(s), maturity=baseline
  full response saved: .demo-state/lint-response.json
```

**Expected:** HTTP 200, then HTTP 503 with `CONFIG_UNAVAILABLE`, then HTTP 200. The middle request fails despite the cached snapshot. The final request succeeds with the original credentials. The two successful requests each queue two reports.

### 9. Download hostname outside the allowlist

**Request:** The batch POST with a valid demo JWT and the body from `requests/lint-unapproved-download-host.json`. The first spec uses the allowed hostname `host.docker.internal`; the second uses `localhost`. The server starts with `--allowed-spec-download-host=host.docker.internal`, so `localhost` does not match the configured `127.0.0.1` hostname.

```shell
./scenarios/09-unapproved-download-host-403.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
{"code":"SPEC_URL_NOT_ALLOWED","message":"The downloadUrl host is not allowed.","details":[{"field":"repository.specifications[1].downloadUrl","message":"The downloadUrl host is not allowed."}],"requestId":"<request-id: UUID>"}
HTTP 403
```

**Expected:** HTTP 403 with error code `SPEC_URL_NOT_ALLOWED`, message `The downloadUrl host is not allowed.`, and field `repository.specifications[1].downloadUrl`. The server rejects the entire batch before loading configuration or downloading either spec. No lint reports are produced or queued for Insights. This scenario does not need a GitHub token because download URLs are checked before fetching configuration.

### 10. Configuration repository outside the allowlist

**Request:** The batch POST with a valid demo JWT and the body from `requests/lint-unapproved-config-repo.json`. The config URL is `https://github.com/example/unapproved-linter-config.git`; the server only allows `https://github.com/specmatic/private-central-linter-config.git`. Both spec download URLs use the allowed hostname `host.docker.internal`.

```shell
./scenarios/10-unapproved-config-repo-403.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
{"code":"CONFIG_URL_NOT_ALLOWED","message":"Configuration repository URL is not allowed.","requestId":"<request-id: UUID>"}
HTTP 403
```

**Expected:** HTTP 403 with error code `CONFIG_URL_NOT_ALLOWED` and message `Configuration repository URL is not allowed.` The server rejects the entire batch before fetching configuration or downloading specs. No lint reports are produced or queued for Insights. This scenario does not need a GitHub token because the config URL is checked before fetching the repository. The allowlist checks the repository URL, so using the same `github.com` hostname does not grant access to another repository.

### 11. Clean batch lint

**Request:** The authenticated batch POST using `requests/lint-clean-batch.json`, which downloads the separate `specs/orders-api-clean.yaml` and `specs/payments-api-clean.yaml` specs. The original specs used by scenario 6 retain their intentional lint findings. Restart `./demo.sh start` after updating the demo so the fixture server serves the new files.

```shell
./scenarios/11-clean-batch-lint.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 200
Clean batch lint response:
  result: success
  orders-api-clean: success, 0 finding(s), maturity=platinum
  payments-api-clean: success, 0 finding(s), maturity=platinum
  full response saved: .demo-state/lint-clean-response.json
```

**Expected:** HTTP 200 with batch and per-spec `result` set to `success`, and zero SARIF findings under the configured `default` profile. The summary prints `0 finding(s)` for each spec. Inspect `.demo-state/lint-clean-response.json` for the full clean reports, including each SARIF run's empty `results` array. The credentialed request is saved to `.demo-state/lint-clean-batch-authenticated.json`; keep it private. As with scenario 6, this scenario uses your GitHub CLI token and queues two reports for background Insights publishing.

### 12. Unknown profile

**Request:** An authenticated batch with a valid first spec and a nonexistent profile on the second spec.

```shell
./scenarios/12-unknown-profile-400.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP/2 400
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"UNKNOWN_PROFILE","message":"Unknown profile 'demo-profile-that-does-not-exist'. Available profiles: default, internal-api, payment-api, public-api","details":[{"field":"repository.specifications[1].profile","message":"Unknown profile 'demo-profile-that-does-not-exist'. Available profiles: default, internal-api, payment-api, public-api"}],"requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 400 with `UNKNOWN_PROFILE`. Check the new entries in `.demo-state/fixtures.log` for this run. A JWKS request may appear, but neither spec should be downloaded. No reports are queued.

### 13. Second specification fails to download

**Request:** An authenticated batch with a valid first spec and a missing second spec on the same allowed fixture host.

```shell
./scenarios/13-missing-spec-502.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP/2 502
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"SPEC_FETCH_FAILED","message":"Specification could not be fetched.","upstreamStatus":404,"requestId":"<request-id: UUID>"}
```

**Expected:** The fixture log shows a successful download of the first spec and a 404 for the second. The lint API returns HTTP 502 with `SPEC_FETCH_FAILED` and no partial reports. Check `/status` and confirm that no Insights work is recorded for the rejected request ID. If the queue was empty before the request, it should stay empty and the published count should stay the same.

### 14. Mixed batch lint

**Request:** An authenticated batch with the clean orders fixture first and the original payments fixture second. The script generates a fresh request ID by default. This example supplies one explicitly so it can be matched across the request, response header, and server log.

```shell
DEMO_REQUEST_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')" ./scenarios/14-mixed-batch-lint.sh
```

```terminaloutput
=== Request ===
POST https://localhost:8443/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 200
HTTP/2 200
x-request-id: <request-id: UUID>
cache-control: no-store
content-length: <response-size: non-negative integer, bytes>
content-type: application/json

Mixed batch lint response:
  result: failure
  orders-api-clean: success, 0 finding(s), maturity=platinum
  payments-api: failure, 15 finding(s), maturity=baseline
  full response saved: .demo-state/lint-mixed-response.json
```

**Expected:** HTTP 200 with `orders-api-clean` reporting `success` first, `payments-api` reporting `failure` second, and the batch reporting `failure`. Both reports are queued. The full response and headers are saved in `.demo-state/lint-mixed-response.json` and `.demo-state/lint-mixed-response.headers`.

### 15. Malformed request ID

**Request:** `GET /health` with `X-Request-Id: not-a-uuid` and no authentication.

```shell
./scenarios/15-invalid-request-id-400.sh
```

```terminaloutput
=== Request ===
GET https://localhost:8443/health
X-Request-Id: not-a-uuid

=== Response ===
HTTP/2 400
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_REQUEST","message":"X-Request-Id must be a valid UUID.","details":[{"field":"X-Request-Id","message":"Supply a UUID or omit the header."}],"requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 400 with `INVALID_REQUEST`. The server generates a fresh UUID that matches in the `X-Request-Id` response header and the JSON `requestId` field.

### 16. Smaller 5 MiB YAML specification

**Request:** `POST /skeptic/lint/reports` with valid OpenAPI YAML containing exactly 5,242,880 Unicode code points, below the fixed 26,214,400-code-point limit.

Use the locally built Enterprise Docker image. Start with `./demo.sh start`, optionally setting `SPECMATIC_ENTERPRISE_IMAGE`.

Run the scenario from a second terminal.

```shell
./scenarios/16-large-yaml-limit.sh
```

```terminaloutput
=== Request ===
POST http://127.0.0.1:8000/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

[credentialed request body omitted]

=== Response ===
HTTP 200
At-limit YAML lint response:
  result: <batch-result: string>
  large-openapi-at-limit: <spec-result: string>, <finding-count: non-negative integer, bytes> finding(s), maturity=<maturity: string>
  full response saved: .demo-state/lint-large-spec-response.json
```

**Expected:** HTTP 200 with SARIF report. Linter may report findings. HTTP 500 `INTERNAL_ERROR` means raw syntax tree parser still rejects input at SnakeYAML's 3 MiB default.

### 18. Static 25 MiB YAML at the shared limit

The checked-in `specs/large-openapi-25mb.yaml` is exactly 26,214,400 ASCII bytes/code points (25 MiB). It is a valid OpenAPI 3.0.3 document with an `x-padding` array of short strings. Startup and scenario execution read this file; they do not generate the specification. This experiment checks document size handling, not a large number of API operations.

Stop any running demo first. In terminal 1, run `./demo.sh start`. It uses Docker image `specmatic/enterprise-snapshots:1.29.3`; override with `SPECMATIC_ENTERPRISE_IMAGE`. The fixed limit is 26,214,400 code points. Add `SPECMATIC_LINT_DEBUG=1` for debug logs.

In terminal 2, run `./scenarios/18-25mb-yaml-limit.sh`.

The reports API receives `requests/lint-25mb-spec.json` with a download URL pointing to the static fixture at `http://host.docker.internal:8765/specs/large-openapi-25mb.yaml`. Expect HTTP 200 and one SARIF report. The scenario fails if either is missing; lint findings themselves may be present. The full response is saved in `.demo-state/lint-25mb-spec-response.json`.

Verified against the locally built Docker image: exact-limit input returns HTTP 200 and one SARIF report.

Requires the same GitHub login and license as other batch scenarios. A successful request queues its report for the Insights destination configured in your license. Press Ctrl-C in terminal 1 to stop the experiment.

Server logs remain visible in the first terminal. They include request IDs and HTTP outcomes for the scenarios.

### 19. Reject YAML above the shared limit

Run `./scenarios/19-over-25mb-yaml-422.sh`. Static `specs/large-openapi-over-25mb.yaml` contains 26,214,401 ASCII code points. The script asserts HTTP 422 and `SPEC_TOO_LARGE`; response saved in `.demo-state/lint-over-25mb-spec-response.json`.

## Insights failure and recovery

Run this walkthrough separately on a fresh demo server. It requires a service-account licence pointing to a controllable Insights test endpoint. The lint server publishes to the Insights URL in its licence, and `./demo.sh start` starts JWT and specification fixtures plus the Specmatic source mock.

The polling output below is a partial example of the blocked state, with changing timestamps and retry counts represented by typed placeholders.

1. Configure the Insights endpoint to accept the `orders-api` report and return HTTP 503 for the `payments-api` report, including its retries. Start the demo with the test licence and run `./scenarios/06-batch-lint.sh` once. Expect HTTP 200 with both reports returned to the caller.
2. From the demo directory, poll the status endpoint until `insights.state` is `blocked`:

   ```shell
   source ./scenarios/common.sh
   while true; do run_request -sS "$SERVER_URL/status"; sleep 2; done
   ```

   ```terminaloutput
   === Request ===
   GET https://localhost:8443/status

   === Response ===
   {
     "status": "not_ready",
     "insights": {
       "state": "blocked",
       "lastDeliveredAt": "<last-delivered-at: ISO 8601 date-time, UTC>",
       "publishedReportCount": 1,
       "publishedBatchCount": 0,
       "unpublishedReports": [
         {
           "requestId": "<batch-request-id: UUID>",
           "repoUrl": "https://github.com/example/skeptic-demo-apis",
           "buildId": "skeptic-demo-001",
           "specifications": [
             {
               "specId": "payments-api",
               "state": "blocked",
               "attempts": <attempt-count: positive integer>,
               "lastFailure": {
                 "at": "<last-failure-at: ISO 8601 date-time, UTC>",
                 "reason": "<failure-reason: string>"
               }
             }
           ]
         }
       ]
     }
   }
   ```

   Confirm that `publishedReportCount` is 1 and the batch's request ID has only the `payments-api` report remaining, with state `blocked` and a nonzero attempt count. Run `./scenarios/01-health.sh` and `./scenarios/02-readiness.sh`. Expect HTTP 200 for health and HTTP 503 with `{"status":"not_ready"}` for readiness.
3. Change the test endpoint to accept `payments-api`. Without submitting another lint request, poll status and readiness until recovery. Expect the publish count to reach 2, the batch to disappear from `unpublishedReports`, and readiness to return HTTP 200. The endpoint should see no repeat delivery attempt for the already delivered `orders-api` report.

## Repeat the demo

Restart `./demo.sh start` to reset the server’s in-memory status and config cache, then run the scenarios in order. Generated keys, JWTs, the credentialed request, logs, responses, and cache files remain under the ignored `.demo-state/` directory. Keep the README and `.demo-state/` out of shared archives.

Scenarios 6, 11, and 14 submit two reports each to the Insights destination configured in the service-account licence. Scenarios 16 and 18 submit one report each. Scenario 19 rejects the specification before linting and submits none.

## Validate the README commands

Run the automated walkthrough with one command:

```shell
python3 scripts/validate_readme_commands.py
```

```terminaloutput
Validation complete: <passed-count: non-negative integer, bytes> passed, <skipped-count: non-negative integer, bytes> skipped/manual, 0 failed.
```

The validator reads the `shell` and following `terminaloutput` blocks in this README, executes commands in order, and checks output against the typed templates. It verifies expected exit codes, placeholder formats, request ID consistency, and JSON fields regardless of key order. It exits nonzero on a command failure, timeout, or output mismatch; captured credentials are not printed.

Validation uses a temporary copy of the demo and separate available ports. It starts and stops its own HTTP and HTTPS servers, leaving an existing demo server and its `.demo-state/` directory alone. Docker and the configured Enterprise image must be available, GitHub CLI must already be signed in with access to the private config repository, and a valid licence must be available. Successful batch scenarios publish sample reports to the Insights destination in that licence.

The interactive `gh auth login` step is checked using the existing login. The Insights failure/recovery polling block is reported as **manual** because it requires a controllable Insights test endpoint and matching licence. The validator's own invocation is skipped to avoid recursion; these are the two skipped/manual blocks in the summary.

Options: `--check-only` validates command/output pairing and placeholder types without running commands; `--timeout SECONDS` sets the per-command/startup timeout (default: 180 seconds). The validator retries the read-only status check for up to 60 seconds while background publishing completes.
