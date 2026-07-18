use strict;
use warnings;
use Test::More;

use SymEngine;

my $x = SymEngine::symbol('x');
isa_ok($x, 'SymEngine::Basic');
is("$x", 'x', 'symbol stringifies');

my $two = SymEngine::integer(2);
isa_ok($two, 'SymEngine::Basic');
is("$two", '2', 'integer stringifies');

my $sum = SymEngine::add($x, SymEngine::integer(1));
is("$sum", '1 + x', 'add works');

my $product = SymEngine::mul($x, $two);
is("$product", '2*x', 'mul works');

my $power = SymEngine::pow($x, $two);
is("$power", 'x**2', 'pow works');

my $neg = SymEngine::neg($x);
is("$neg", '-x', 'neg works');

my $sin = SymEngine::sin($x);
is("$sin", 'sin(x)', 'sin works');

done_testing;
