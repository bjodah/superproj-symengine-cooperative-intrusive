--TEST--
Canonical identity reuse: add(x, 0) returns the existing PHP wrapper
--SKIPIF--
<?php
if (!extension_loaded('symengine')) die('skip symengine extension not loaded');
if (!method_exists('SymEngine\\Basic', 'phpRefCount')) die('skip phpRefCount helper unavailable');
?>
--FILE--
<?php
$x = symengine_symbol('x');
$before = $x->phpRefCount();
$again = symengine_add($x, symengine_zero());

echo 'same zval: ', ($x === $again ? 'true' : 'false'), "\n";
echo 'same native: ', ($x->sameObject($again) ? 'true' : 'false'), "\n";
echo 'refcount increased: ', ($x->phpRefCount() > $before ? 'true' : 'false'), "\n";

unset($again);
echo 'refcount restored: ', ($x->phpRefCount() === $before ? 'true' : 'false'), "\n";
?>
--EXPECT--
same zval: true
same native: true
refcount increased: true
refcount restored: true
