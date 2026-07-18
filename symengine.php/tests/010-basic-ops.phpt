--TEST--
Basic operations: integer, symbol, add, sub, div, mul, neg, pow, str, eq
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
use SymEngine\Basic;
use SymEngine\Integer;
use SymEngine\Symbol;

// Integer creation
$i5 = symengine_integer(5);
$i3 = symengine_integer(3);
var_dump(get_class($i5));
var_dump(get_class($i3));

// Symbol creation
$x = symengine_symbol('x');
$y = symengine_symbol('y');
var_dump(get_class($x));

// String representation
echo "str(5): ", symengine_str($i5), "\n";
echo "str(x): ", symengine_str($x), "\n";

// Addition
$add = symengine_add($i5, $i3);
echo "5 + 3 = ", symengine_str($add), "\n";

// Subtraction
$sub = symengine_sub($x, $y);
echo "x - y = ", symengine_str($sub), "\n";

// Division
$div = symengine_div($i5, $i3);
echo "5 / 3 = ", symengine_str($div), "\n";

// Multiplication
$mul = symengine_mul($i5, $i3);
echo "5 * 3 = ", symengine_str($mul), "\n";

// Negation
$neg = symengine_neg($x);
echo "neg(x) = ", symengine_str($neg), "\n";

// Power
$pow = symengine_pow($i5, $i3);
echo "5 ^ 3 = ", symengine_str($pow), "\n";

// Symbolic operations
$expr1 = symengine_add($x, $y);
echo "x + y = ", symengine_str($expr1), "\n";

$expr2 = symengine_mul($x, $y);
echo "x * y = ", symengine_str($expr2), "\n";

$expr3 = symengine_pow($x, symengine_integer(2));
echo "x ^ 2 = ", symengine_str($expr3), "\n";

// Equality
echo "eq(5, 5): ", var_export(symengine_eq($i5, symengine_integer(5)), true), "\n";
echo "eq(5, 3): ", var_export(symengine_eq($i5, $i3), true), "\n";
echo "eq(x+y, y+x): ", var_export(symengine_eq($expr1, symengine_add($y, $x)), true), "\n";

// Constants
echo "zero: ", symengine_str(symengine_zero()), "\n";
echo "one: ", symengine_str(symengine_one()), "\n";
echo "two: ", symengine_str(symengine_two()), "\n";
echo "pi: ", symengine_str(symengine_pi()), "\n";
echo "e: ", symengine_str(symengine_e()), "\n";
?>
--EXPECTF--
string(%d) "SymEngine\Integer"
string(%d) "SymEngine\Integer"
string(%d) "SymEngine\Symbol"
str(5): 5
str(x): x
5 + 3 = 8
x - y = x - y
5 / 3 = 5/3
5 * 3 = 15
neg(x) = -x
5 ^ 3 = 125
x + y = x + y
x * y = x*y
x ^ 2 = x**2
eq(5, 5): true
eq(5, 3): false
eq(x+y, y+x): true
zero: 0
one: 1
two: 2
pi: pi
e: E
