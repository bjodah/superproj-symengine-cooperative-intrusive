# Bootstrap baseline for SymEngine.pm.
#
# The arithmetic, constant and string expectations that used to be repeated
# here now live in binding-spec/test-cases.yaml and are rendered into the
# generated shared_cases.t.  What remains is what that shared schema cannot
# express: the module loads, the hand-written factory XSUBs work, and the
# overloaded structural comparison holds.
use strict;
use warnings;
use Test::More;

use SymEngine;

my $x = SymEngine::symbol('phase0_x');
my $two = SymEngine::integer(2);

is("$x", 'phase0_x', 'symbol');
is("$two", '2', 'integer');
ok($x == SymEngine::symbol('phase0_x'), 'structural equality');
ok(!($x == SymEngine::symbol('phase0_y')), 'structural inequality');

done_testing;
