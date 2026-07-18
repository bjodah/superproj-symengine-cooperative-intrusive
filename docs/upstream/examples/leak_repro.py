"""Reproduction A: symengine.py Symbol-subclass instances are never collected.

Requires: pip install symengine  (measured against 0.14.1)
"""
import gc
import weakref

import symengine


class MySymbol(symengine.Symbol):
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
alive = sum(1 for r in refs if r() is not None)
print(f"subclass instances still alive after del + gc.collect(): {alive}/1000")
