# reasoning/ — Vendored Semantica Rete engine + rule facade

Vendored from **[semantica-agi/semantica](https://github.com/semantica-agi/semantica)**
`semantica/reasoning/` (MIT license), plus an EAI-CUSTOM facade adaptation layer.

- **Pinned SHA:** `7057387775ecdf74c14e38d0067fd8e1267eaaf8` (repo HEAD at vendoring time, 2026-09-13; same commit as the frontend explorer vendor in `frontend/src/extensions/ontology/explorer/`)
- **License:** MIT (upstream repo LICENSE)
- **EAI-CUSTOM plan:** `docs/superpowers/plans/2026-09-13-ontology-reasoning-rules.md` Task 1
- **Design:** `docs/superpowers/specs/2026-09-13-ontology-reasoning-rules-design.md` §3

## Vendored file inventory

| Upstream | Local |
| --- | --- |
| `semantica/reasoning/rete_engine.py` | `rete_engine.py` |

Dependency closure of `rete_engine.py` upstream is exactly 3 package-internal
imports (`..utils.logging`, `..utils.progress_tracker`, `.reasoner`); well under
the 25-file BLOCKED threshold in plan Step 1.3. Rather than vendoring the
~36KB `reasoner.py` (whose own closure pulls action/GKG write-back machinery
this engine never uses), the three names it needs are inlined as shims.

## Strip records (plan Step 1.3)

All strips are inside the clearly marked `EAI vendoring shims` block at the top
of `rete_engine.py`; algorithm code below the block is unchanged upstream.

1. **`from ..utils.logging import get_logger`** → stdlib `logging.getLogger`.
   Upstream `get_logger` is a thin named-logger wrapper; no formatting/profile
   behaviour is needed here.
2. **`from ..utils.progress_tracker import get_progress_tracker`** → no-op
   `_NoopProgressTracker` (`start_tracking`/`stop_tracking`/`update_tracking`
   return/pass). Upstream uses the tracker purely for console progress
   reporting around `build_network`/`match_patterns`/`execute_matches`; there
   is no reporting sink in this deployment.
3. **`from .reasoner import Fact, Rule, _make_activation_key`** → inline
   equivalents:
   - `Fact` — faithful copy of the upstream dataclass (incl. `__str__`
     rendering `pred(a, b)`, which the regex matcher relies on).
   - `Rule` — same dataclass shape, but `rule_type: RuleType` (enum) and
     `actions: List[Action]` degraded to inert plain-typed fields. ReteEngine
     never reads them; they only matter when a `Reasoner` is bound for
     side-effect actions, which this deployment never does.
   - `_make_activation_key` — simplified to the value domain the engine's only
     call site passes (string bindings + `(fact_id, predicate, arguments)`
     tuples). Upstream's generic `_canonicalize_activation_value` (nested
     mappings/sets) has no feeder here.

Additive-only edits (upstream code untouched):

- Vendored-source header comment + `# ruff: noqa: UP006, UP035, UP045` — the
  vendored file keeps upstream's `typing.Dict/List/Optional` style; this repo
  enables `UP` in `backend/ruff.toml`. Narrow file-level exemption, recorded
  here as the sanctioned vendoring adaptation.
- The whole file (upstream code included) is ruff-formatted to this repo's
  240-column style (upstream ships 88-column formatting), so line layout
  differs from upstream while semantics are unchanged.
- License kept alongside the code: `LICENSE-SEMANTICA-MIT` in this directory is
  the upstream repo `LICENSE` verbatim at the pinned SHA (explorer/ precedent in
  `frontend/src/extensions/ontology/explorer/`).
- Facade layer (`facade.py`, EAI-CUSTOM): registration validation raises the
  dedicated `RuleSyntaxError(ValueError)` so the Task 3 MCP layer can narrow-
  catch rule-registration failures without swallowing unrelated `ValueError`s;
  duplicate rule names are rejected to keep activation provenance unambiguous.

## Facade semantics (`facade.py`, EAI-CUSTOM)

Implementation route: **adapt the vendored ReteEngine API** (route a). The
alpha/beta/terminal network and token propagation do the matching and joining;
the facade adds only the triple-space adaptation, the fixpoint loop, and the
hardcoded caps (~60 lines of glue, no reinvented matcher).

- **Fact space is triples** `(subject, predicate, object)`. Patterns
  (`"<predicate>(?var, ?var)"`) project a triple by arity: 1-arg pattern
  `p(?X)` binds the subject (type facts: predicate = etype, e.g. `mine(?M)`);
  2-arg pattern binds `(subject, object)`. A predicate referenced with both
  arities gets both projection views.
- **Derived facts feed back** into the fact space for subsequent iterations
  (forward chain). Re-deriving a known fact is not double-counted, and the
  same activation (rule + bindings + premises, keyed by upstream
  `_make_activation_key`) never fires twice across iterations.
- **`run()`** chains to fixpoint (an iteration with no new facts) and returns
  `{"derived": [{subject, predicate, object, rule}], "activations": [{rule,
  facts}], "stats": {...}}`. It does not mutate the facade's registered
  facts/rules, so it can be called repeatedly with identical results.
- **Hardcoded caps** (`MAX_ITERATIONS=10`, `MAX_DERIVED=1000`,
  `MAX_RULE_FIRES=500`): reaching any cap stops the chain and sets the
  corresponding `max_*_reached` flag in `stats` — never raises.
- **Registration-time fail-closed validation**: malformed patterns/conclusions
  (arity not in {1, 2}, non-`?var` arguments) raise `ValueError` at
  `add_rule()` instead of silently never matching.
- **No enable/disable here** — the registration layer (plan Task 2,
  `rule_registry.py`) filters rules by `enabled` before they reach the facade.
- `add_fact(inferred=..., rule=...)` is provenance annotation only; it does not
  affect matching.

## Known limitations (inherited from upstream string-based matching)

- Fact values containing `", "` or `")"` corrupt pattern matching (upstream
  renders facts as strings and matches with anchored regexes). In-domain
  entity names/IRIs do not contain these; the Task 2 rule lint narrows
  predicates to the registry enum.
- Pattern arguments must be `?vars`; constant arguments (supported upstream via
  inlined `initial_bindings`) are out of scope for this facade.
- Conclusion templates substitute bound `?vars` token-aware; unbound vars stay
  as literal `"?var"` text in the derived fact (Task 2 lint can pin variable
  coverage).

## Tests

`backend/tests/test_reasoning_rete.py` — 11 cases: single-pattern derive,
two-pattern join, no-match, self-feed fixpoint, chained forward feeding,
MAX_RULE_FIRES cap really stopping the run, three fail-closed registration
pins (malformed pattern / arity 3 / non-`?var` conclusion), duplicate rule
name rejection, and the source-level check that enable/disable filtering
stays out of the facade.
