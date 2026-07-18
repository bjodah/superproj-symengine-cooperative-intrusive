use strict;
use warnings;
use Test::More;

use SymEngine;

my $expr;
{
    my $x = SymEngine::symbol('x');
    $expr = SymEngine::add($x, SymEngine::integer(1));
    isa_ok($expr, 'SymEngine::Basic');
}

is("$expr", '1 + x', 'expression remains valid after input wrapper leaves scope');

{
    my $x = SymEngine::symbol('x');
    my $sin = SymEngine::sin($x);
    is("$sin", 'sin(x)', 'function expression remains valid');
}

my $one = SymEngine::one();
ok(SymEngine::cpp_use_count($one) >= 0, 'ownership probe is callable');

done_testing;
