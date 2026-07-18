--TEST--
SymEngine extension loads and reports version
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
var_dump(extension_loaded('symengine'));
var_dump(phpversion('symengine'));
var_dump(defined('SYMENGINE_VERSION') ? SYMENGINE_VERSION : 'constant not defined');
?>
--EXPECT--
bool(true)
string(5) "0.1.0"
string(20) "constant not defined"