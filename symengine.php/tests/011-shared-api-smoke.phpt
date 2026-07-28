--TEST--
Bootstrap surface (arithmetic/constants live in the generated shared cases)
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
// The arithmetic, constant and string expectations that used to be repeated
// here now live in binding-spec/test-cases.yaml and are rendered into
// generated/090-shared-cases.phpt.  What remains is what that shared schema
// cannot express: the hand-written factory functions and symengine_eq().
$x = symengine_symbol('phase0_x');
$two = symengine_integer(2);

echo symengine_str($x), "\n";
echo symengine_str($two), "\n";
var_export(symengine_eq($x, symengine_symbol('phase0_x'))); echo "\n";
var_export(symengine_eq($x, symengine_symbol('phase0_y'))); echo "\n";
?>
--EXPECT--
phase0_x
2
true
false
