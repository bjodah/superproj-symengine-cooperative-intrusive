--TEST--
Debug ownership helpers expose cooperative state when enabled
--SKIPIF--
<?php
if (!extension_loaded('symengine')) die('skip symengine extension not loaded');
if (!method_exists('SymEngine\\Basic', 'cppUseCount')) die('skip debug ownership helpers unavailable');
?>
--FILE--
<?php
$zero = symengine_zero();
$x = symengine_symbol('x');

echo 'zero seeded: ', ($zero->isSingletonSeeded() ? 'true' : 'false'), "\n";
echo 'symbol seeded: ', ($x->isSingletonSeeded() ? 'true' : 'false'), "\n";
echo 'zero owner external: ', ($zero->externalOwnerAddress() !== 'inline' ? 'true' : 'false'), "\n";
echo 'symbol owner external: ', ($x->externalOwnerAddress() !== 'inline' ? 'true' : 'false'), "\n";
echo 'zero cpp use count: ', $zero->cppUseCount(), "\n";
echo 'symbol cpp use count: ', $x->cppUseCount(), "\n";
?>
--EXPECT--
zero seeded: true
symbol seeded: false
zero owner external: true
symbol owner external: true
zero cpp use count: 0
symbol cpp use count: 0
