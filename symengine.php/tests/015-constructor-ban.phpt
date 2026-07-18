--TEST--
Direct PHP wrapper construction is banned
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
foreach (['SymEngine\\Basic', 'SymEngine\\Integer', 'SymEngine\\Symbol'] as $class) {
    try {
        new $class();
        echo $class, ": unexpected success\n";
    } catch (Exception $e) {
        echo $class, ': ', $e->getMessage(), "\n";
    }
}

$int = symengine_integer(1);
$sym = symengine_symbol('x');
echo 'int instance: ', ($int instanceof SymEngine\Integer ? 'true' : 'false'), "\n";
echo 'sym instance: ', ($sym instanceof SymEngine\Symbol ? 'true' : 'false'), "\n";
?>
--EXPECT--
SymEngine\Basic: SymEngine objects cannot be constructed directly; use symengine_integer(), symengine_symbol(), or SymEngine factory functions
SymEngine\Integer: SymEngine objects cannot be constructed directly; use symengine_integer(), symengine_symbol(), or SymEngine factory functions
SymEngine\Symbol: SymEngine objects cannot be constructed directly; use symengine_integer(), symengine_symbol(), or SymEngine factory functions
int instance: true
sym instance: true
