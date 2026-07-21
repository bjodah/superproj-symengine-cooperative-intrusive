#!/bin/bash
# .ci/ci-common.sh - Shared CI configuration and helper functions
set -euo pipefail

SUPERPROJECT_ROOT=$(realpath "$(dirname "${BASH_SOURCE[0]}")/..")
export SUPERPROJECT_ROOT
CI_ORIGINAL_PATH="${CI_ORIGINAL_PATH:-$PATH}"
export CI_ORIGINAL_PATH

# Foreign-runtime toolchains are installed alongside the Python variants. Keep
# their locations explicit so wrapper lanes never accidentally select a
# host-provided ABI-incompatible development installation.
export CI_PHP_DEBUG_ROOT="${CI_PHP_DEBUG_ROOT:-/opt-6/php-8.5.7-debug}"
export CI_PERL_DEBUG_ROOT="${CI_PERL_DEBUG_ROOT:-/opt-6/perl-v5.43.11-debug}"
# The JDK 21 installation in /opt-6 is a runtime-only distribution. Use the
# complete OpenJDK toolchain for CMake's UseJava support.
export CI_JAVA_HOME="${CI_JAVA_HOME:-/opt-4/miniforge3/lib/jvm}"

# Resolve Boost path if present
export Boost_ROOT=$(compgen -G "${Boost_ROOT:-'/path-not-provided'}" || true)

# Toolchain mechanics (compilers, sanitizer flags, instrumented stdlib and
# sanitizer-python resolution) are owned by the triceratops CI image, staged
# under /opt-N (from bjodah-containers/triceratops/env-N/env-*.sh). Point
# CI_TOOLCHAIN_ENV_DIR at a bind-mounted checkout of that env-N directory to
# iterate on those scripts without rebuilding the image (see
# .ci/host-local-test-run.sh).
if [[ -z "${CI_TOOLCHAIN_ENV_DIR:-}" ]]; then
    _ci_toolchain_probe=$(compgen -G "/opt*/env-asan.sh" | sort -rV | head -1 || true)
    CI_TOOLCHAIN_ENV_DIR="${_ci_toolchain_probe%/*}"
    unset _ci_toolchain_probe
fi
export CI_TOOLCHAIN_ENV_DIR

# Resolve the default Python installation paths
export CI_DEFAULT_PYTHON_ROOT=/opt-3/cpython-v3.13-apt-deb
export CI_DEFAULT_PYTHON=/opt-3/cpython-v3.13-apt-deb/bin/python
export CI_DEFAULT_PIP=/opt-3/cpython-v3.13-apt-deb/bin/pip

# Resolve the TSAN Python installation paths
if [[ -e "${CI_TOOLCHAIN_ENV_DIR}/env-python-tsan.sh" ]]; then
    source "${CI_TOOLCHAIN_ENV_DIR}/env-python-tsan.sh"
    export CI_TSAN_PYTHON_ROOT="${OPT_TSAN_PYTHON_ROOT}"
    export CI_TSAN_PYTHON="${OPT_TSAN_PYTHON}"
    export CI_TSAN_PIP="${OPT_TSAN_PIP}"
else
    export CI_TSAN_PYTHON_ROOT=""
    export CI_TSAN_PYTHON=""
    export CI_TSAN_PIP=""
fi

# Resolve the ASAN Python installation paths. The image's env-python-asan.sh
# also resolves LIBCXX_ASAN_ROOT and stages the wrapper interpreter that
# LD_PRELOADs the instrumented libc++abi (see that script for the
# __cxa_throw rationale).
if [[ -e "${CI_TOOLCHAIN_ENV_DIR}/env-python-asan.sh" ]]; then
    source "${CI_TOOLCHAIN_ENV_DIR}/env-python-asan.sh"
    export CI_ASAN_PYTHON_ROOT="${OPT_ASAN_PYTHON_ROOT}"
    export CI_ASAN_PYTHON_REAL="${OPT_ASAN_PYTHON_REAL}"
    export CI_ASAN_PYTHON="${OPT_ASAN_PYTHON}"
    export CI_ASAN_PIP="${OPT_ASAN_PIP}"
else
    export CI_ASAN_PYTHON_ROOT=""
    export CI_ASAN_PYTHON=""
    export CI_ASAN_PYTHON_REAL=""
    export CI_ASAN_PIP=""
fi

# Select the active Python toolchain
ci_use_python_toolchain() {
    local target=$1
    if [[ "$target" == "default" ]]; then
        export CI_PYTHON_ROOT="$CI_DEFAULT_PYTHON_ROOT"
        export CI_PYTHON="$CI_DEFAULT_PYTHON"
        export CI_PIP="$CI_DEFAULT_PIP"
    elif [[ "$target" == "tsan" ]]; then
        export CI_PYTHON_ROOT="$CI_TSAN_PYTHON_ROOT"
        export CI_PYTHON="$CI_TSAN_PYTHON"
        export CI_PIP="$CI_TSAN_PIP"
    elif [[ "$target" == "asan" ]]; then
        export CI_PYTHON_ROOT="$CI_ASAN_PYTHON_ROOT"
        export CI_PYTHON="$CI_ASAN_PYTHON"
        export CI_PIP="$CI_ASAN_PIP"
    else
        echo "Unknown python toolchain: $target" >&2
        return 1
    fi
    export PATH="${CI_PYTHON_ROOT}/bin:${CI_ORIGINAL_PATH}"
}

ci_use_php_toolchain() {
    if [[ ! -x "${CI_PHP_DEBUG_ROOT}/bin/phpize"
          || ! -x "${CI_PHP_DEBUG_ROOT}/bin/php-config" ]]; then
        echo "PHP development toolchain is missing at ${CI_PHP_DEBUG_ROOT}" >&2
        return 1
    fi
    export PATH="${CI_PHP_DEBUG_ROOT}/bin:${PATH}"
}

ci_use_perl_toolchain() {
    if [[ ! -x "${CI_PERL_DEBUG_ROOT}/bin/perl" ]]; then
        echo "Perl toolchain is missing at ${CI_PERL_DEBUG_ROOT}" >&2
        return 1
    fi
    export CI_PERL_EXECUTABLE="${CI_PERL_DEBUG_ROOT}/bin/perl"
}

ci_use_java_toolchain() {
    if [[ ! -x "${CI_JAVA_HOME}/bin/java" || ! -x "${CI_JAVA_HOME}/bin/javac" ]]; then
        echo "JDK is missing at ${CI_JAVA_HOME}" >&2
        return 1
    fi
    export JAVA_HOME="${CI_JAVA_HOME}"
    export PATH="${JAVA_HOME}/bin:${PATH}"
}

ci_ensure_python_toolchain() {
    if [[ -n "${CI_PYTHON:-}" && -n "${CI_PIP:-}" && -n "${CI_PYTHON_ROOT:-}" ]]; then
        export PATH="${CI_PYTHON_ROOT}/bin:${CI_ORIGINAL_PATH}"
        return 0
    fi

    if [[ "${SYMENGINE_VARIANT:-}" == "tsan" ]]; then
        ci_use_python_toolchain tsan
    elif [[ "${SYMENGINE_VARIANT:-}" == "asan" ]]; then
        ci_use_python_toolchain asan
    else
        ci_use_python_toolchain default
    fi
}

ci_pip() {
    ci_ensure_python_toolchain
    local python_exe="$CI_PYTHON"
    if [[ -n "${CI_ASAN_PYTHON_REAL:-}" && "$CI_PYTHON" == "${CI_ASAN_PYTHON:-}" ]]; then
        python_exe="$CI_ASAN_PYTHON_REAL"
    fi
    "$python_exe" -m pip "$@"
}

ci_set_tsan_prefix() {
    if [[ "${SYMENGINE_VARIANT:-}" == "tsan" ]]; then
        export TSAN_PREFIX="setarch $(uname -m) -R"
    else
        export TSAN_PREFIX=""
    fi
}

# Export compiler/linker flags for a given variant
ci_set_variant_flags() {
    local variant=$1
    local user_cmake_args="${CMAKE_ARGS:-}"

    ci_set_tsan_prefix
    
    case "$variant" in
        release)
            export CXXFLAGS="-std=c++20"
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Release -DWITH_BFD=OFF -DWITH_LLVM=ON -DINTEGER_CLASS=gmp -DWITH_SYMENGINE_RCP=ON ${user_cmake_args}"
            ;;
        debug)
            export CXXFLAGS="-Og -g -ggdb3 -std=c++20 -fsized-deallocation"
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=ON -DINTEGER_CLASS=boostmp ${user_cmake_args}"
            ;;
        glibcxxdbg)
            source "${CI_TOOLCHAIN_ENV_DIR}/env-glibcxxdbg.sh"
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=OFF -DINTEGER_CLASS=boostmp ${user_cmake_args}"
            ;;
        cxx14)
            # Keep a pre-C++17 core lane: cooperative hook pointer aliases
            # must remain parseable by supported C++11/C++14 consumers.
            export CXXFLAGS="-std=c++14"
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=OFF -DINTEGER_CLASS=boostmp ${user_cmake_args}"
            ;;
        tsan)
            # Compose from the image's fragments instead of taking its full
            # default CXXFLAGS, to keep -std/-ggdb3/-fsized-deallocation.
            # Building against the TSan-instrumented libc++ (rather than an
            # uninstrumented libstdc++) lets TSan see synchronization inside
            # the standard library.
            source "${CI_TOOLCHAIN_ENV_DIR}/env-tsan.sh"
            export CXXFLAGS="-std=c++20 -O1 -g -ggdb3 -fsized-deallocation ${OPT_TSAN_CXXFLAGS} ${OPT_TSAN_STDLIB_CXXFLAGS}"
            export LDFLAGS="${OPT_TSAN_LDFLAGS}"
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=OFF -DINTEGER_CLASS=boostmp -DHAVE_GCC_ABI_DEMANGLE=no ${user_cmake_args}"
            ;;
        asan)
            source "${CI_TOOLCHAIN_ENV_DIR}/env-asan.sh"
            test -d "${LIBCXX_ASAN_ROOT}"
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=OFF -DINTEGER_CLASS=boostmp -DWITH_SYMENGINE_RCP=ON -DHAVE_GCC_ABI_DEMANGLE=no ${user_cmake_args}"
            local symbolizer_path
            symbolizer_path=$(command -v llvm-symbolizer || true)
            if [[ -n "$symbolizer_path" ]]; then
                export ASAN_OPTIONS="symbolize=1:detect_leaks=1:check_initialization_order=1:external_symbolizer_path=$symbolizer_path"
            else
                export ASAN_OPTIONS="symbolize=1:detect_leaks=1:check_initialization_order=1"
            fi
            export LSAN_OPTIONS="suppressions=${SUPERPROJECT_ROOT}/.ci/lsan_suppressions.txt"
            ;;
        msan)
            # env-msan.sh appends the sanitizer/stdlib flags to pre-seeded
            # base flags (and errors out if the instrumented libc++ is absent).
            export CXXFLAGS="-std=c++20"
            export CFLAGS=""
            export LDFLAGS=""
            source "${CI_TOOLCHAIN_ENV_DIR}/env-msan.sh"
            export CMAKE_ARGS="-DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=OFF -DINTEGER_CLASS=boostmp -DWITH_SYMENGINE_RCP=ON  -DHAVE_GCC_ABI_DEMANGLE=no ${user_cmake_args}"
            ;;
        tcmalloc)
            export CXXFLAGS="-std=c++20"
            export CC="${CLANG_CC:-clang}"
            export CXX="${CLANG_CXX:-clang++}"
            export CCACHE_CPP2=true
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Release -DWITH_BFD=OFF -DWITH_LLVM=ON -DWITH_TCMALLOC=ON ${user_cmake_args}"
            ;;
        *)
            echo "Unknown variant: $variant" >&2
            return 1
            ;;
    esac

    # Configure Boost prefix path if INTEGER_CLASS=boostmp is used
    if [[ "$CMAKE_ARGS" == *INTEGER_CLASS=boostmp* ]]; then
        if [[ ${Boost_ROOT:-""} != "" ]]; then
            export CMAKE_PREFIX_PATH="${Boost_ROOT}:${CMAKE_PREFIX_PATH:-}"
        fi
    fi
}

# Apply RCP choice backend settings
ci_apply_rcp_choice() {
    if [[ "${SYMENGINE_RCP_CHOICE:-}" == "cooperative_intrusive" ]]; then
        ci_ensure_python_toolchain
        # Remove -DWITH_SYMENGINE_RCP=ON if present in CMAKE_ARGS
        CMAKE_ARGS=$(echo " ${CMAKE_ARGS:-} " | sed 's/ -DWITH_SYMENGINE_RCP=ON / /g' | sed 's/^ *//;s/ *$//')
        CMAKE_ARGS="${CMAKE_ARGS} -DSYMENGINE_RCP_BACKEND=cooperative_intrusive"
        export CMAKE_ARGS
        
        # nanobind and Litgen are needed only when this configure invocation
        # actually enables the nbsymengine target. Keeping them out of core
        # SymEngine builds prevents CMake's unused-nanobind_DIR warning.
        if [[ " ${CMAKE_ARGS} " == *" -DBUILD_PYTHON_NANOBIND=ON "* ]]; then
            local nanobind_floor=2.13.0
            local nanobind_version
            nanobind_version=$("$CI_PYTHON" -m nanobind --version)
            if [[ "$(printf '%s\n%s\n' "$nanobind_floor" "$nanobind_version" | sort -V | head -n 1)" != "$nanobind_floor" ]]; then
                echo "nanobind ${nanobind_floor} or newer is required; found ${nanobind_version}" >&2
                return 1
            fi
            if [[ -z "${NB_CMAKE_DIR:-}" ]]; then
                export NB_CMAKE_DIR=$("$CI_PYTHON" -m nanobind --cmake_dir)
            fi
            export LITGEN_ROOT="${LITGEN_ROOT:-/opt-6/litgen-6085aaa}"
            export SYMENGINE_LITGEN_DIR="${SYMENGINE_LITGEN_DIR:-${LITGEN_ROOT}/src}"
            if [[ ! -d "${SYMENGINE_LITGEN_DIR}" ]]; then
                echo "Litgen not found at ${SYMENGINE_LITGEN_DIR}" >&2
                return 1
            fi
            export CMAKE_ARGS="${CMAKE_ARGS} -Dnanobind_DIR=${NB_CMAKE_DIR} -DSYMENGINE_LITGEN_DIR=${SYMENGINE_LITGEN_DIR}"
        fi
    fi
}
