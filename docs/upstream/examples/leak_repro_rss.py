"""Reproduction B: unbounded RSS growth from Symbol-subclass churn in symengine.py.

Requires: pip install symengine  (measured against 0.14.1)
"""
import gc
import resource

import symengine


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


class MySymbol(symengine.Symbol):
    pass


N = 200_000
base = rss_mb()
for i in range(N):
    s = symengine.Symbol(f"plain_{i}")
    del s
gc.collect()
print(f"plain Symbol:    RSS delta {rss_mb() - base:+7.1f} MiB")

base = rss_mb()
for i in range(N):
    s = MySymbol(f"sub_{i}")
    del s
gc.collect()
print(f"Symbol subclass: RSS delta {rss_mb() - base:+7.1f} MiB")

x = MySymbol("x")
fs, = symengine.sin(x).free_symbols
print("round-trip identity preserved:", fs is x, "| type:", type(fs).__name__)
