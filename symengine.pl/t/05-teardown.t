use strict;
use warnings;
use Test::More;

# Interpreter teardown is where cooperative ownership is hardest: SymEngine's
# singletons are pinned by C++ statics whose destructors run *after* the Perl
# interpreter is gone.  We run a child interpreter under the most aggressive
# global-destruction mode (PERL_DESTRUCT_LEVEL=2) and assert it exits cleanly
# with a mix of live singletons and ordinary expressions still referenced.

my $code = <<'CHILD';
use SymEngine;
my @keep;
# Singletons (pinned by SymEngine C++ statics).
push @keep, SymEngine::pi();
push @keep, SymEngine::one();
push @keep, SymEngine::zero();
# Ordinary expressions referencing operands that are themselves kept alive.
my $x = SymEngine::symbol('x');
my $y = SymEngine::symbol('y');
push @keep, SymEngine::add($x, SymEngine::integer(1));
push @keep, SymEngine::mul($x, $y);
push @keep, SymEngine::sin(SymEngine::pow($x, SymEngine::integer(2)));
# A heavily-shared singleton wrapped via a canonicalized expression.
push @keep, SymEngine::add($x, SymEngine::integer(0));
exit 0;
CHILD

my @inc = map { "-I$_" } @INC;
local $ENV{PERL_DESTRUCT_LEVEL} = 2;
# This probe asserts crash-free teardown, not leak-freeness.  An ASAN-enabled
# perl exits non-zero from its *own* interpreter leaks, which would mask the
# signal we care about, so disable leak detection in the child.
local $ENV{ASAN_OPTIONS} = 'detect_leaks=0:' . ($ENV{ASAN_OPTIONS} // '');

my $status = system($^X, @inc, '-e', $code);

is($status, 0,
    'child interpreter tears down cleanly with live singletons (PERL_DESTRUCT_LEVEL=2)')
    or diag("child exited with wait status $status");

done_testing;
