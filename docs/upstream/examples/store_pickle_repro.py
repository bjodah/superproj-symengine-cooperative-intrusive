"""Reproduction C: symengine.py's store_pickle=True workaround avoids the leak
but loses round-trip identity and post-construction mutations.

Requires: pip install symengine  (measured against 0.14.1)
"""
import symengine


class PickleSymbol(symengine.Symbol):
    def __init__(self, name, tag=None):
        self.tag = tag
        super().__init__(name, store_pickle=True)

    def __reduce__(self):
        return (self.__class__, (str(self), self.tag))


x = PickleSymbol("x", tag="original")
expr = symengine.sin(x)
fs, = expr.free_symbols
print("identity preserved with store_pickle:", fs is x)
x.tag = "mutated-after-creation"
fs2, = expr.free_symbols
print("round-tripped object's .tag:", fs2.tag)
