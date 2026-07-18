use strict;
use warnings;
use Test::More;

use SymEngine;

my $x = SymEngine::symbol('phase0_x');
my $two = SymEngine::integer(2);

is("$x", 'phase0_x', 'symbol');
is("$two", '2', 'integer');
is('' . SymEngine::zero(), '0', 'zero');
is('' . SymEngine::one(), '1', 'one');
is('' . SymEngine::pi(), 'pi', 'pi');
is('' . SymEngine::add($x, $two), '2 + phase0_x', 'add');
is('' . SymEngine::sub($x, $two), '-2 + phase0_x', 'sub');
is('' . SymEngine::mul($x, $two), '2*phase0_x', 'mul');
is('' . SymEngine::div($x, $two), '(1/2)*phase0_x', 'div');
is('' . SymEngine::pow($x, $two), 'phase0_x**2', 'pow');
is('' . SymEngine::neg($x), '-phase0_x', 'neg');
ok($x == SymEngine::symbol('phase0_x'), 'structural equality');
ok(!($x == SymEngine::symbol('phase0_y')), 'structural inequality');

done_testing;
