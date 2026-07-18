--TEST--
Phase 0 shared API smoke surface
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
$x = symengine_symbol('phase0_x');
$two = symengine_integer(2);

echo symengine_str($x), "\n";
echo symengine_str($two), "\n";
echo symengine_str(symengine_zero()), "\n";
echo symengine_str(symengine_one()), "\n";
echo symengine_str(symengine_pi()), "\n";
echo symengine_str(symengine_add($x, $two)), "\n";
echo symengine_str(symengine_sub($x, $two)), "\n";
echo symengine_str(symengine_mul($x, $two)), "\n";
echo symengine_str(symengine_div($x, $two)), "\n";
echo symengine_str(symengine_pow($x, $two)), "\n";
echo symengine_str(symengine_neg($x)), "\n";
var_export(symengine_eq($x, symengine_symbol('phase0_x'))); echo "\n";
var_export(symengine_eq($x, symengine_symbol('phase0_y'))); echo "\n";
?>
--EXPECT--
phase0_x
2
0
1
pi
2 + phase0_x
-2 + phase0_x
2*phase0_x
(1/2)*phase0_x
phase0_x**2
-phase0_x
true
false
