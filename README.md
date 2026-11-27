# Specmatic Lint Server demo

This client-ready demo shows how the Specmatic Lint Server validates API specifications, authenticates callers, loads lint rules from a Git configuration repository, and publishes reports to Insights. Local API-spec and JWKS fixtures keep the API and caller identity setup self-contained. You provide your own service-account licence and a Git configuration repository you can read. Each numbered scenario makes exactly one HTTP request to the lint server. Run them individually to inspect the request, response, and server logs.

For the quickest walkthrough, complete Setup, start the server with HTTP, then run scenarios 1–7 in order from a second terminal. Later scenarios demonstrate specific error cases and optional behavior. The output blocks show examples; your server version, timestamps, IDs, license expiry, config commit, and lint results may differ.

## Setup

Requirements: Docker, Python 3, Git, GitHub CLI, curl, OpenSSL, netcat, a Specmatic Enterprise service-account licence, and read access to your GitHub config repository. Generate the licence from your Specmatic service account and save it as `~/.specmatic/specmatic-license.txt`. Create the directory first with `mkdir -p ~/.specmatic` if it does not exist.

The server runs using `specmatic/enterprise:latest`. Start Docker before running the demo. The demo uses bridge networking and publishes the lint server on `127.0.0.1:8000` (HTTP) or `127.0.0.1:8443` (HTTPS); Docker Desktop host networking is not required. The container reaches the JWKS and spec fixtures through `host.docker.internal:8765`. An explicit host-gateway mapping also supports Docker Engine on Linux. The fixture server binds to `0.0.0.0:8765` so containers can reach it; it serves only demo public keys and specification files.

Pull the image before starting:

```shell
docker pull specmatic/enterprise:latest
```

```terminaloutput
latest: Pulling from specmatic/enterprise
```

1. Create or choose a GitHub repository for the lint configuration. The demo expects its default branch to be named `main`.
2. Add this file at the repository root as `specmatic-linter.yaml`, then commit and push it to `main`:

```yaml
profiles:
  default:
    rules:
      extends:
        - recommended
```

3. Sign in to GitHub CLI with an account that can read the repository, then set its HTTPS clone URL:

```shell
gh auth login --hostname github.com
export SPECMATIC_CONFIG_REPO_URL="https://github.com/YOUR-ORG/YOUR-LINTER-CONFIG.git"
```

The batch examples request the `default` profile. Replace `YOUR-ORG/YOUR-LINTER-CONFIG` with your repository path. Keep this terminal open; you’ll set the same URL in the scenario terminal too.

The batch scenarios retrieve your token just before building the request using `gh auth token --hostname github.com`. No token environment variable is needed. Authenticated scenarios print the request body, including this GitHub token. Treat terminal output and screenshots as sensitive, and keep generated request files private.

## Start the server

In this terminal, start HTTP (recommended for the first run):

```shell
./demo.sh start
```

```terminaloutput
Starting the lint server on http://127.0.0.1:8000
Run one scenario at a time from a second terminal. Press Ctrl-C here when done.
{"timestamp":"<timestamp: ISO 8601 date-time, UTC>","level":"INFO","service":"lint-server","component":"server","event":"server.started","port":8000,"scheme":"http"}
```

For an HTTPS run, start `./demo.sh start --https` instead. The scripts trust its generated local certificate. The JWKS and spec fixtures remain local HTTP services.

The server stays running while you run scenarios. Open a second terminal, change to this demo directory, and set the same config URL there (replace the example with your repository URL):

```shell
export SPECMATIC_CONFIG_REPO_URL="https://github.com/YOUR-ORG/YOUR-LINTER-CONFIG.git"
```

Then run the scenarios below one at a time. They detect the selected HTTP or HTTPS URL automatically. Press Ctrl-C in the first terminal to stop the server.

## Optional: license troubleshooting

The standard setup reads `~/.specmatic/specmatic-license.txt`. To use another file, set `SPECMATIC_LICENSE_PATH` before starting:

```shell
SPECMATIC_LICENSE_PATH=/path/to/specmatic-license.txt ./demo.sh start
```

```terminaloutput
Starting the lint server on http://127.0.0.1:8000
```

To check the missing-file error:

```shell
SPECMATIC_LICENSE_PATH=/does-not-exist/specmatic-license.txt ./demo.sh start
```

```terminaloutput
SPECMATIC_LICENSE_PATH does not point to a file.
```

You can pass license text through the environment instead of mounting a file. For example, this intentionally invalid value demonstrates the server's startup error:

```shell
SPECMATIC_LICENSE_CONTENT='this-is-not-a-valid-license' ./demo.sh start
```

**Expected:** The lint server exits during startup with a license-load error stating that the license key could not be parsed.

For a valid license, use `SPECMATIC_LICENSE_CONTENT="$(cat ~/.specmatic/specmatic-license.txt)" ./demo.sh start`. Avoid putting license content into shared shell history or logs.

## Scenarios

### 1. Health

**Request:** `GET /health` (no authentication)

```shell
./scenarios/01-health.sh
```

```terminaloutput
=== Request ===
GET <server-url: selected server URL>/health

=== Response ===
<protocol: HTTP status line>
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
GET <server-url: selected server URL>/readiness

=== Response ===
<protocol: HTTP status line>
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
POST <server-url: selected server URL>/skeptic/lint/reports
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 401
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
POST <server-url: selected server URL>/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 403
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
GET <server-url: selected server URL>/status

=== Response ===
<protocol: HTTP status line>
{
  "status": "ready",
  "linterVersion": "<server-version: string>",
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

**Insights destination:** Successful lint requests publish sample reports to the Insights URL in your license. Use a test license or test Insights workspace for this demo if you do not want sample reports in production.

**Request:** `POST /skeptic/lint/reports` with two specs, a demo-generated RS256 JWT, and a GitHub token that can read your config repository. The scenario retrieves the token with GitHub CLI, builds the request, and saves it under `.demo-state/`.

```shell
./scenarios/06-batch-lint.sh
```

```terminaloutput
=== Request ===
POST <server-url: selected server URL>/skeptic/lint/reports
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
GET <server-url: selected server URL>/status

=== Response ===
HTTP 200
{
  "status": "ready",
  "linterVersion": "<server-version: string>",
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
      "repoUrl": "<your-config-repository-url>",
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

**Request:** The batch POST with a valid demo JWT but a deliberately invalid GitHub token in `config.git.token`. This demonstrates a bad central config credential without changing your GitHub CLI login.

```shell
./scenarios/08-invalid-config-token.sh
```

```terminaloutput
=== Request ===
POST <server-url: selected server URL>/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
{"code":"CONFIG_UNAVAILABLE","message":"Configuration source is temporarily unavailable.","requestId":"<request-id: UUID>"}
HTTP 503
```

**Expected:** HTTP 503 with error code `CONFIG_UNAVAILABLE` and message `Configuration source is temporarily unavailable.` The JWT passes authentication, but the server cannot fetch configuration with the invalid GitHub token. No lint reports are produced. The generated request is saved to `.demo-state/lint-batch-invalid-config-token.json`.


To demonstrate a failed credential replacement with a warm cache, start a fresh server and run these three scenarios in sequence within five minutes. Use the same GitHub CLI login for both valid requests.

```shell
./scenarios/06-batch-lint.sh
./scenarios/08-invalid-config-token.sh
./scenarios/06-batch-lint.sh
```

```terminaloutput
=== Request ===
POST <server-url: selected server URL>/skeptic/lint/reports
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
POST <server-url: selected server URL>/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
{"code":"CONFIG_UNAVAILABLE","message":"Configuration source is temporarily unavailable.","requestId":"<request-id: UUID>"}
HTTP 503

=== Request ===
POST <server-url: selected server URL>/skeptic/lint/reports
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

**Request:** The batch POST with a valid demo JWT and the body from `requests/lint-unapproved-download-host.json`. The first spec uses the allowed hostname `host.docker.internal`; the second uses `localhost`. The server starts with `--allowed-spec-download-host=host.docker.internal`, so `localhost` does not match. Inside the container, `localhost` refers to the container itself.

```shell
./scenarios/09-unapproved-download-host-403.sh
```

```terminaloutput
=== Request ===
POST <server-url: selected server URL>/skeptic/lint/reports
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

**Request:** The batch POST uses `https://github.com/example/unapproved-linter-config.git`, which differs from the repository URL you configured. Both spec download URLs use the allowed hostname `host.docker.internal`.

```shell
./scenarios/10-unapproved-config-repo-403.sh
```

```terminaloutput
=== Request ===
POST <server-url: selected server URL>/skeptic/lint/reports
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

**Request:** The authenticated batch POST using `requests/lint-clean-batch.json`, which downloads the separate `specs/orders-api-clean.yaml` and `specs/payments-api-clean.yaml` specs. The original specs used by scenario 6 retain their intentional lint findings.

```shell
./scenarios/11-clean-batch-lint.sh
```

```terminaloutput
=== Request ===
POST <server-url: selected server URL>/skeptic/lint/reports
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
POST <server-url: selected server URL>/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 400
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"UNKNOWN_PROFILE","message":"Unknown profile 'demo-profile-that-does-not-exist'. Available profiles: default","details":[{"field":"repository.specifications[1].profile","message":"Unknown profile 'demo-profile-that-does-not-exist'. Available profiles: default"}],"requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 400 with `UNKNOWN_PROFILE`. Check the new entries in `.demo-state/fixtures.log` for this run. A JWKS request may appear, but neither spec should be downloaded. No reports are queued.

### 13. Second specification fails to download

**Request:** An authenticated batch with a valid first spec and a missing second spec on the same allowed fixture host.

```shell
./scenarios/13-missing-spec-502.sh
```

```terminaloutput
=== Request ===
POST <server-url: selected server URL>/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 502
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
POST <server-url: selected server URL>/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 200
HTTP 200
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
GET <server-url: selected server URL>/health
X-Request-Id: not-a-uuid

=== Response ===
HTTP 400
x-request-id: <request-id: UUID>
cache-control: no-store
content-type: application/json

{"code":"INVALID_REQUEST","message":"X-Request-Id must be a valid UUID.","details":[{"field":"X-Request-Id","message":"Supply a UUID or omit the header."}],"requestId":"<request-id: UUID>"}
```

**Expected:** HTTP 400 with `INVALID_REQUEST`. The server generates a fresh UUID that matches in the `X-Request-Id` response header and the JSON `requestId` field.

### 16. Large specification (5 MB)

**Request:** An authenticated lint request for the bundled `large-enterprise-api.json` fixture (about 5.2 MB). This demonstrates downloading and linting a larger specification through the same local fixture server.

```shell
./scenarios/16-large-spec-lint.sh
```

```terminaloutput
=== Request ===
POST <server-url: selected server URL>/skeptic/lint/reports
Authorization: Bearer <bearer-token: RS256 JWT, base64url.base64url.base64url>
Content-Type: application/json
X-Request-Id: <request-id: UUID>

<request-body: JSON object from the scenario fixture>

=== Response ===
HTTP 200
Large 5MB spec lint response:
  result: <result: string>
  large-enterprise-api: <result: string>, <finding-count: positive integer> finding(s), maturity=<maturity: string>
  full response saved: .demo-state/lint-large-response.json
```

**Expected:** HTTP 200 with one report for `large-enterprise-api`. The result and finding count depend on the lint configuration in your repository. The full report is saved to `.demo-state/lint-large-response.json`.

Server logs remain visible in the first terminal. They include request IDs and HTTP outcomes for the scenarios.

## JWT authentication scenarios

For focused caller-authentication checks, use the [JWT authentication scenarios](jwt-auth-scenarios/README.md). They cover valid and rejected tokens, claim checks, malformed credentials, and request ID handling. Each numbered script sends one request and prints its response. The automated runner checks the JSON error code and message, request ID correlation, and the Bearer challenge on every HTTP 401. It also sends valid and invalid requests in sequence to check that authentication state does not leak between requests.

With the demo server running, run the full JWT scenario set from a second terminal:

```shell
python3 jwt-auth-scenarios/run_all.py
```

These auth-only checks use the local JWKS fixture and do not need a GitHub token or submit reports to Insights. They reuse the server URL and TLS settings selected at startup.

## Insights failure and recovery

Run this walkthrough separately on a fresh demo server. It requires a service-account licence pointing to a controllable Insights test endpoint. The lint server publishes to the Insights URL in its licence, and `./demo.sh start` starts only the JWT and spec fixtures.

The polling output below is a partial example of the blocked state, with changing timestamps and retry counts represented by typed placeholders.

1. Configure the Insights endpoint to accept the `orders-api` report and return HTTP 503 for the `payments-api` report, including its retries. Start the demo with the test licence and run `./scenarios/06-batch-lint.sh` once. Expect HTTP 200 with both reports returned to the caller.
2. From the demo directory, poll the status endpoint until `insights.state` is `blocked`:

   ```shell
   source ./scenarios/common.sh
   while true; do run_request -sS "$SERVER_URL/status"; sleep 2; done
   ```

   ```terminaloutput
   === Request ===
   GET <server-url: selected server URL>/status

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

Restart `./demo.sh start` to reset the server’s in-memory status and config cache, then run the scenarios in order. Generated keys, JWTs, credentialed requests, logs, responses, and session data are stored under the ignored `.demo-state/` directory. When sharing the demo, include the project files, README, scenarios, requests, and specs. Exclude `.demo-state/`, `.specmatic-linter/`, `.git/`, and `.idea/`; these contain local run data, cached configuration, repository history, or IDE settings that the client does not need.

Each successful batch scenario submits sample reports to the Insights destination configured in your service-account licence. Use a test destination if you do not want demo reports in a production Insights workspace.

## Validate the README commands

Run the automated walkthrough with one command:

```shell
python3 scripts/validate_readme_commands.py
```

The summary shows how many commands passed and how many optional or manual steps were skipped. Counts may change when README examples are added or removed.

The validator reads shell blocks from this README and runs the supported commands in a temporary copy of the demo. It checks that the server starts, scenarios exit successfully, status endpoints return valid JSON, and the JWT runner sees the expected auth responses, request ID correlation, and challenge headers. It exits nonzero if a command fails or times out. Successful lint scenarios publish sample reports to the Insights destination in your license, so use a test destination when running it. JWT-only scenarios stop before config loading and report submission.

Validation uses a temporary copy of the demo and separate available ports. It starts and stops its own HTTP server, leaving an existing demo server and its `.demo-state/` directory alone. Docker must be running, GitHub CLI must already be signed in with access to the configured repository, and a valid licence must be available.

Interactive GitHub login, optional license troubleshooting, the alternative HTTPS startup, Insights recovery, and the validator's own invocation are skipped. Insights recovery needs a controllable Insights test endpoint and matching licence.

Options: `--check-only` counts the README shell examples without running the demo; `--no-pull` uses the cached Docker image; `--timeout SECONDS` sets the per-command/startup timeout (default: 60 seconds).
