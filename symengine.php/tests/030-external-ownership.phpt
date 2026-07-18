--TEST--
External ownership: isExternalOwned true after wrapping; phpRefCount predictable
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
use SymEngine\Basic;

// Test singleton external ownership
$zero = symengine_zero();
echo "zero->isExternalOwned(): ", ($zero->isExternalOwned() ? 'true' : 'false'), "\n";
$zero_initial_ref = $zero->phpRefCount();
echo "zero->phpRefCount() (initial): ", $zero_initial_ref, "\n";

// Test integer external ownership
$int = symengine_integer(42);
echo "int->isExternalOwned(): ", ($int->isExternalOwned() ? 'true' : 'false'), "\n";
$int_initial_ref = $int->phpRefCount();
echo "int->phpRefCount() (initial): ", $int_initial_ref, "\n";

// Copy reference - refcount should increase
$int2 = $int;
echo "int->phpRefCount() (after copy): ", $int->phpRefCount(), "\n";
echo "int2->phpRefCount(): ", $int2->phpRefCount(), "\n";
$after_copy_ref = $int->phpRefCount();
echo "refcount increased: ", ($after_copy_ref > $int_initial_ref ? 'true' : 'false'), "\n";

// Unset one reference - refcount should decrease
unset($int2);
$after_unset_ref = $int->phpRefCount();
echo "int->phpRefCount() (after unset): ", $after_unset_ref, "\n";
echo "refcount decreased: ", ($after_unset_ref < $after_copy_ref ? 'true' : 'false'), "\n";

// Test symbol external ownership
$sym = symengine_symbol('x');
echo "sym->isExternalOwned(): ", ($sym->isExternalOwned() ? 'true' : 'false'), "\n";

// Test expression external ownership
$expr = symengine_add(symengine_integer(1), symengine_integer(2));
echo "expr->isExternalOwned(): ", ($expr->isExternalOwned() ? 'true' : 'false'), "\n";

// Verify sameObject works with singleton wrappers
$zero2 = symengine_zero();
echo "zero->sameObject(zero2): ", ($zero->sameObject($zero2) ? 'true' : 'false'), "\n";

// Test that non-external-owned check works (should not happen for wrapped objects)
$int3 = symengine_integer(100);
echo "int3->isExternalOwned(): ", ($int3->isExternalOwned() ? 'true' : 'false'), "\n";

// Copying a singleton wrapper should change its PHP refcount predictably too.
// The tracking array holds an extra ref, so initial refcount is higher.
$zero_copy = $zero;
$zero_after_copy = $zero->phpRefCount();
echo "zero refcount increased on copy: ", ($zero_after_copy > $zero_initial_ref ? 'true' : 'false'), "\n";
unset($zero_copy);
echo "zero refcount dropped after unset: ", ($zero->phpRefCount() < $zero_after_copy ? 'true' : 'false'), "\n";
?>
--EXPECTF--
zero->isExternalOwned(): true
zero->phpRefCount() (initial): %d
int->isExternalOwned(): true
int->phpRefCount() (initial): %d
int->phpRefCount() (after copy): %d
int2->phpRefCount(): %d
refcount increased: true
int->phpRefCount() (after unset): %d
refcount decreased: true
sym->isExternalOwned(): true
expr->isExternalOwned(): true
zero->sameObject(zero2): true
int3->isExternalOwned(): true
zero refcount increased on copy: true
zero refcount dropped after unset: true
