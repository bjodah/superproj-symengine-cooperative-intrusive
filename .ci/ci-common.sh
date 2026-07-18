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

# Resolve the default Python installation paths
export CI_DEFAULT_PYTHON_ROOT=/opt-3/cpython-v3.13-apt-deb
export CI_DEFAULT_PYTHON=/opt-3/cpython-v3.13-apt-deb/bin/python
export CI_DEFAULT_PIP=/opt-3/cpython-v3.13-apt-deb/bin/pip

# Resolve the TSAN Python installation paths
export CI_TSAN_PYTHON_ROOT=/opt-3/cpython-v3.14.4-tsan
export CI_TSAN_PYTHON=/opt-3/cpython-v3.14.4-tsan/bin/python3.14
export CI_TSAN_PIP=/opt-3/cpython-v3.14.4-tsan/bin/pip3.14

# Resolve the ASAN C++ library installation paths
export LIBCXX_ASAN_ROOT="${LIBCXX_ASAN_ROOT:-$(compgen -G "/opt*/libcxx*-asan/" | sort -rV | head -1 || true)}"
export LIBCXX_ASAN_ROOT="${LIBCXX_ASAN_ROOT%/}"

# Resolve the ASAN Python installation paths
export CI_ASAN_PYTHON_ROOT="${CI_ASAN_PYTHON_ROOT:-$(compgen -G "/opt*/cpython*-asan/" | sort -rV | head -1 || true)}"
export CI_ASAN_PYTHON_ROOT="${CI_ASAN_PYTHON_ROOT%/}"
if [[ -n "${CI_ASAN_PYTHON_ROOT}" ]]; then
    export CI_ASAN_PYTHON_REAL="$(compgen -G "${CI_ASAN_PYTHON_ROOT}/bin/python3.*" | grep -E '/python3\.[0-9]+$' | sort -rV | head -1 || true)"
    export CI_ASAN_PIP="$(compgen -G "${CI_ASAN_PYTHON_ROOT}/bin/pip3.*" | sort -rV | head -1 || true)"
    export CI_ASAN_SITE_ROOT=/tmp/asan-python-path
    export CI_ASAN_PYTHON=/tmp/python-asan-wrapper
    mkdir -p "${CI_ASAN_SITE_ROOT}"
    cat <<'EOF' > "${CI_ASAN_SITE_ROOT}/sitecustomize.py"
import os

libcxx_root = os.environ.get("CI_ASAN_LIBCXX_ROOT")
if libcxx_root:
    asan_lib_dir = os.path.join(libcxx_root, "lib")
    ld_library_path = os.environ.get("LD_LIBRARY_PATH")
    if ld_library_path:
        filtered = [p for p in ld_library_path.split(":") if os.path.normpath(p) != os.path.normpath(asan_lib_dir)]
        if filtered:
            os.environ["LD_LIBRARY_PATH"] = ":".join(filtered)
        else:
            os.environ.pop("LD_LIBRARY_PATH", None)

    preload_path = os.path.join(asan_lib_dir, "libc++abi.so")
    ld_preload = os.environ.get("LD_PRELOAD")
    if ld_preload:
        filtered = [p for p in ld_preload.split(":") if os.path.normpath(p) != os.path.normpath(preload_path)]
        if filtered:
            os.environ["LD_PRELOAD"] = ":".join(filtered)
        else:
            os.environ.pop("LD_PRELOAD", None)
EOF
    cat <<EOF > "${CI_ASAN_PYTHON}"
#!/bin/sh
export CI_ASAN_LIBCXX_ROOT="${LIBCXX_ASAN_ROOT}"
export LD_LIBRARY_PATH="${LIBCXX_ASAN_ROOT}/lib:\${LD_LIBRARY_PATH:-}"
export LD_PRELOAD="${LIBCXX_ASAN_ROOT}/lib/libc++abi.so\${LD_PRELOAD:+:\$LD_PRELOAD}"
export PYTHONPATH="${CI_ASAN_SITE_ROOT}:\${PYTHONPATH:-}"
exec "${CI_ASAN_PYTHON_REAL}" "\$@"
EOF
    chmod +x "${CI_ASAN_PYTHON}"
else
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
            export CXXFLAGS="-Og -g -ggdb3 -std=c++20 -D_GLIBCXX_DEBUG -D_GLIBCXX_DEBUG_PEDANTIC -D_GLIBCXX_ASSERTIONS -D_GLIBCXX_SANITIZE_VECTOR -fsized-deallocation"
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=OFF -DINTEGER_CLASS=boostmp ${user_cmake_args}"
            ;;
        tsan)
            export CXXFLAGS="-std=c++20 -fsanitize=thread -O1 -g -ggdb3 -fsized-deallocation"
            export LDFLAGS="-fsanitize=thread ${LDFLAGS:-}"
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=OFF -DINTEGER_CLASS=boostmp -DHAVE_GCC_ABI_DEMANGLE=no ${user_cmake_args}"
            export CC="${CLANG_CC:-clang}"
            export CXX="${CLANG_CXX:-clang++}"
            export CCACHE_CPP2=true
            ;;
        asan)
            test -d "${LIBCXX_ASAN_ROOT}"
            export CXXFLAGS="-std=c++20 -fsanitize=address -O1 -g -fno-omit-frame-pointer -fno-optimize-sibling-calls -fsized-deallocation -stdlib++-isystem ${LIBCXX_ASAN_ROOT}/include/c++/v1 -ferror-limit=5"
            export LDFLAGS="-fsanitize=address -Wl,-rpath,${LIBCXX_ASAN_ROOT}/lib -L${LIBCXX_ASAN_ROOT}/lib -lc++ -lc++abi -stdlib=libc++"
            export CMAKE_ARGS="-DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=OFF -DINTEGER_CLASS=boostmp -DWITH_SYMENGINE_RCP=ON -DHAVE_GCC_ABI_DEMANGLE=no ${user_cmake_args}"
            export CC="${CLANG_CC:-clang}"
            export CXX="${CLANG_CXX:-clang++}"
            export CCACHE_CPP2=true
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
            test -d "${LIBCXX_MSAN_ROOT}"
            export CXXFLAGS="-std=c++20 -fsanitize=memory -fsanitize-memory-track-origins=2 -fsanitize-memory-param-retval -fsized-deallocation -stdlib++-isystem ${LIBCXX_MSAN_ROOT}/include/c++/v1 -fno-omit-frame-pointer -fno-optimize-sibling-calls -O1 -glldb"
            export LDFLAGS="-fsanitize=memory -fsanitize-memory-track-origins=2 -Wl,-rpath,${LIBCXX_MSAN_ROOT}/lib -L${LIBCXX_MSAN_ROOT}/lib  -stdlib=libc++ -rtlib=compiler-rt -unwindlib=libunwind -lc++abi"
            export CMAKE_ARGS="-DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_BUILD_TYPE=Debug -DWITH_BFD=OFF -DWITH_LLVM=OFF -DINTEGER_CLASS=boostmp -DWITH_SYMENGINE_RCP=ON  -DHAVE_GCC_ABI_DEMANGLE=no ${user_cmake_args}"
            export CC="${CLANG_CC:-clang}"
            export CXX="${CLANG_CXX:-clang++}"
            export CCACHE_CPP2=true
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
        
        # Ensure nanobind headers are discoverable.
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
        export CMAKE_ARGS="${CMAKE_ARGS} -Dnanobind_DIR=${NB_CMAKE_DIR}"
        
        # Make the pinned in-tree litgen importable
        export PYTHONPATH="${SUPERPROJECT_ROOT}/nbsymengine/external/litgen/src:${PYTHONPATH:-}"
    fi
}
