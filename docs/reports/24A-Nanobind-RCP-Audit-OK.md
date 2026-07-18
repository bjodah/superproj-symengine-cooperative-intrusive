## Nanobind race-fix currency audit (COMPLETED — findings recorded here)

**Question asked:** latest git nanobind carries fixes for race conditions around
its intrusive reference counting; are we up to date?

**Verdict: yes, on both axes that matter.** Verified 2026-07-10:

* The vendored submodule `nbsymengine/external/nanobind` is pinned at
  `9f65626` (v2.12.0-114). Upstream `master` was at `ff6a401` (2026-07-07),
  42 commits ahead — **none** of those touch `include/nanobind/intrusive/`
  (`git diff --stat 9f65626 ff6a401 -- include/nanobind/intrusive` is empty),
  and none mention intrusive/race in their messages (they are ndarray/stubgen
  perf work plus the v2.13.0 release commit).
* Every intrusive-counter fix in nanobind's entire history is an ancestor of
  our pin, including the two race-relevant ones:
  * `ee64aa1` (2026-06-12) — *"Fix lost reference updates in
    intrusive_counter::set_self_py"*: replaced the load → transfer → plain-store
    hand-off with a CAS retry loop that transfers refs **before** publication.
  * `47abc72` (2024-02-14) — check the deletion refcount **after** the cmpxchg.
* The CI toolchain does **not** build against the submodule: `ci_apply_rcp_choice`
  resolves `nanobind_DIR` via `python -m nanobind --cmake_dir`, i.e. the
  pip-installed **nanobind 2.13.0** (released 2026-06-18) — which also contains
  all of the above fixes.

**Our reimplementation is at parity.** `symengine/symengine/symengine_rcp_cooperative.cpp`
is a faithful port of `counter.inl` at the fixed revision:

| nanobind fix | our port | status |
|---|---|---|
| `ee64aa1` CAS loop w/ pre-publication transfer + post-CAS surplus decref | `set_self_external()` lines 113–133 | ported |
| `47abc72` post-cmpxchg `v == 3` deletion check | `dec_ref()` line 102 | ported |
| underflow abort in `dec_ref` | `dec_ref()` lines 93–97 | ported (via `cooperative_abort`) |
| relaxed (`0`) atomic orderings, MSVC `_InterlockedCompareExchangePointer` fallback | same macros | ported |
