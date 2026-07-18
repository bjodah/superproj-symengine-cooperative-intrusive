"""Demonstration: the cooperative_intrusive backend runs the same probes as
reproductions A/B with no leak, while keeping identity and mutations.

Requires nbsymengine built with SYMENGINE_RCP_BACKEND=cooperative_intrusive
on PYTHONPATH, e.g.:
  SYMENGINE_RCP_CHOICE=cooperative_intrusive .ci/ci-02-build-and-test-nbsymengine.sh <builddir>
  PYTHONPATH=<builddir> python docs/upstream/examples/no_leak_demo.py
"""
import gc
import resource
import weakref

from nbsymengine import _core as se


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


class MySymbol(se.Symbol):
    def __init__(self, name, extra=None):
        super().__init__(name)
        self.extra = extra


refs = []
for i in range(1000):
    s = MySymbol(f"s{i}", extra=list(range(100)))
    refs.append(weakref.ref(s))
    del s
for _ in range(3):
    gc.collect()
print(f"subclass instances still alive after del + gc.collect(): "
      f"{sum(1 for r in refs if r() is not None)}/1000")

N = 200_000
base = rss_mb()
for i in range(N):
    s = se.Symbol(f"plain_{i}")
    del s
gc.collect()
print(f"plain Symbol:    RSS delta {rss_mb() - base:+7.1f} MiB")

base = rss_mb()
for i in range(N):
    s = MySymbol(f"sub_{i}")
    del s
gc.collect()
print(f"Symbol subclass: RSS delta {rss_mb() - base:+7.1f} MiB")

x = MySymbol("x", extra="user-data")
expr = se.sin(x)
arg, = expr.get_args()
print("round-trip identity preserved:", arg is x,
      "| type:", type(arg).__name__, "| .extra:", arg.extra)
x.extra = "mutated-after-creation"
arg2, = expr.get_args()
print("mutation visible after round-trip:", arg2.extra)
