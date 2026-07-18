# symengine.pl

Minimal Perl XS wrapper for SymEngine.

This subproject exists to validate SymEngine's cooperative reference-counting
work against a second reference-counted runtime. The first binding surface is
deliberately small: symbols, integers, constants, arithmetic helpers,
stringification, equality, and ownership probes.

## Local build

Build SymEngine first, then build and test the Perl extension:

```bash
cmake -S .. -B ../build-perl -G Ninja \
  -DSYMENGINE_RCP_BACKEND=cooperative_intrusive
cmake --build ../build-perl --target symengine

SYMENGINE_SOURCE_DIR=../symengine \
SYMENGINE_BUILD_DIR=../build-perl/symengine \
perl Makefile.PL
make
prove -lv t
```

SymEngine core now provides the generic `cooperative_intrusive` backend without
depending on nanobind headers. The current Perl XS wrapper keeps Perl-specific
code local to `xs/perl_symengine.*`.

## Current constraints

- One Perl interpreter.
- No Perl ithreads support.
- Minimal API only.
- Full Perl-side cooperative ownership is not wired up yet; the current holder
  remains an `RCP<const Basic>` stored inside the Perl wrapper.
