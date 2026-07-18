--TEST--
Expression teardown: subprocess holding non-singleton expressions until exit
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
require __DIR__ . '/support/subprocess.php';

$script = __DIR__ . '/060-expression-teardown-sub.php';
$ext = realpath(__DIR__ . '/../modules/symengine.so');
$ext = $ext !== false ? $ext : (ini_get('extension_dir') . '/symengine.so');
$result = symengine_run_subprocess($script, 10, $ext);
$output = preg_split('/\r?\n/', rtrim($result['stdout']));
$stderr = preg_split('/\r?\n/', rtrim($result['stderr']));
$exitCode = $result['exit_code'];

echo "Exit code: $exitCode\n";
echo "Output:\n";
foreach ($output as $line) {
    if ($line === '') {
        continue;
    }
    echo "  $line\n";
}

if ($result['timed_out']) {
    echo "Timed out: true\n";
    if ($result['stderr'] !== '') {
        echo "Stderr:\n";
        foreach ($stderr as $line) {
            if ($line === '') {
                continue;
            }
            echo "  $line\n";
        }
    }
    exit(1);
}

if ($exitCode !== 0) {
    if ($result['stderr'] !== '') {
        echo "Stderr:\n";
        foreach ($stderr as $line) {
            if ($line === '') {
                continue;
            }
            echo "  $line\n";
        }
    }
    echo "FAIL: subprocess exited with code $exitCode\n";
    exit(1);
}
echo "PASS: clean exit\n";
?>
--EXPECT--
Exit code: 0
Output:
  expr1: x + y
  expr2: 2*x
  expr3: x**3
  expr4: -(-x + y)
  expr5: x**3*(x + y)
  OK: expression teardown test completed
PASS: clean exit
