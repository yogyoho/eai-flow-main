# CEO Review — Implementation Tasks

> Generated: 2026-06-15 | Mode: HOLD SCOPE | Branch: fix/four-module-p0-df2-df3-df5-df6

## P1 — Block ship ✅ ALL DONE

- [x] **T1** ✅ — Review Context — Switched activities to ReviewAssignment + wired evaluate_gate()
  - `create_review_assignments` → creates ReviewAssignment rows
  - `check_reviews_complete` → queries ReviewAssignment + calls evaluate_gate()
  - `handle_rejection` → resets ReviewAssignment rows
  - Files: `activities.py`, `review_activities.py` (extracted)

- [x] **T2** ✅ — Doc Merge — Fixed hardcoded title suffix
  - Replaced `"_消防设计报告"` with dynamic mapping from project.report_type
  - File: `notification_activities.py` (`_sync_chapters_to_doc_space`)

- [x] **T3** ✅ — Phase Duties — Migrated duty key to role key
  - `_get_member_duty` reads `role` key first, falls back to `duty`
  - `init_task` writes `{"role": role_key}` (unified format)
  - File: `review_activities.py`, `activities.py`

- [x] **T4** ✅ — LLM Validation — Added content validation
  - `_validate_generated_content()`: empty check + refusal detection
  - `_sanitize_log_msg()`: credential stripping for logs
  - 2 new tests: empty_content → empty_error, refusal → refusal_error
  - File: `writing_activities.py`

- [x] **T5** ✅ — Security — Added ownership validation + log sanitization
  - `start_ai_writing`: verifies chapter.project_id == given project_id
  - `_sanitize_log_msg`: truncates + strips key=, api_key=, token=, secret= patterns

## P2 — Should land same branch ✅ ALL DONE

- [x] **T6** ✅ — Integration Tests — 22 tests covering E2E workflow chain
  - New file: `backend/tests/test_workflow_integration.py`
  - Tests: gate strategies (5), review check (3), rollback (1), chapter lifecycle (3), finalize (5), E2E chain (2), dependency graph (3)

- [x] **T7** ✅ — Code Organization — Split activities.py into bounded-context modules
  - `writing_activities.py`: AI generation + source parsing (4 activities + helpers)
  - `review_activities.py`: review assignment + gate + rejection (4 activities)
  - `notification_activities.py`: phase/review/workflow notifications (3 activities)
  - `activities.py`: orchestration (init/advance/evaluate/gather) + re-exports

- [x] **T8** ✅ — Finalize Flow — execute_finalize now merges chapter content
  - Creates document with merged chapter content (not empty shell)
  - Resolves project folder, generates title from report_type
  - File: `backend/app/extensions/docmgr/finalize.py`

## P3 — Follow-up TODOs ✅ ALL DONE

- [x] **T9** ✅ — Review Timeout — 24h/48h/72h escalation
  - `create_review_assignments`: sets `deadline_at` = now + 48h
  - `notify_review_pending`: checks deadlines, escalates overdue to phase_lead (>48h) and owner (>72h)
  - Helper functions: `_resolve_phase_lead_ids`, `_resolve_owner_ids`
  - 3 new tests: deadline notification + escalation chain
  - Files: `review_activities.py`, `notification_activities.py`

- [x] **T10** ✅ — Observability — Trace IDs + metrics
  - New `workflow/metrics.py`: in-process counters, structured event logging
  - `record_ai_generation_success/failure` wired into `start_ai_writing`
  - `record_review_action` wired into `check_reviews_complete`
  - `record_workflow_phase_transition` wired into `init_phase`
  - `get_metrics_snapshot()` for admin/debug endpoints
  - Files: `workflow/metrics.py` (new), `writing_activities.py`, `review_activities.py`, `activities.py`
