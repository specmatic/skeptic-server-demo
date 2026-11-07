# Specmatic Lint Server demo

This demo uses local API-spec and JWKS fixtures plus the private central configuration repository. Each numbered scenario makes exactly one HTTP request to the lint server. Run them individually to inspect each request, response, and the corresponding server logs. Each scenario prints the request method, URL, headers, and body (when present) before the response. Authorization headers include the actual demo bearer token so its claims can be inspected.

## Setup

Requirements: Docker, Python 3, Git, GitHub CLI, curl, OpenSSL, netcat, and a Specmatic Enterprise service-account licence.

The server runs using `specmatic/enterprise:latest`. Start Docker before running the demo. The demo uses bridge networking and publishes the lint server on `127.0.0.1:8000` (HTTP) or `127.0.0.1:8443` (HTTPS); Docker Desktop host networking is not required. The container reaches the JWKS and spec fixtures through `host.docker.internal:8765`. An explicit host-gateway mapping also supports Docker Engine on Linux. The fixture server binds to `0.0.0.0:8765` so containers can reach it; it serves only demo public keys and specification files.

Pull the image before starting:

```shell
docker pull specmatic/enterprise:latest
```

To use a specific image tag, set `SPECMATIC_ENTERPRISE_IMAGE=specmatic/enterprise:<tag>` when running `./demo.sh start`.

The startup script mounts `~/.specmatic/specmatic-license.txt` read-only into the container. If the licence is elsewhere, set `SPECMATIC_LICENSE_PATH` to its file before starting the server. `SPECMATIC_LICENSE_CONTENT` is passed through when supplied and takes precedence over the file. Each session directory is mounted into the container for cache and TLS files. Pressing Ctrl-C stops the container and fixture server.

Sign in to GitHub CLI using an account with read access to `specmatic/private-central-linter-config`:

```sh
gh auth login --hostname github.com
```

The batch scenario retrieves your token just before building the request using `gh auth token --hostname github.com`. No token environment variable is needed. The generated request contains the token in its config repository URL and is printed by the scenario; do not share that output or the generated request file.

## Demonstrate a missing licence

Before starting the server, point to a licence file that does not exist:

```shell
SPECMATIC_LICENSE_PATH=/does-not-exist/specmatic-license.txt ./demo.sh start
```

**Expected:** The startup script exits with code 1 before starting the server and prints:

```terminaloutput
SPECMATIC_LICENSE_PATH does not point to a file.
```

This override applies only to this command. For normal startup below, use a valid licence at the default location or set `SPECMATIC_LICENSE_PATH` to its file.

## Demonstrate invalid licence content

You can also supply the licence directly through `SPECMATIC_LICENSE_CONTENT`. To demonstrate the server rejecting invalid content, run:

```shell
SPECMATIC_LICENSE_CONTENT='this-is-not-a-valid-license' ./demo.sh start
```

**Expected:** The server rejects the licence during startup and exits with code 1. The logs include the following error:

```terminaloutput
"level":"INFO","service":"lint-server","component":"server","event":"server.start_failed","outcome":"failure","exceptionType":"io.specmatic.license.core.LicenseLoadException","errorMessage":"Unable to parse license key. Please ensure it is a valid Specmatic license key."}
```

## Start the server

Start with HTTP:

```shell
./demo.sh start
```

Or start with HTTPS:

```shell
./demo.sh start --https
```

HTTPS mode creates a local certificate and PKCS#12 keystore under `.demo-state/`, then starts the lint server at `https://localhost:8443`. The scenario scripts trust this certificate automatically, so they verify TLS without disabling certificate checks. The JWKS and specification fixtures remain local HTTP services; HTTPS covers the client connection to the lint server.

### Start with valid licence content

To demonstrate successful startup using `SPECMATIC_LICENSE_CONTENT`, load the valid service-account licence from your local file:

Start with HTTP:

```shell
SPECMATIC_LICENSE_CONTENT="$(cat ~/.specmatic/specmatic-license.txt)" ./demo.sh start
```

Or start with HTTPS:

```shell
SPECMATIC_LICENSE_CONTENT="$(cat ~/.specmatic/specmatic-license.txt)" ./demo.sh start --https
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

**Expected:** HTTP 200 with `{"status":"up"}`. This confirms the server is responding over the selected protocol.

### 2. Readiness

**Request:** `GET /readiness` (no authentication)

```shell
./scenarios/02-readiness.sh
```

**Expected:** HTTP 200 with `{"status":"ready"}`. This reports whether the server can currently accept lint work.

### 3. Missing JWT

**Request:** `POST /skeptic/lint/reports` with the batch body from `requests/lint-batch.json` and no Authorization header.

```shell
./scenarios/03-no-token-401.sh
```

**Expected:** HTTP 401. The server rejects the request before loading configuration or fetching specs.

### 4. JWT scope mismatch

**Request:** The same batch POST, with a demo-generated RS256 JWT. Its signature, issuer, and audience are valid. The token's `scope` is `lint:run`; the configured exact value is `lint:run reports:read`.

```shell
./scenarios/04-wrong-scope-403.sh
```

**Expected:** HTTP 403 because the token does not satisfy the exact claim match.

### 5. Status before linting

**Request:** `GET /status` (no authentication). Run this before the batch request.

```shell
./scenarios/05-status-before-lint.sh
```

**Expected:** HTTP 200. On a fresh server run, Insights is healthy with no published reports, and the config list is empty.

### 6. Batch lint

**Request:** `POST /skeptic/lint/reports` with two specs, a self-contained credentialed config Git URL, and a demo-generated RS256 JWT containing the required scope. The scenario retrieves the GitHub token just in time with `gh auth token --hostname github.com`, builds the request from `requests/lint-batch.json`, then saves it under `.demo-state/`.

```shell
./scenarios/06-batch-lint.sh
```

**Expected:** HTTP 200 with one report per spec. The lint `result` is `failure` because the small sample specs intentionally produce findings. The full response is saved to `.demo-state/lint-response.json`. The server queues each report for background Insights publishing and returns without waiting for that work.

### 7. Status after linting

**Request:** `GET /status` (no authentication). The script waits five seconds after the batch before making this request.

```shell
./scenarios/07-status-after-lint.sh
```

**Expected:** HTTP 200. The config snapshot shows the loaded branch and commit. After both pushes succeed, `publishedReportCount` should be 2 and the queue should be empty. The counter reflects successful Insights responses; any report still queued has not succeeded yet.

### 8. Invalid config repository token

**Request:** The batch POST with a valid demo JWT but a deliberately invalid GitHub token in the config repository URL. This demonstrates a bad central config credential without setting `CENTRAL_CONFIG_REPO_TOKEN` or changing your GitHub CLI login.

```shell
./scenarios/08-invalid-config-token.sh
```

**Expected:** HTTP 503 with error code `CONFIG_UNAVAILABLE` and message `Configuration source is temporarily unavailable.` The JWT passes authentication, but the server cannot fetch the private configuration with the invalid GitHub token. No lint reports are produced. The generated request is saved to `.demo-state/lint-batch-invalid-config-token.json`.


To demonstrate a failed credential replacement with a warm cache, start a fresh server and run these three scenarios in sequence within five minutes. Use the same GitHub CLI login for both valid requests.

```shell
./scenarios/06-batch-lint.sh
./scenarios/08-invalid-config-token.sh
./scenarios/06-batch-lint.sh
```

**Expected:** HTTP 200, then HTTP 503 with `CONFIG_UNAVAILABLE`, then HTTP 200. The middle request fails despite the cached snapshot. The final request succeeds with the original credentials. The two successful requests each queue two reports.

### 9. Download hostname outside the allowlist

**Request:** The batch POST with a valid demo JWT and the body from `requests/lint-unapproved-download-host.json`. The first spec uses the allowed hostname `host.docker.internal`; the second uses `localhost`. The server starts with `--allowed-spec-download-host=host.docker.internal`, so `localhost` does not match. Inside the container, `localhost` refers to the container itself.

```shell
./scenarios/09-unapproved-download-host-403.sh
```

**Expected:** HTTP 403 with error code `SPEC_URL_NOT_ALLOWED`, message `The downloadUrl host is not allowed.`, and field `repository.specifications[1].downloadUrl`. The server rejects the entire batch before loading configuration or downloading either spec. No lint reports are produced or queued for Insights. This scenario does not need a GitHub token because download URLs are checked before fetching configuration.

### 10. Configuration repository outside the allowlist

**Request:** The batch POST with a valid demo JWT and the body from `requests/lint-unapproved-config-repo.json`. The config URL is `https://github.com/example/unapproved-linter-config.git`; the server only allows `https://github.com/specmatic/private-central-linter-config.git`. Both spec download URLs use the allowed hostname `host.docker.internal`.

```shell
./scenarios/10-unapproved-config-repo-403.sh
```

**Expected:** HTTP 403 with error code `CONFIG_URL_NOT_ALLOWED` and message `Configuration repository URL is not allowed.` The server rejects the entire batch before fetching configuration or downloading specs. No lint reports are produced or queued for Insights. This scenario does not need a GitHub token because the config URL is checked before fetching the repository. The allowlist checks the repository URL, so using the same `github.com` hostname does not grant access to another repository.

### 11. Clean batch lint

**Request:** The authenticated batch POST using `requests/lint-clean-batch.json`, which downloads the separate `specs/orders-api-clean.yaml` and `specs/payments-api-clean.yaml` specs. The original specs used by scenario 6 retain their intentional lint findings. Restart `./demo.sh start` after updating the demo so the fixture server serves the new files.

```shell
./scenarios/11-clean-batch-lint.sh
```

**Expected:** HTTP 200 with batch and per-spec `result` set to `success`, and zero SARIF findings under the configured `default` profile. The summary prints `0 finding(s)` for each spec. Inspect `.demo-state/lint-clean-response.json` for the full clean reports, including each SARIF run's empty `results` array. The credentialed request is saved to `.demo-state/lint-clean-batch-authenticated.json`; keep it private. As with scenario 6, this scenario uses your GitHub CLI token and queues two reports for background Insights publishing.

### 12. Unknown profile

**Request:** An authenticated batch with a valid first spec and a nonexistent profile on the second spec.

```shell
./scenarios/12-unknown-profile-400.sh
```

**Expected:** HTTP 400 with `UNKNOWN_PROFILE`. Check the new entries in `.demo-state/fixtures.log` for this run. A JWKS request may appear, but neither spec should be downloaded. No reports are queued.

### 13. Second specification fails to download

**Request:** An authenticated batch with a valid first spec and a missing second spec on the same allowed fixture host.

```shell
./scenarios/13-missing-spec-502.sh
```

**Expected:** The fixture log shows a successful download of the first spec and a 404 for the second. The lint API returns HTTP 502 with `SPEC_FETCH_FAILED` and no partial reports. Check `/status` and confirm that no Insights work is recorded for the rejected request ID. If the queue was empty before the request, it should stay empty and the published count should stay the same.

### 14. Mixed batch lint

**Request:** An authenticated batch with the clean orders fixture first and the original payments fixture second. The script generates a fresh request ID by default. This example supplies one explicitly so it can be matched across the request, response header, and server log.

```shell
DEMO_REQUEST_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')" ./scenarios/14-mixed-batch-lint.sh
```

**Expected:** HTTP 200 with `orders-api-clean` reporting `success` first, `payments-api` reporting `failure` second, and the batch reporting `failure`. Both reports are queued. The full response and headers are saved in `.demo-state/lint-mixed-response.json` and `.demo-state/lint-mixed-response.headers`.

### 15. Malformed request ID

**Request:** `GET /health` with `X-Request-Id: not-a-uuid` and no authentication.

```shell
./scenarios/15-invalid-request-id-400.sh
```

**Expected:** HTTP 400 with `INVALID_REQUEST`. The server generates a fresh UUID that matches in the `X-Request-Id` response header and the JSON `requestId` field.

Server logs remain visible in the first terminal. They include request IDs and HTTP outcomes for the scenarios.

## Insights failure and recovery

Run this walkthrough separately on a fresh demo server. It requires a service-account licence pointing to a controllable Insights test endpoint. The lint server publishes to the Insights URL in its licence, and `./demo.sh start` starts only the JWT and spec fixtures.

1. Configure the Insights endpoint to accept the `orders-api` report and return HTTP 503 for the `payments-api` report, including its retries. Start the demo with the test licence and run `./scenarios/06-batch-lint.sh` once. Expect HTTP 200 with both reports returned to the caller.
2. From the demo directory, poll the status endpoint until `insights.state` is `blocked`:

   ```shell
   source ./scenarios/common.sh
   while true; do run_request -sS "$SERVER_URL/status"; sleep 2; done
   ```

   Confirm that `publishedReportCount` is 1 and the batch's request ID has only the `payments-api` report remaining, with state `blocked` and a nonzero attempt count. Run `./scenarios/01-health.sh` and `./scenarios/02-readiness.sh`. Expect HTTP 200 for health and HTTP 503 with `{"status":"not_ready"}` for readiness.
3. Change the test endpoint to accept `payments-api`. Without submitting another lint request, poll status and readiness until recovery. Expect the publish count to reach 2, the batch to disappear from `unpublishedReports`, and readiness to return HTTP 200. The endpoint should see no repeat delivery attempt for the already delivered `orders-api` report.

## Repeat the demo

Restart `./demo.sh start` to reset the server’s in-memory status and config cache, then run the scenarios in order. Generated keys, JWTs, the credentialed request, logs, responses, and cache files remain under the ignored `.demo-state/` directory. Keep the README and `.demo-state/` out of shared archives.

Each run of a successful batch scenario (6, 11, or 14) submits two sample reports to the Insights destination configured in the service-account licence.
