--TEST--
Temporary C++ handles: operations constructing temporary RCPs don't break ownership
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
use SymEngine\Basic;

// Test basic operations that create temporary C++ handles
$sum = symengine_add(symengine_integer(2), symengine_integer(3));
echo "sum: ", symengine_str($sum), "\n";
echo "sum->isExternalOwned(): ", ($sum->isExternalOwned() ? 'true' : 'false'), "\n";

$prod = symengine_mul(symengine_integer(2), symengine_integer(3));
echo "prod: ", symengine_str($prod), "\n";
echo "prod->isExternalOwned(): ", ($prod->isExternalOwned() ? 'true' : 'false'), "\n";

$pow = symengine_pow(symengine_integer(2), symengine_integer(3));
echo "pow: ", symengine_str($pow), "\n";
echo "pow->isExternalOwned(): ", ($pow->isExternalOwned() ? 'true' : 'false'), "\n";

// Chained operations
$expr = symengine_add(
    symengine_mul(symengine_integer(3), symengine_symbol('x')),
    symengine_mul(symengine_integer(2), symengine_symbol('y'))
);
echo "expr: ", symengine_str($expr), "\n";
echo "expr->isExternalOwned(): ", ($expr->isExternalOwned() ? 'true' : 'false'), "\n";

// Verify original objects still intact
echo "a: ", symengine_str(symengine_integer(2)), "\n";
echo "b: ", symengine_str(symengine_integer(3)), "\n";
// a and symengine_integer(2) are different objects (same value, different identity)
$a_same = symengine_integer(2)->sameObject(symengine_integer(2));
echo "a->sameObject(symengine_integer(2)): ", ($a_same ? 'true' : 'false'), "\n";

// Test with symbols - more complex temporaries
$x = symengine_symbol('x');
$y = symengine_symbol('y');

$expr2 = symengine_add(
    symengine_mul(symengine_integer(3), symengine_pow($x, symengine_integer(2))),
    symengine_mul(symengine_integer(2), $y)
);
echo "expr2: ", symengine_str($expr2), "\n";
echo "expr2->isExternalOwned(): ", ($expr2->isExternalOwned() ? 'true' : 'false'), "\n";

// Multiple operations on same object
$int = symengine_integer(5);
$int_ref1 = $int->phpRefCount();
$sum1 = symengine_add($int, symengine_integer(1));
$sum2 = symengine_add($int, symengine_integer(2));
$int_ref2 = $int->phpRefCount();
echo "int refcount after multiple ops: ", $int_ref2, "\n";
echo "int refcount stable: ", ($int_ref2 == $int_ref1 ? 'true' : 'false'), "\n";

// Test that temporary objects don't share identity
$expr_a = symengine_add(symengine_integer(1), symengine_integer(2));
$expr_b = symengine_add(symengine_integer(1), symengine_integer(2));
echo "expr_a->sameObject(expr_b): ", ($expr_a->sameObject($expr_b) ? 'true' : 'false'), "\n";

// Test singleton identity preserved through operations
$zero = symengine_zero();
$zero2 = symengine_add($zero, symengine_integer(0));
echo "zero_after->sameObject(zero): ", ($zero2->sameObject($zero) ? 'true' : 'false'), "\n";
?>
--EXPECTF--
sum: 5
sum->isExternalOwned(): true
prod: 6
prod->isExternalOwned(): true
pow: 8
pow->isExternalOwned(): true
expr: 3*x + 2*y
expr->isExternalOwned(): true
a: 2
b: 3
a->sameObject(symengine_integer(2)): false
expr2: 2*y + 3*x**2
expr2->isExternalOwned(): true
int refcount after multiple ops: %d
int refcount stable: true
expr_a->sameObject(expr_b): false
zero_after->sameObject(zero): true