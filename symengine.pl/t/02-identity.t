use strict;
use warnings;
use Test::More;

use SymEngine;

my $pi1 = SymEngine::pi();
my $pi2 = SymEngine::pi();

ok(SymEngine::same_object($pi1, $pi2), 'pi wrappers point at the same C++ singleton');
ok($pi1 == $pi2, 'pi wrappers compare equal');

my $x1 = SymEngine::symbol('x');
my $x2 = SymEngine::symbol('x');

ok($x1 == $x2, 'symbols with same name compare equal');
ok(!SymEngine::same_object($x1, $x2), 'equal symbols need not be the same C++ object');

done_testing;
