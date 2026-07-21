# Vamp

A phone-hosted, local-first copilot for building a working musician's
career in the Oklahoma City metro — gig/job/competition aggregation with
ruthless filters, a requirements-vs-your-kit readiness system, and an
outbound prospects engine for all the paying work that never gets posted.

Named for "vamp till ready": improvise indefinitely until the cue.

- **What and why:** [`PLAN.md`](PLAN.md)
- **How it gets built (milestones, session prompts, model assignments):**
  [`docs/EXECUTION.md`](docs/EXECUTION.md)
- **Rules for coding sessions:** [`CLAUDE.md`](CLAUDE.md)

Runs entirely on an Android phone under [Termux](https://termux.dev/) —
the phone is both server and client. No cloud, no accounts, no telemetry,
no auto-sending anything, ever.

Status: M0–M7 complete — skeleton, capture + leads inbox, feeds + watchers,
requirements + vault + kit builder, prospects engine + OKC seed data, the
AI layer, money/scene/people, and notification + phone-ops polish. See
`docs/DEMO.md` for a milestone-by-milestone walkthrough and `PLAN.md` §12
for what each one covers. Daily-usable from M1 on — share a post to Vamp,
work the inbox, run the patrol checklist; every milestone since adds more
of the loop: READY/Missing badges and the kit builder (M3), the outbound
prospects engine (M4), AI-assisted scoring and drafting (M5), gigs/income/
scene/people (M6), and the morning digest + Outreach Sprint notifications,
seasonal playbook reminders, and the metrics page (M7).
