# ACMIS

A multi-tenant Academic Management Information System for universities: one
codebase serving many institutions, each with its own PostgreSQL database.

Thirteen Next.js applications over one Python API, in a Turborepo. 152 tables,
267 API operations, and a policy bundle of 90 policies and 249 rules that
decides every one of them.

---

## What is here

| | |
|---|---|
| `services/api` | The backend. A FastAPI monolith: the domain, the ABAC engine, the audit trail, and both Alembic migration trees. |
| `apps/*` | One Next.js app per module. Each has its own dev server, its own nav, and its own accent colour; they share the design system and the session. |
| `packages/ui` | The design system: 52 components — shadcn/ui primitives plus the app chrome, tables, charts and status vocabulary. |
| `packages/api-client` | A typed client over the API. Hand-written rather than generated, so the method names read like the domain. |
| `packages/auth` | The session: an encrypted HttpOnly cookie, sealed and opened on the server. No app ever holds an API token in the browser. |
| `docs/standards.md` | Every standard implemented and every open-source system studied, with what was taken from each. |

### The modules

| Port | App | What it is for |
|---|---|---|
| 3000 | Shell | Sign in, and move between the modules you have access to |
| 3001 | Admissions | Schemes, applications, selection lists, offers, enrolment |
| 3002 | Student Records | The student record and its life-cycle |
| 3003 | Curriculum | Programmes, versions, courses, offerings, timetable |
| 3004 | Teaching & Learning | Course spaces, notes, question banks, online assessment |
| 3005 | Assessment | Mark sheets, moderation, boards, results, awards |
| 3006 | Finance | Fees, invoices, receipts, sponsorship, late payment |
| 3007 | Faculty & Staff | Staff records, appointments, workload, leave |
| 3008 | Governance & Audit | The audit trail, access review, policies, returns |
| 3009 | Developers | API clients, keys, webhooks, LTI tools, the sandbox |
| 3010 | Student Portal | Your record, registration, fees, results, notes, tests |
| 3011 | Library | Catalogue, circulation, fines, acquisitions, e-resources |
| 3012 | Quality Assurance | Delivery, attendance, evaluations, observations, audits |

---

## Running it

```bash
docker compose -f infra/docker-compose.yml up -d     # Postgres, Redis, MinIO, Mailpit
pnpm install

cd services/api
./scripts/with-venv.sh python -m acmis.cli control-migrate   # control plane
./scripts/with-venv.sh python -m acmis.cli control-seed
./scripts/with-venv.sh python -m acmis.cli demo              # a whole institution
./scripts/with-venv.sh uvicorn acmis.main:app --port 8000

cd ../..
for a in apps/*/; do cp "$a/.env.example" "$a/.env.local"; done
pnpm dev                                                     # every app
```

`demo` is additive and safe to re-run: it never deletes anything, so a
walkthrough survives a re-seed. It builds one institution — Kampala Institute
of Technology — with 8 academic units, 5 programmes, 10 courses, 22 staff, 60
students, 28 applicants, a full library, a semester of class registers, an
evaluation that has closed, mark sheets at every stage of approval, and about
1,200 audit events.

### Signing in

Every seeded account uses the password **`Kampala-Demo-2026!`**.

| Username | Who | Open |
|---|---|---|
| `STF/007` | Academic Registrar | 3000, 3002 |
| `STF/011` | Head of Admissions | 3001 |
| `STF/008` | Deputy Registrar (Records) | 3002 |
| `STF/013` | Secretary to Senate | 3003 |
| `STF/003` | Lecturer, teaches CSC1101 | 3004 |
| `STF/016` | Examinations Officer | 3005 |
| `STF/001` | Head of Department | 3005 |
| `STF/009` | Bursar | 3006 |
| `STF/010` | Accountant | 3006 |
| `STF/018` | HR Officer | 3007 |
| `STF/014` | Internal Auditor | 3008 |
| `STF/015` | System Administrator | 3009 |
| `24/U/0001/BSC` | Student | 3010 |
| `STF/019` | University Librarian | 3011 |
| `STF/020` | Librarian | 3011 |
| `STF/021` | Library Assistant | 3011 — sees the desk only |
| `STF/022` | Quality Assurance Officer | 3012 |

The roles are held by different people on purpose. An examiner cannot approve
their own marks, a bursar cannot release a waiver they raised, and a library
assistant cannot waive a fine. In each case the button is **absent** rather
than disabled, because a disabled button is a promise the system will not
keep. Sign in as two of them and try.

---

## The decisions worth knowing

### A database per tenant

A control-plane database (`acmis_control`) holds the universities; each gets
`acmis_t_<slug>`. Cross-tenant leakage is then a connection-string bug rather
than a missing `WHERE` clause, and one institution's data can be restored,
exported or deleted without touching another's.

The tenant is resolved from the JWT's `tid` claim first, the `Host` header
second, and an `X-ACMIS-Tenant` header only outside production. A token issued
for one institution cannot be redirected at another's data by anything the
caller controls.

### Attribute-based access control, in the codebase

The authorization engine is here rather than in OPA, Cedar or Casbin. The
reasoning, and the alternatives rejected, is in `docs/standards.md`. In short:
the decisions this system makes are about *relationships* — did this examiner
teach this offering, is this the student's own record, did the person
approving also enter the marks — and the policies have to be readable by a
registrar in a meeting, not only by an engineer.

Policies are YAML with XACML's vocabulary (policy set, target, condition,
obligation), deny-overrides combining, field-level masking, and a decision
trace on every answer. Conditions are Python expressions compiled through an
AST allow-list: no attribute access outside the request, no calls outside a
fixed helper table, no comprehensions, no lambdas — rejected at load time, so
a malformed policy fails on boot rather than on the request that touches it.

Two helpers exist because their absence caused real bugs:

- `owns(resource.student_id, subject.student_id)` rather than `==`, because
  `None == None` is true — and an "own record" rule asked of a class-level
  request would otherwise grant the whole class. It did: a member of staff
  could read the library's entire circulation register through the rule meant
  to show readers their own loans.
- `matches()` is a full match, not a search, so a rule naming
  `mark_sheet:read` does not also permit `mark_sheet:read_sensitive`.

### The audit trail cannot be edited

Twelve tables carry `CREATE RULE ... DO INSTEAD NOTHING` on `UPDATE` and
`DELETE`. An attempt to change history is discarded silently by Postgres, and
retention is enforced through a `SECURITY DEFINER` purge function that is the
only way to remove anything. There is also an `acmis_auditor` role with
`SELECT` and nothing else.

Reading matters as much as writing: reading the audit trail is itself audited,
and so is reading a student's medical notes, a payroll record or an
unpublished result.

`evaluation_response` is append-only for a different reason — anonymity. A
response carries no student identifier at all, and with `UPDATE` discarded
nobody can add one later.

### Money is double-entry

`post_transaction` refuses a transaction whose legs do not sum to zero. The
student's balance is a `SUM` over the ledger, cached with a `recomputed_at`
stamp rather than incremented. Every surcharge, waiver and reversal is a pair
of entries, and the demo tenant's ledger sums to exactly zero — the e2e suite
asserts it after applying late-payment surcharges.

### Standards, not exports

LTI 1.3 Advantage (platform side, with Deep Linking, AGS and NRPS), OneRoster
1.2 for rostering and gradebook, QTI 2.1/3.0 import and export, and
SCORM/cmi5/xAPI records. The standards endpoints mount at the application
root rather than under `/api/v1`, because a conforming consumer constructs
`/ims/oneroster/rostering/v1p2/users` and should not have to be told about us.

### Keyset pagination everywhere

Every list endpoint pages on a cursor over `(sort key, id)`, never an offset.
An admissions officer working down a merit list would otherwise skip a
candidate every time another application is scored: the rows shift, and page
two starts after where page one now ends. `keyset_page` generates the filter
from the same expression as the `ORDER BY`, because a keyset predicate that
does not exactly mirror the ordering silently drops rows — which is worse than
offset paging, because it looks correct.

---

## Working on it

```bash
pnpm build          # every app and package
pnpm typecheck
pnpm lint

cd services/api
pnpm lint           # ruff, including the tests
pnpm typecheck      # mypy --strict, 107 files
pnpm test           # 412 tests
```

The Python suite is worth knowing about, because most of it checks things that
are wrong *silently*:

- **`test_descriptors.py`** reads every resource descriptor statically and
  checks each attribute it reaches for against the SQLAlchemy mapper. A
  descriptor reaching through a relationship that does not exist publishes
  `None`, every rule conditioning on it fails to match, and the result reads
  as "denied by default" — which sends people to the policy files for a fault
  in a model. That happened: nobody could mark an essay for a week.
- **`test_policy_bundle.py`** checks that every action the API enforces is
  *named* by some policy. An action no policy mentions is denied for
  everybody, which is a feature nobody can use. Three shipped that way.
- **`test_sql_idioms.py`** forbids `col.in_((value, None))` — nothing is ever
  `IN` a `NULL`, so the institution-wide fallback row can never match — and
  `LIMIT` without `ORDER BY`.
- **`test_architecture.py`** asserts the module import graph stays acyclic and
  that the middleware order the security model assumes is the order installed.

### Adding a module

1. A model module under `acmis/modules/<name>/`, and a line in
   `acmis/modules/registry.py`.
2. Resource descriptors in `acmis/modules/descriptors.py` — the contract
   between the domain and the policies.
3. A policy file in `acmis/policies/`. `pnpm test` will tell you if an action
   is unreachable or an attribute is misspelt.
4. A router, mounted in `acmis/routers/__init__.py`.
5. Methods on `packages/api-client`, and an entry in
   `packages/ui/src/lib/modules.ts` with an accent colour.
6. `pnpm --filter @acmis/app-<name> dev`.
