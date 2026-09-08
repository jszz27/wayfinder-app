# Sprint 4 — CI/CD and deployment

**Goal** (`Plan.md` §7 Step 4, §12): a GitHub Actions workflow, a Cloud
Run deployment, and somewhere for secrets to live that is not a file in
the repository.

**Board columns**: `Backlog` → `To do` → `In progress` → `In review` → `Done`

---

## Where it runs

| Piece | What | Where |
| --- | --- | --- |
| `frontend` | nginx serving the built widget | Cloud Run, us-central1 |
| `backend-rest` | FastAPI, **max 1 instance** | Cloud Run, us-central1 |
| `backend-ws` | FastAPI WebSockets, session affinity, 60-minute timeout | Cloud Run, us-central1 |
| `wayfinder-db` | PostgreSQL 17, `db-f1-micro` | Cloud SQL, us-central1 |
| `wayfinder-migrate` | `alembic upgrade head` | Cloud Run job |
| Images | `backend-rest`, `backend-ws`, `frontend` | Artifact Registry |
| Secrets | database URL, JWT signing key | Secret Manager |

us-central1 throughout, because `chirp_2` language detection already runs
there — `global` does not have it — so keeping the services beside it
saves a round trip at the start of every session.

Running cost is about **$10 a month**, nearly all of it Cloud SQL. Cloud
Run scales to zero, so the three services cost close to nothing when idle.

---

## Decisions

### No service account key exists, because none can

The organisation policy `iam.disableServiceAccountKeyCreation` blocks key
creation outright. That was an obstacle in Sprint 1; here it forced the
answer that was right anyway.

GitHub authenticates by **Workload Identity Federation**: Actions mints an
OIDC token, Google exchanges it for a short-lived credential, and the
provider is bound by an attribute condition to exactly one repository.

```
--attribute-condition="assertion.repository == 'jszz27/wayfinder-app'"
```

No long-lived credential exists in the repository, in GitHub's secret
store, or on anyone's laptop. Nothing to leak and nothing to rotate.

### `--max-instances=1` on the REST API is correctness, not thrift

A guide conversation held while auto-save is off lives in the server's own
memory — that is what makes "reaches no table" true. Under Cloud Run's
autoscaling a second instance would not have it, and pressing Save would
answer "no longer available to save" for no reason the user could see.

Capping the service is the honest fix at this size: no code changes, and
the privacy model keeps its shape. `backend-ws` is uncapped, because its
only state is the database.

This is the ceiling to lift first if the thing ever needs to scale. Lifting
it means moving those conversations to shared storage, which means deciding
whether "not kept" can survive a row existing.

### Migrations are a Cloud Run job, built from the serving image

The same artefact that answers requests also brings the schema up to date,
over the same Cloud SQL socket, as the same service account. No second
credential and no proxy on a runner.

The pipeline migrates **before** deploying. A new column has to exist
before the revision that selects it takes traffic; the other order gives
you a successful deploy and a stream of 500s.

### The deploy is manual on purpose

`workflow_dispatch` only. CI runs on every push and is the gate; deploying
is a decision, taken deliberately. The last step asks all three services
for a 200 and fails the run otherwise, because a green deploy with a dead
service behind it is worse than a red one.

### nginx with `try_files`, or every Sprint 3 route 404s

The widget is a single-page app whose routes became real in Sprint 3.
Served as plain static files, `/saved` would 404 on a reload or a pasted
link — a break that never appears in development, where Vite handles the
fallback. `try_files $uri $uri/ /index.html` is the whole fix, and it is
why the pipeline checks a route rather than only the root.

---

## Issues

### Issue 18 — Continuous integration `infra`
- [x] Both suites and the widget build on every push and pull request
- [x] Three jobs, so a red build says which half broke without opening the log
- [x] `postgres:17`, matching what the project develops against
- [x] `wayfinder_test` created in CI; conftest's refusal to touch another database still applies
- [x] The WebSocket job fails if any test is skipped

### Issue 19 — Images `infra`
- [x] Both backends and the widget build reproducibly from their Dockerfiles
- [x] Non-root, and `PORT` honoured as Cloud Run injects it
- [x] `.dockerignore` and `.gcloudignore` — the second is what the build upload actually reads
- [x] The widget's backend URLs arrive as build arguments, since Vite compiles them in

### Issue 20 — Cloud Run `infra`
- [x] Three services deployed, public, in us-central1
- [x] REST capped at one instance for the reason above
- [x] WebSocket service given session affinity and a 60-minute timeout
- [x] Runtime service account holds only Cloud SQL, Vertex, Speech and the two secrets

### Issue 21 — Data and secrets `infra`
- [x] Cloud SQL PostgreSQL 17, reached over the connector's unix socket
- [x] Schema applied by a Cloud Run job from the serving image
- [x] Signing key and database URL in Secret Manager, injected as environment variables
- [x] Nothing secret in the repository; `.env` remains git-ignored and local

### Issue 22 — Deploy pipeline `infra`
- [x] Workload Identity Federation, no keys, scoped to one repository
- [x] Build, push, migrate, deploy, then verify — in that order
- [x] Manual trigger only
- [x] Proven by deploying `v2` over the running `v1`

---

## Verification evidence

| Check | Evidence |
| --- | --- |
| CI is real | Failed on its first run for a real reason (below), then green: 136 + 96 tests and a clean widget build |
| No test silently skipped | backend-ws reports 96, not 91; the job fails if that changes |
| Clean-room install | Both services installed into fresh virtualenvs from their pyproject files alone, and passed |
| Schema reached Cloud SQL | The migration job logged all three revisions and `Container called exit(0)` |
| The API is live | `signup` 201, `login` returned a token, `GET /api/users/me` came back with the account |
| Gemini works from Cloud Run | A live guide answer, not the mock: "To send money, first tap on the button that says Send at the bottom of your screen." |
| Data persists | That conversation read back from Cloud SQL, and survived a redeploy |
| Signup flow in production | Confirm-password, redirect to sign in, sign in, header — all against the deployed widget |
| SPA routes survive a reload | `GET /saved` on the deployed widget returns 200, not 404 |
| The pipeline works | The `Deploy` run went green through all eleven steps, deploying `v2` over the running `v1` |
| Federation works | The auth step exchanged an OIDC token with no key anywhere in the repository |

### Three things that only failed outside this machine

**An undeclared dependency.** `EmailStr` needs `email-validator`, and
nothing declared it. It worked here because this machine happened to have
it — `pip show` reported nothing requiring it — and failed on the first
clean install anywhere. The Docker build and the Cloud Run deploy would
have failed the same way, later and more expensively. This is the clearest
argument for CI in the whole project: it found the bug on its first run,
before any of the deployment existed.

**A CRLF inside a secret.** The database password was written with
Python's `print`, which on Windows appends `\r\n`, and stored with those
two bytes. The Cloud SQL user was created from `$(cat ...)`, which strips
them. 34 bytes against 32, and `password authentication failed for user
"wayfinder"` with a password that was, character for character, correct.

**A 99.7 MiB build context.** `gcloud builds submit` reads `.gcloudignore`
and not `.dockerignore`, so the first upload carried the whole virtualenv:
6,667 files. With the right file, 28 files and 95 KiB.

### Two things I got wrong and corrected

Both Dockerfiles installed the package *before* copying `app/`. setuptools
then finds nothing, builds an empty wheel, and the failure surfaces much
later at import — it worked at all only because the working directory
happens to be on the path. Fixed to copy source first.

The deploy pipeline used Cloud Build, which kept being refused on its
staging bucket from Actions. Clearing that would have taken four more
permissions on the deployer plus the compute service account acting on its
behalf, to produce an image the runner can build itself in one step. The
runner has Docker; this machine does not, which was the only reason Cloud
Build was there. `frontend/cloudbuild.yaml` remains as the no-local-Docker
path.

---

## Out of scope this sprint

A custom domain and HTTPS certificate — the `run.app` URLs are the
addresses for now · Cloud SQL backups, off to keep the cost to one
instance's worth · Staging as a separate project · Alerting and uptime
checks, which belong with Sprint 5's reliability work · Lifting the
one-instance ceiling on the REST API · Rotating the JWT signing key, which
has no procedure yet · The 106 untested language pairs, still carried.
