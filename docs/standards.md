# What this was based on, and what that cost

ACMIS did not invent a question engine, a rostering format or an authorization
model. Where a proven system or a published standard already answers a
question, ACMIS follows it. This file records each borrowing, what was taken,
what was deliberately *not* taken, and — where it matters — the licence
position.

## Licence position, stated first

**No GPL code is copied into this repository.** Two of the systems that
informed the design most — Moodle and ERPNext — are GPLv3. Copying their code
here would place the whole of ACMIS under GPLv3, which for a multi-tenant
platform that universities deploy and extend is a decision nobody should make
by accident in a commit.

So the relationship with those two is **design study only**: their public
documentation and their data model were read, the reasoning was understood,
and the equivalent was written here from scratch. That is not a licence
loophole — a design idea is not a copyrighted work, and "grades are stored as
a fraction of the question" is a design idea. What is avoided is the thing that
would actually be infringement: lifting their source.

Where a permissively-licensed implementation exists, it was used or consulted
directly, and that is noted below.

---

## Assessment and the question engine — Moodle (GPLv3, design study)

Moodle's question engine has had two decades and tens of millions of sittings
to find the edges. Three ideas were taken:

**1. The question/behaviour split.** Moodle separates *what a question is*
(question type) from *how a candidate interacts with it* (question behaviour).
Most home-grown quiz tools miss this, and missing it means a formative practice
quiz and a final examination need separate code paths for the same question
types. ACMIS has `QuestionKind` and `Behaviour` for exactly this reason — see
`acmis/modules/learning/models.py`.

**2. Grades stored as a fraction.** Moodle stores a candidate's result as a
fraction from 0 to 1 and multiplies by the question's `maxmark`. ACMIS stores
`AttemptResponse.fraction` alongside `marks_awarded` for the same reason its
documentation gives: a judgement about an answer should not be entangled with
how many marks the question happens to be worth in this paper. Re-weight a
question and every candidate's mark follows correctly, with nothing remarked.

**3. The calculated question type.** A stem with `{a}`/`{b}` placeholders, a
formula answer, and a dataset of variable sets instantiated per candidate. It
solves the problem no amount of shuffling can — every candidate gets the same
question with different numbers, so an answer passed between them is wrong.

**Not taken:** Moodle's full response-processing language, its adaptive items,
and its plugin architecture. All three are more expressive than what ACMIS
needs, and the expressiveness has a cost: a question whose marking rules are a
small program is a question nobody can review before an examination. A QTI
item using adaptive processing is therefore *declined on import with a stated
reason* rather than approximated — `acmis/modules/interop/qti.py`.

**Also taken, from Moodle's item analysis:** the facility and discrimination
indices, on the upper/lower-27% split. A question with high facility and
near-zero discrimination is measuring nothing; one with *negative*
discrimination almost always has an incorrect answer key. That is a finding a
lecturer can act on and it is invisible without the arithmetic.

## Interoperability — 1EdTech standards (specifications, freely implementable)

An institution adopting ACMIS already owns content and already runs other
systems. Supporting the standards they speak is the difference between
"migrate everything" and "plug in what you have".

### LTI 1.3 Advantage — `acmis/modules/interop/lti.py`

ACMIS implements the **platform** side: it issues launches into external tools
and receives grades back. Every claim URI, scope and message type is a literal
constant from the specification rather than an inline string, so a typo is a
`NameError` at import rather than a launch a tool silently rejects.

Implemented: OIDC third-party-initiated login, `id_token` minting with the
core claims, JWKS and OpenID discovery endpoints, Deep Linking, Assignment and
Grade Services (line items, scores, results), Names and Role Provisioning.

Every LTI library on PyPI — `PyLTI1p3` (MIT) included — implements the *tool*
side. There is no permissively-licensed Python platform implementation, which
is why this is written against the specification.

Three things done deliberately rather than conventionally:

- **`sub` is a per-tool pseudonym, not our user id.** `sub` is disclosed to the
  tool and becomes its permanent key for that person. Sending our internal
  UUID would hand every registered vendor a join key across the whole
  institution, and let two vendors correlate their records about the same
  student.
- **Services are granted individually.** A content tool needs Deep Linking and
  nothing else. Granting grade-write access because it was easier is how a
  courseware vendor ends up able to change marks.
- **A tool's grades land on a draft mark sheet as a component score.** Never a
  final mark, never past the approval chain. A tool reporting a grade does not
  bypass moderation, a department board, a faculty board and Senate because it
  arrived over HTTP.

### OneRoster 1.2 — `acmis/modules/interop/oneroster.py`

Rostering and gradebook, read-only. Field names and shapes were cross-checked
against the **Ed-Fi Alliance's `edfi-oneroster` (Apache-2.0)** implementation —
a permissive licence, consulted directly for the exact `sourcedId`,
`dateLastModified`, GUIDRef `{href, sourcedId, type}` and `{"users": [...]}`
envelope shapes. A near-miss on any of those is an integration that half-works
and is miserable to debug from the consumer's side.

**Not implemented: the write bindings.** OneRoster `PUT`/`DELETE` would let an
external system change enrolments and marks, and the modules in this system
spend their whole time ensuring that happens through an approval chain.
Anything that needs to write does so through the ACMIS API, where the policy
bundle applies.

**Note on paging:** OneRoster specifies offset paging. The ACMIS API uses
keyset cursors, which are better. The standard wins at the boundary — a
conforming client implements offset — and the trade does not leak inward.

### QTI 2.1 and 3.0 — `acmis/modules/interop/qti.py`

Import and export of question banks. Both versions are read: 2.1 because that
is what most systems still export whatever the current version is, 3.0 because
it is what new tools produce.

Round-tripping is the point. An institution should be able to leave; a question
bank readable only through our own API is a question bank held hostage.

### SCORM, cmi5 and xAPI

`ContentPackage` records imports; `XapiStatement` stores statements in the
tenant's own database rather than forwarding to an external Learning Record
Store by default. These statements are behavioural data about identified
students, and the institution should decide where that goes — forwarding is
configuration, not the default.

## Finance — double-entry bookkeeping (ERPNext GPLv3, design study)

The pattern is centuries older than any software, but ERPNext's student-fee
handling was read for how an education-sector ledger hangs together.

What was taken is the discipline, not the code: every movement is a balanced
set of `LedgerEntry` legs, `post_transaction` refuses a set that does not sum
to zero, and a student's balance is a `SUM` over entries with
`StudentAccount.balance_minor` as an explicitly-labelled cache. On
disagreement the entries win and the cache is rebuilt.

The alternative — a `balance` column that fifteen code paths increment — is
what produces the single most common failure in university finance systems: a
balance nobody can explain, because two of those paths ran twice.

## Authorization — XACML vocabulary, OPA/Cedar rejected with reasons

`acmis/core/abac/` uses XACML's vocabulary — policy set, policy, rule, target,
condition, obligation — because that vocabulary already has answers for the
questions that arrive on day two: what happens when two rules disagree, how do
you scope a rule cheaply before evaluating it, how does a decision carry
instructions back to the caller. The wire format is YAML rather than XACML's
XML, and the combining algorithm is fixed rather than pluggable.

**OPA/Rego and Cedar were both considered and rejected**, and the reason is in
`acmis/core/abac/expressions.py`: an authorization decision happens several
times per request and sits in front of every query, and both engines put
either a network hop or a foreign runtime between the request and its answer.
Cedar has no first-party Python binding; OPA means running and versioning a
sidecar per deployment and shipping the whole attribute set over the wire to
ask about one record.

The condition language here is far less expressive, deliberately: no loops, no
assignment, no imports, and AST-validated at load so a malformed policy fails
when the bundle loads rather than on the first request that touches it. If a
rule cannot be said in these terms it belongs in the module's own rule engine,
where it can be tested.

**Casbin** (Apache-2.0, and a real Python library) was the closest call. It was
passed over because its model files express *what* is allowed but have nowhere
to put field-level masking, obligations, or the decision trace that the audit
trail persists — and those three are the parts of this system that a
degree-award appeal actually needs.

## Academic regulations — NCHE guidance (Uganda)

The default progression and classification rules in
`acmis/modules/assessment/rules.py` encode the National Council for Higher
Education's framing for Ugandan undergraduate programmes: a 5.0-point scale,
normal progress at a grade point of 2.0 and above, probationary progress below
it, retakes carried forward.

They are **defaults, not truths**. Every value lives in
`CurriculumVersion.progression_rules` and `classification_rules` as data, and
is stamped onto each computed result. An institution on a 4.0 scale changes
four numbers; a 2024 graduate stays classified under the 2024 rules, which is
the whole reason the rules are data rather than code.

## What was looked at and not used

- **Kuali Student, OpenSIS, Fedena, Gibbon** — school-oriented or dormant.
  Their data models assume a K-12 shape (homerooms, grade levels) that fights
  a university's faculty/department/programme/curriculum-version structure.
- **Open edX** — an excellent MOOC platform and the wrong shape for a
  registry. Its course model has no notion of a curriculum version a cohort is
  attached to, which is the single most load-bearing idea in ACMIS.
- **Keycloak** — a strong identity provider, and ACMIS federates *to* one via
  `UserAccount.external_idp`. It is not an authorization engine for this
  domain: "the registrar of this faculty, for a student in that programme,
  during the registration window" is not expressible in realm roles.
- **OpenFGA / Zanzibar** (Apache-2.0) — genuinely good at relationship
  questions, and a plausible future for the unit-scoping half of the policy
  bundle. Rejected for now for the same reason as OPA: a network hop on the
  authorization hot path, plus a second source of truth for who can do what.

## Reference material in this repository

`reference/` (git-ignored) holds shallow clones consulted while building —
currently the Apache-2.0 `edfi-oneroster`. Nothing in it is compiled, imported
or distributed. It is there so the field shapes could be checked against a
working implementation rather than against prose.
