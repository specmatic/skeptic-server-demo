# Config repository cache validation

Use this focused walkthrough to check credential-free config URLs, private-repo tokens, background refresh, and token rotation.

## Before you start

- Run from the `skeptic-server-demo` root. Docker, the demo image, and a test license with a test Insights destination are needed for live lint requests.
- For client validation, use an approved GitHub App installation-token broker and a disposable private rules branch. Do not use `gh auth token` as evidence of App-token behavior.
- The Git URL must have no username, password, or token. Private repositories use `config.git.token`, sent by the demo request as `Authorization`; public repositories can omit the token.
- The runner does not print or save the lint request body. Its saved response is sanitized. Never paste a real token into a command transcript or logs.

## Start the demo server

In terminal 1, set the credential-free repository URL. The runner uses it as the server's exact config-repository allowlist by default:

```bash
export DEMO_CONFIG_REPO_URL='https://github.com/ORG/REPO.git'
./config-repo-cache-scenarios/run.sh start
```

If the allowlist must differ, set `DEMO_ALLOWED_CONFIG_REPO_URL` explicitly before `start`.

## Prepare the rules commits

Use the `default` profile. Commit C0 with `operation-summary` disabled:

```yaml
profiles:
  default:
    rules:
      extends:
        - recommended
      override:
        operation-summary:
          severity: off
```

The same fixture with severity `error` and message `CLIENT_VALIDATION_C1` is C1:

```yaml
profiles:
  default:
    rules:
      extends:
        - recommended
      override:
        operation-summary:
          severity: error
          message: CLIENT_VALIDATION_C1
```

The demo lints [`specs/config-refresh-marker.yaml`](../specs/config-refresh-marker.yaml), which has an operation without a summary. With C0, its SARIF has no `operation-summary` result. After C1 refreshes, the result contains `CLIENT_VALIDATION_C1`.

## Load C0 and observe the background refresh

In terminal 2, set the same clean URL and branch. For a private repo, obtain a short-lived App token from the approved broker and pass it only as `DEMO_CONFIG_TOKEN`. For a public repo, set `DEMO_NO_CONFIG_TOKEN=1` instead.

```bash
export DEMO_CONFIG_REPO_URL='https://github.com/ORG/REPO.git'
export DEMO_CONFIG_BRANCH='config-refresh-validation'
DEMO_CONFIG_TOKEN="$(your-approved-app-token-broker)" ./config-repo-cache-scenarios/run.sh lint
```

The scenario uses [`requests/lint-config-refresh.json`](../requests/lint-config-refresh.json), with the token supplied separately as `config.git.token`. It prints a redacted Authorization line and omits the request body. Do not issue another lint while observing the refresh.

From your local rules checkout, push C1 and wait for the matching fresh SHA. The wait command polls `GET /status` only, up to 360 seconds:

```bash
CONFIG_REPO_CHECKOUT='/path/to/rules-checkout'
git -C "$CONFIG_REPO_CHECKOUT" push origin "$DEMO_CONFIG_BRANCH"
C1_SHA="$(git -C "$CONFIG_REPO_CHECKOUT" rev-parse HEAD)"
./config-repo-cache-scenarios/run.sh wait "$C1_SHA"
```

Expected:

```text
PASS: config refreshed to <commit-sha: 40 hexadecimal characters> (stale=false).
```

After the wait succeeds, lint once more and verify both the refreshed SHA and the C1 SARIF marker:

```bash
DEMO_CONFIG_TOKEN="$(your-approved-app-token-broker)" ./config-repo-cache-scenarios/run.sh lint
./config-repo-cache-scenarios/run.sh verify "$C1_SHA"
```

For a public repository, use `DEMO_NO_CONFIG_TOKEN=1` in place of `DEMO_CONFIG_TOKEN=...` on each lint command.

## Check token rotation

1. With token A still valid, submit a lint using token B. This request must authenticate successfully and become the remembered credential for that config entry.
2. Revoke token A at the broker.
3. Push another valid rules commit.
4. Use `run.sh wait <new-sha>` and make no lint requests while it waits.
5. Confirm `/status` reports the new SHA and `stale: false`. Record timestamps, request IDs, HTTP results, and sanitized server logs; never record token values.

Use independently revocable tokens from the approved broker. A local fixture can check token replacement logic, but cannot prove App issuance or revocation.

## Controlled local checks

These use dummy tokens and local Git HTTP, not GitHub or Insights. They need the neighboring Enterprise checkout, its contract-test license and mocks, Docker, and the cached Enterprise image. The full command waits through the five-minute background refresh.

```bash
./config-repo-cache-scenarios/run.sh local-smoke
./config-repo-cache-scenarios/run.sh local-full
```

The dummy token's `.netrc` is isolated under ignored `.demo-state/` to check ambient-auth suppression. Never place a real token there. These checks cover the local HTTP/auth/cache path; client validation still needs the approved App token broker and test Insights destination.

## Runner commands

- `start [--https]`: start server with the URL as exact allowlist default.
- `lint`: submit the marker-spec request; requires `DEMO_CONFIG_TOKEN` or `DEMO_NO_CONFIG_TOKEN=1`.
- `status`: run the existing read-only status scenario.
- `wait <full-sha>`: poll status until that config SHA is fresh, up to six minutes.
- `verify <full-sha>`: verify the sanitized saved lint response.
- `local-smoke` / `local-full`: run controlled fixture checks.

Generated data stays under ignored `.demo-state/`. Keep that directory out of shared archives.
