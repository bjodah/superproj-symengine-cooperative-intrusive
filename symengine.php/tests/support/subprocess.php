<?php

function symengine_run_subprocess(string $script, int $timeoutSeconds = 10, ?string $extensionPath = null): array
{
    $ext = $extensionPath;
    if ($ext === null) {
        $siblingModule = realpath(dirname(__DIR__) . '/modules/symengine.so');
        if ($siblingModule !== false) {
            $ext = $siblingModule;
        } else {
            $ext = ini_get('extension_dir') . '/symengine.so';
        }
    }
    $cmd = [PHP_BINARY, '-d', 'extension=' . $ext, $script];

    $spec = [
        0 => ['pipe', 'r'],
        1 => ['pipe', 'w'],
        2 => ['pipe', 'w'],
    ];

    $proc = proc_open($cmd, $spec, $pipes);
    if (!is_resource($proc)) {
        throw new RuntimeException('failed to start subprocess');
    }

    fclose($pipes[0]);
    stream_set_blocking($pipes[1], false);
    stream_set_blocking($pipes[2], false);

    $stdout = '';
    $stderr = '';
    $deadline = microtime(true) + $timeoutSeconds;
    $exitCode = null;
    $timedOut = false;

    while (true) {
        $stdout .= stream_get_contents($pipes[1]);
        $stderr .= stream_get_contents($pipes[2]);

        $status = proc_get_status($proc);
        if (!$status['running']) {
            $exitCode = $status['exitcode'];
            break;
        }

        if (microtime(true) >= $deadline) {
            $timedOut = true;
            proc_terminate($proc);
            break;
        }

        usleep(10000);
    }

    $stdout .= stream_get_contents($pipes[1]);
    $stderr .= stream_get_contents($pipes[2]);
    fclose($pipes[1]);
    fclose($pipes[2]);

    $closeCode = proc_close($proc);
    if ($exitCode === null || $exitCode < 0) {
        $exitCode = $closeCode;
    }

    return [
        'stdout' => $stdout,
        'stderr' => $stderr,
        'exit_code' => $exitCode,
        'timed_out' => $timedOut,
    ];
}
