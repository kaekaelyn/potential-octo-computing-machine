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

Status: M0 (skeleton), M1 (capture + leads inbox), M2 (feeds + watchers),
and M3 (requirements + vault + kit builder) complete. Daily-usable from
M1 on — share a post to Vamp, work the inbox, run the patrol checklist;
M3 adds READY/Missing badges, the unlock report, the kit builder, and
EPK export on top.
