<?php

$keep = [];

for ($i = 0; $i < 500; ++$i) {
    $x = symengine_symbol('x' . $i);
    $expr = symengine_add(
        symengine_pow($x, symengine_integer(2)),
        symengine_integer($i)
    );
    $keep[] = $expr;

    if (($i % 100) === 0) {
        $again = symengine_add($x, symengine_zero());
        if (!$x->sameObject($again)) {
            fwrite(STDERR, "canonical identity mismatch at iteration $i\n");
            exit(2);
        }
        $keep[] = $again;
    }
}

echo 'kept: ', count($keep), "\n";
echo 'last: ', symengine_str($keep[count($keep) - 1]), "\n";
echo "OK: loop teardown test completed\n";
