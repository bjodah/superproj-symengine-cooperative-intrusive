--TEST--
Expression ownership: expression-held RCP pins operand wrapper
--SKIPIF--
<?php
if (!extension_loaded('symengine')) die('skip symengine extension not loaded');
if (!method_exists('SymEngine\\Basic', 'phpRefCount')) die('skip phpRefCount helper unavailable');
?>
--FILE--
<?php
$x = symengine_symbol('x');
$before = $x->phpRefCount();
$expr = symengine_add($x, symengine_integer(1));
$during = $x->phpRefCount();

echo 'expr: ', symengine_str($expr), "\n";
echo 'operand pinned: ', ($during > $before ? 'true' : 'false'), "\n";

unset($expr);
echo 'pin released: ', ($x->phpRefCount() === $before ? 'true' : 'false'), "\n";
?>
--EXPECT--
expr: 1 + x
operand pinned: true
pin released: true
