"""Domain modules.

Each module owns its tables, its rules and its HTTP surface, and talks to its
neighbours through their service functions rather than their tables. The
boundaries are the same ones the nine frontend apps are split along, which is
what makes "one module per app" more than a directory convention:

    tenancy      control plane: universities, plans, platform staff
    identity     accounts, sessions, roles, permissions
    shared       reference data every module needs: units, academic calendar
    admissions   application through to enrolment
    students     the student record and its life-cycle events
    curriculum   programmes, courses, versions, timetabling
    finance      fees, invoices, receipts, sponsorship, the student ledger
    people       staff records, appointments, workload, leave
    assessment   marks, moderation, boards, awards, transcripts
    governance   audit, policy overlays, reporting, statutory returns
    developers   API clients, keys, webhooks, sandbox

Import direction is enforced in `tests/test_module_boundaries.py`: `shared` and
`identity` may be imported by anyone, and nothing may import `governance`
except through `acmis.core.audit`. A module that reaches into another's models
is the first step towards a monolith nobody can split later, and this one is
meant to stay splittable.
"""
