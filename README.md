# taco-updates

TACO Smart Procurement update releases and the V6.11 automated release gate.

## Release flow

1. Publish an unsigned GitHub prerelease named `rc-<version>` with one package named `TACO_Update_<version>_win-x64.zip`.
2. Run **TACO V6.11 Automated Release Gate** from **Actions → Run workflow** with matching `version` and `rc_tag` values.
3. The Windows runner executes four gates against the real packaged executables:
   - ZIP, required layout, path traversal, secret material, executable, version and SHA-256 validation.
   - Isolated Schema 3 → 5 migration, pre-migration backup, legacy JSON hash preservation and SQLite integrity/table validation.
   - Successful updater replacement, exit code, history, backup and installed-payload hash validation.
   - Deliberately broken package, non-zero exit, complete failure/rollback history and byte-for-byte restoration.
4. A passing run uploads `RC_VALIDATION_<version>.txt` and `CHECKSUMS_RC_<version>_SHA256.txt` to the RC release. The production workflow refuses older or incomplete evidence.
5. After reviewing the run and evidence, run **TACO Secure Signed Update Promotion**. Its `promote` job must wait for approval on the protected `production` environment before it can access the signing secret or publish `v<version>`.

## Required GitHub settings

Create an environment named `production` under **Settings → Environments** and configure:

- At least one required reviewer; do not allow the workflow initiator to self-approve if your GitHub plan exposes that option.
- Environment secret `TACO_UPDATE_PRIVATE_KEY_B64`, containing the base64-encoded Ed25519 private-key PEM.
- Optional deployment branch/tag restrictions appropriate to the repository release policy.

Do not create the signing secret as a repository or organization secret. The RC gate never references it. The promotion workflow injects it only into the signing step and never writes the decoded private key to disk.

## First V6.11 gate run

Confirm that prerelease `rc-6.11.0` is published and contains `TACO_Update_6.11.0_win-x64.zip`. Then run the automated gate with:

```text
version: 6.11.0
rc_tag: rc-6.11.0
```

All four PASS lines must appear in the Actions summary, and the two evidence files on the RC release must have been replaced by the run. Only then start the production promotion with `version=6.11.0` and `rc_tag=rc-6.11.0`; verify that it pauses for the required reviewer before signing.
