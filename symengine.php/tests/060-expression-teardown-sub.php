<?php
$x = symengine_symbol('x');
$y = symengine_symbol('y');
$expr1 = symengine_add($x, $y);
$expr2 = symengine_mul($x, symengine_integer(2));
$expr3 = symengine_pow($x, symengine_integer(3));
$expr4 = symengine_mul(symengine_integer(-1), symengine_add(symengine_mul(symengine_integer(-1), $x), $y));
$expr5 = symengine_mul($expr1, $expr3);

echo "expr1: ", symengine_str($expr1), "\n";
echo "expr2: ", symengine_str($expr2), "\n";
echo "expr3: ", symengine_str($expr3), "\n";
echo "expr4: ", symengine_str($expr4), "\n";
echo "expr5: ", symengine_str($expr5), "\n";

foreach ([
    'expr1' => $expr1,
    'expr2' => $expr2,
    'expr3' => $expr3,
    'expr4' => $expr4,
    'expr5' => $expr5,
] as $name => $value) {
    if (!$value->isExternalOwned()) {
        fwrite(STDERR, "$name should be external-owned\n");
        exit(2);
    }
}

$sum = symengine_add($expr1, $expr2);
if (symengine_str($sum) !== '3*x + y') {
    fwrite(STDERR, 'sum = ' . symengine_str($sum) . "\n");
    exit(2);
}

$diff = symengine_add($expr5, symengine_mul(symengine_integer(-1), symengine_mul($expr1, $expr3)));
if (symengine_str($diff) !== '0') {
    fwrite(STDERR, 'diff = ' . symengine_str($diff) . "\n");
    exit(2);
}

echo "OK: expression teardown test completed\n";
