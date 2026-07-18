--TEST--
Loop teardown: repeated expressions and canonical singleton reuse exit cleanly
--SKIPIF--
<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>
--FILE--
<?php
require __DIR__ . '/support/subprocess.php';

$script = __DIR__ . '/065-loop-teardown-sub.php';
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
  kept: 505
  last: 499 + x499**2
  OK: loop teardown test completed
PASS: clean exit
