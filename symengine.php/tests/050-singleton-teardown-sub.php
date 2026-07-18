<?php
/**
 * Subprocess-based singleton teardown test.
 * Creates singleton wrappers and holds them until exit.
 */

$zero = symengine_zero();
$one = symengine_one();
$pi = symengine_pi();
$e = symengine_e();
$two = symengine_two();

echo "zero: ", symengine_str($zero), "\n";
echo "one: ", symengine_str($one), "\n";
echo "pi: ", symengine_str($pi), "\n";
echo "e: ", symengine_str($e), "\n";
echo "two: ", symengine_str($two), "\n";

foreach (['zero' => $zero, 'one' => $one, 'pi' => $pi, 'e' => $e, 'two' => $two] as $name => $value) {
    if (!$value->isExternalOwned()) {
        fwrite(STDERR, "$name should be external-owned\n");
        exit(2);
    }
}

$zero2 = symengine_zero();
if (!$zero->sameObject($zero2)) {
    fwrite(STDERR, "zero identity reuse failed\n");
    exit(2);
}

$pi2 = symengine_pi();
if (!$pi->sameObject($pi2)) {
    fwrite(STDERR, "pi identity reuse failed\n");
    exit(2);
}

$sum = symengine_add($one, $two);
if (symengine_str($sum) !== '3') {
    fwrite(STDERR, 'sum = ' . symengine_str($sum) . "\n");
    exit(2);
}

$pi_plus = symengine_add($pi, $one);
if (symengine_str($pi_plus) !== '1 + pi') {
    fwrite(STDERR, 'pi_plus = ' . symengine_str($pi_plus) . "\n");
    exit(2);
}

echo "OK: singleton teardown test completed\n";
exit(0);
