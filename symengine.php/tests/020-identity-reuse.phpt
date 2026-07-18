--TEST--
Identity reuse: repeated wrapping of same singleton returns same PHP object
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
use SymEngine\Basic;

// Test singleton identity reuse
$zero1 = symengine_zero();
$zero2 = symengine_zero();
$zero3 = symengine_zero();

echo "zero1 === zero2: ", ($zero1 === $zero2 ? 'true' : 'false'), "\n";
echo "zero2 === zero3: ", ($zero2 === $zero3 ? 'true' : 'false'), "\n";
echo "zero1 === zero3: ", ($zero1 === $zero3 ? 'true' : 'false'), "\n";

// Test sameObject method
echo "zero1->sameObject(zero2): ", ($zero1->sameObject($zero2) ? 'true' : 'false'), "\n";
echo "zero2->sameObject(zero3): ", ($zero2->sameObject($zero3) ? 'true' : 'false'), "\n";

// Test other singletons
$one1 = symengine_one();
$one2 = symengine_one();
echo "one1 === one2: ", ($one1 === $one2 ? 'true' : 'false'), "\n";
echo "one1->sameObject(one2): ", ($one1->sameObject($one2) ? 'true' : 'false'), "\n";

$pi1 = symengine_pi();
$pi2 = symengine_pi();
echo "pi1 === pi2: ", ($pi1 === $pi2 ? 'true' : 'false'), "\n";
echo "pi1->sameObject(pi2): ", ($pi1->sameObject($pi2) ? 'true' : 'false'), "\n";

// Test non-singleton objects (should NOT be identical)
$int1 = symengine_integer(42);
$int2 = symengine_integer(42);
echo "int1 === int2: ", ($int1 === $int2 ? 'true' : 'false'), "\n";
echo "int1->sameObject(int2): ", ($int1->sameObject($int2) ? 'true' : 'false'), "\n";

// Same object variable reference
$int3 = $int1;
echo "int3 = int1; int3 === int1: ", ($int3 === $int1 ? 'true' : 'false'), "\n";
echo "int3->sameObject(int1): ", ($int3->sameObject($int1) ? 'true' : 'false'), "\n";
?>
--EXPECT--
zero1 === zero2: true
zero2 === zero3: true
zero1 === zero3: true
zero1->sameObject(zero2): true
zero2->sameObject(zero3): true
one1 === one2: true
one1->sameObject(one2): true
pi1 === pi2: true
pi1->sameObject(pi2): true
int1 === int2: false
int1->sameObject(int2): false
int3 = int1; int3 === int1: true
int3->sameObject(int1): true