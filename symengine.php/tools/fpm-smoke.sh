#!/bin/bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    >&2 echo "Usage: $0 <symengine-install-prefix> <symengine-extension-so>"
    exit 1
fi

INSTALL_PREFIX=$1
EXTENSION_SO=$2

PHP_FPM=$(command -v php-fpm8.4 || command -v php-fpm8.3 || command -v php-fpm8.2 || command -v php-fpm || true)
FCGI_CLIENT=$(command -v cgi-fcgi || true)

if [[ -z "$PHP_FPM" ]]; then
    >&2 echo "php-fpm not found on PATH"
    exit 2
fi

if [[ -z "$FCGI_CLIENT" ]]; then
    >&2 echo "cgi-fcgi not found on PATH"
    exit 2
fi

if [[ ! -f "$EXTENSION_SO" ]]; then
    >&2 echo "extension not found: $EXTENSION_SO"
    exit 1
fi

TMP_ROOT=$(mktemp -d /tmp/symengine-fpm.XXXXXX)
FPM_STDOUT="$TMP_ROOT/php-fpm-stdout.log"
FPM_ERROR="$TMP_ROOT/php-fpm-error.log"

dump_logs() {
    local status=$?
    if [[ $status -ne 0 ]]; then
        >&2 echo "FPM smoke failed; artifacts: $TMP_ROOT"
        if [[ -f "$FPM_STDOUT" ]]; then
            >&2 echo "=== php-fpm stdout/stderr ==="
            >&2 sed -n '1,200p' "$FPM_STDOUT"
        fi
        if [[ -f "$FPM_ERROR" ]]; then
            >&2 echo "=== php-fpm error log ==="
            >&2 sed -n '1,200p' "$FPM_ERROR"
        fi
    fi
    if [[ -n "${FPM_PID:-}" ]]; then
        kill "$FPM_PID" 2>/dev/null || true
        wait "$FPM_PID" 2>/dev/null || true
    fi
    if [[ $status -eq 0 ]]; then
        rm -rf "$TMP_ROOT"
    fi
}
trap dump_logs EXIT

DOCROOT="$TMP_ROOT/docroot"
FPM_SOCKET="$TMP_ROOT/php-fpm.sock"
mkdir -p "$DOCROOT"
chmod 755 "$TMP_ROOT" "$DOCROOT"

if [[ "$(id -u)" -eq 0 ]]; then
    if id www-data >/dev/null 2>&1; then
        FPM_USER=www-data
        FPM_GROUP=$(id -gn www-data)
    else
        FPM_USER=nobody
        FPM_GROUP=$(getent group nogroup >/dev/null 2>&1 && echo nogroup || echo nobody)
    fi
    FPM_ROOT_FLAG=()
else
    FPM_USER=$(id -un)
    FPM_GROUP=$(id -gn)
    FPM_ROOT_FLAG=()
fi

cat > "$DOCROOT/singleton.php" <<'PHP'
<?php
$GLOBALS['keep'] = [symengine_zero(), symengine_one(), symengine_pi()];
echo "worker:", getmypid(), "\n";
echo "singleton:", symengine_str($GLOBALS['keep'][2]), "\n";
PHP

cat > "$DOCROOT/expression.php" <<'PHP'
<?php
$x = symengine_symbol('x');
$GLOBALS['expr'] = symengine_add(symengine_pow($x, symengine_integer(2)), symengine_one());
echo "worker:", getmypid(), "\n";
echo "expression:", symengine_str($GLOBALS['expr']), "\n";
PHP

cat > "$DOCROOT/canonical.php" <<'PHP'
<?php
$x = symengine_symbol('x');
$again = symengine_add($x, symengine_zero());
echo "worker:", getmypid(), "\n";
echo "canonical:", ($x === $again ? "same" : "different"), "\n";
PHP

cat > "$TMP_ROOT/php.ini" <<EOF
extension=$EXTENSION_SO
display_errors=1
log_errors=1
error_reporting=E_ALL
cgi.fix_pathinfo=0
EOF

cat > "$TMP_ROOT/php-fpm.conf" <<EOF
[global]
error_log = $FPM_ERROR
daemonize = no

[www]
listen = $FPM_SOCKET
listen.mode = 0666
user = $FPM_USER
group = $FPM_GROUP
pm = static
pm.max_children = 1
clear_env = no
env[LD_LIBRARY_PATH] = ${INSTALL_PREFIX}/lib:${LD_LIBRARY_PATH:-}
php_admin_value[doc_root] = $DOCROOT
catch_workers_output = yes
EOF

export LD_LIBRARY_PATH="${INSTALL_PREFIX}/lib:${LD_LIBRARY_PATH:-}"
"$PHP_FPM" -t -c "$TMP_ROOT/php.ini" -y "$TMP_ROOT/php-fpm.conf" >> "$FPM_STDOUT" 2>&1
"$PHP_FPM" "${FPM_ROOT_FLAG[@]}" -c "$TMP_ROOT/php.ini" -y "$TMP_ROOT/php-fpm.conf" -F > "$FPM_STDOUT" 2>&1 &
FPM_PID=$!

request() {
    local script_name=$1
    SCRIPT_FILENAME="$DOCROOT/$script_name" REQUEST_METHOD=GET "$FCGI_CLIENT" -bind -connect "$FPM_SOCKET"
}

for _ in $(seq 1 100); do
    if ! kill -0 "$FPM_PID" 2>/dev/null; then
        >&2 echo "php-fpm exited before it became ready"
        exit 1
    fi
    if request singleton.php >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done

EXPECTED_WORKER_PID=

assert_request() {
    local script_name=$1
    local expected=$2
    local output
    local worker_pid
    output=$(request "$script_name")
    printf '%s\n' "$output" | tee "$TMP_ROOT/request-$script_name.log"
    if [[ "$output" != *"$expected"* ]]; then
        >&2 echo "unexpected response for $script_name"
        >&2 echo "expected substring: $expected"
        >&2 echo "actual response:"
        >&2 printf '%s\n' "$output"
        exit 1
    fi
    worker_pid=$(printf '%s\n' "$output" | tr -d '\r' | awk -F: '/^worker:/ { print $2; exit }')
    if [[ -z "$worker_pid" ]]; then
        >&2 echo "response for $script_name did not include worker pid"
        exit 1
    fi
    if [[ -z "$EXPECTED_WORKER_PID" ]]; then
        EXPECTED_WORKER_PID=$worker_pid
    elif [[ "$worker_pid" != "$EXPECTED_WORKER_PID" ]]; then
        >&2 echo "FPM worker changed between requests: expected $EXPECTED_WORKER_PID, got $worker_pid"
        exit 1
    fi
}

assert_request singleton.php "singleton:pi"
assert_request expression.php "expression:1 + x**2"
assert_request canonical.php "canonical:same"

kill "$FPM_PID"
wait "$FPM_PID"
FPM_PID=

echo "FPM smoke passed with worker $EXPECTED_WORKER_PID"
