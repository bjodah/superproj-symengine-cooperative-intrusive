use strict;
use warnings;
use Test::More;
use Scalar::Util qw(refaddr);

use SymEngine;

# These tests exercise the cooperative_intrusive ownership model: a SymEngine
# object handed out to Perl is "externalized" so that the blessed inner SV
# becomes the object's reference-count anchor.  Every C++ RCP that points at the
# object is then mirrored as an SvREFCNT on that wrapper, and vice versa.

# --- Externalization basics ------------------------------------------------
{
    my $x = SymEngine::symbol('x');
    ok(SymEngine::is_external_owned($x),
        'a freshly handed-out wrapper is external-owned');
    is(SymEngine::perl_refcount($x), 1,
        'a freshly handed-out wrapper has a single Perl reference');
    is(SymEngine::cpp_use_count($x), 0,
        'use_count() is 0 in external-owned mode (Perl holds the references)');
}

# --- Identity reuse for an already-externalized object ---------------------
# add(x, 0) canonicalizes back to x, so SymEngine hands the very same C++ object
# back to Perl.  Because x already owns a wrapper, we must get that same wrapper
# (same inner SV) rather than a second one.
{
    my $x = SymEngine::symbol('x');
    my $again = SymEngine::add($x, SymEngine::integer(0));
    ok(SymEngine::same_object($x, $again),
        'add(x, 0) yields the same C++ object');
    is(refaddr($x), refaddr($again),
        'an already-externalized object reuses its existing Perl wrapper');
    is(SymEngine::perl_refcount($x), 2,
        'reusing the wrapper takes exactly one more Perl reference');
    undef $again;
    is(SymEngine::perl_refcount($x), 1,
        'dropping the reused wrapper restores the reference count');
}

# --- Wrappers are kept alive by copied C++ RCPs ----------------------------
# Building an expression copies an RCP to each operand into the new node, which
# (in external mode) pins the operand's Perl wrapper.
{
    my $expr;
    {
        my $x = SymEngine::symbol('x');
        is(SymEngine::perl_refcount($x), 1, 'lone symbol: refcount 1');
        $expr = SymEngine::add($x, SymEngine::integer(1));
        is(SymEngine::perl_refcount($x), 2,
            'the new expression holds a C++ ref that pins the operand wrapper');
    }
    # $x's lexical is gone, but the expression's internal RCP keeps it alive.
    is("$expr", '1 + x',
        'operand stays valid after its Perl wrapper leaves scope');
}

# --- Releasing the last C++ reference through Perl-owned mode ---------------
{
    my $x = SymEngine::symbol('solo');
    my $expr = SymEngine::add($x, SymEngine::integer(1));
    is(SymEngine::perl_refcount($x), 2, 'two references: lexical + expression');
    undef $expr;
    is(SymEngine::perl_refcount($x), 1,
        'releasing the expression releases its cooperative reference');
    # Dropping $x here releases the final reference and deletes the C++ object;
    # reaching the next statement proves the teardown path did not fault.
    undef $x;
    ok(1, 'final release of an externalized object did not crash');
}

# --- Singletons / canonical objects ----------------------------------------
{
    my $pi1 = SymEngine::pi();
    my $pi2 = SymEngine::pi();
    ok(SymEngine::same_object($pi1, $pi2), 'pi() is a shared C++ singleton');
    is(refaddr($pi1), refaddr($pi2),
        'repeated pi() calls reuse one Perl wrapper');
    ok(SymEngine::is_external_owned($pi1),
        'a singleton is external-owned while Perl holds it');

    # A singleton keeps a permanent C++ reference from its SymEngine static, so
    # its wrapper refcount never drops to the lexical count alone.
    cmp_ok(SymEngine::perl_refcount($pi1), '>=', 2,
        'singleton wrapper is pinned by the SymEngine C++ static too');
}

done_testing;
