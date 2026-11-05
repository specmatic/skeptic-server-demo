# Specmatic Lint Server demo

This demo uses local API-spec and JWKS fixtures plus the private central configuration repository. Each numbered scenario makes exactly one HTTP request to the lint server. Run them individually to inspect each request, response, and the corresponding server logs. Each scenario prints the request method, URL, headers, and body (when present) before the response. Authorization headers include the actual demo bearer token so its claims can be inspected.

## Setup

Requirements: Java 17+, Python 3, Git, OpenSSL, netcat, and a Specmatic Enterprise service-account licence.

Build the Enterprise executable from the Enterprise repository root:

```shell
./gradlew :executable:shadowObfuscatedJar
```

If the licence is not available at `~/.specmatic/specmatic-license.txt`, set `SPECMATIC_LICENSE_PATH` to its file before starting the server.

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

```text
SPECMATIC_LICENSE_PATH does not point to a file.
```

This override applies only to this command. For normal startup below, use a valid licence at the default location or set `SPECMATIC_LICENSE_PATH` to its file.

## Demonstrate invalid licence content

You can also supply the licence directly through `SPECMATIC_LICENSE_CONTENT`. To demonstrate the server rejecting invalid content, run:

```shell
SPECMATIC_LICENSE_CONTENT='this-is-not-a-valid-license' ./demo.sh start
```

**Expected:** The server rejects the licence during startup and exits with code 1. The logs include the following error, followed by a stack trace:

```text
Checking for Specmatic Enterprise service-account license...
io.specmatic.license.core.LicenseLoadException: Unable to parse license key. Please ensure it is a valid Specmatic license key.
```

This override applies only to this command. For normal startup below, supply a valid service-account licence.

## Start the server

From this demo directory, run the server in one terminal and leave it open. Startup and request logs appear here.

```shell
./demo.sh start
```

### Start with valid licence content

To demonstrate successful startup using `SPECMATIC_LICENSE_CONTENT`, load the valid service-account licence from your local file:

```shell
SPECMATIC_LICENSE_CONTENT="$(cat ~/.specmatic/specmatic-license.txt)" ./demo.sh start
```

**Expected:** The server accepts the licence and stays running on `http://localhost:8000`. The licence content is read from the file without printing it to the terminal. This override applies only to this command.

Use either startup command above, then continue with the scenarios.

In a second terminal, change to this demo directory and run the scenarios below, one at a time. Press Ctrl-C in the first terminal to stop the server.

## Scenarios

### 1. Health

**Request:** `GET /health` (no authentication)

```shell
./scenarios/01-health.sh
```

**Expected:** HTTP 200 with `{"status":"up"}`. This confirms the HTTP server is responding.

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

Server logs remain visible in the first terminal. They include request IDs and HTTP outcomes for the scenarios.

## Repeat the demo

Restart `./demo.sh start` to reset the server’s in-memory status and config cache, then run the scenarios in order. Generated keys, JWTs, the credentialed request, logs, responses, and cache files remain under the ignored `.demo-state/` directory. Keep the README and `.demo-state/` out of shared archives.

Each run of the batch scenario submits two sample reports to the Insights destination configured in the service-account licence.
