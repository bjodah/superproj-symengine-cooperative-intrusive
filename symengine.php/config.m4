PHP_ARG_ENABLE(symengine, whether to enable SymEngine support,
[  --enable-symengine         Enable SymEngine extension])

if test "$PHP_SYMENGINE" != "no"; then
  PHP_REQUIRE_CXX()

  SEARCH_PATH="/usr/local /usr /opt/local /opt/homebrew"
  if test -n "$SYMENGINE_PREFIX"; then
    SEARCH_PATH="$SYMENGINE_PREFIX $SEARCH_PATH"
  fi
  SYMENGINE_DIR=""
  SYMENGINE_LIBDIR=""
  for dir in $SEARCH_PATH; do
    if test -f "$dir/include/symengine/symengine_rcp.h"; then
      SYMENGINE_DIR=$dir
      if test -d "$dir/lib64"; then
        SYMENGINE_LIBDIR="$dir/lib64"
      else
        SYMENGINE_LIBDIR="$dir/lib"
      fi
      break
    fi
  done

  if test -z "$SYMENGINE_DIR"; then
    AC_MSG_ERROR([SymEngine not found. Please install SymEngine with cooperative_intrusive backend.])
  fi

  PHP_ADD_INCLUDE($SYMENGINE_DIR/include)
  if test -n "$Boost_ROOT" && test -f "$Boost_ROOT/include/boost/multiprecision/cpp_int.hpp"; then
    PHP_ADD_INCLUDE($Boost_ROOT/include)
  fi
  PHP_ADD_LIBRARY_WITH_PATH(symengine, $SYMENGINE_LIBDIR, SYMENGINE_SHARED_LIBADD)
  PHP_ADD_LIBRARY(stdc++, 1, SYMENGINE_SHARED_LIBADD)

  PHP_SUBST(SYMENGINE_SHARED_LIBADD)

  AC_LANG_PUSH([C++])
  symengine_saved_CPPFLAGS="$CPPFLAGS"
  symengine_saved_LDFLAGS="$LDFLAGS"
  symengine_saved_LIBS="$LIBS"
  CPPFLAGS="$CPPFLAGS -I$SYMENGINE_DIR/include"
  if test -n "$Boost_ROOT" && test -f "$Boost_ROOT/include/boost/multiprecision/cpp_int.hpp"; then
    CPPFLAGS="$CPPFLAGS -I$Boost_ROOT/include"
  fi
  LDFLAGS="$LDFLAGS -L$SYMENGINE_LIBDIR"
  LIBS="$LIBS -lsymengine"

  AC_MSG_CHECKING([whether SymEngine uses cooperative_intrusive RCP])
  AC_LINK_IFELSE([
    AC_LANG_SOURCE([[#include <symengine/symengine_rcp.h>
    #if !defined(WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP)
    #error cooperative_intrusive backend required
    #endif
    int main() {
        SymEngine::cooperative_intrusive_init(nullptr, nullptr);
        return 0;
    }]])
  ], [
    AC_MSG_RESULT([yes])
  ], [
    AC_MSG_FAILURE([SymEngine with SYMENGINE_RCP_BACKEND=cooperative_intrusive is required])
  ])

  CPPFLAGS="$symengine_saved_CPPFLAGS"
  LDFLAGS="$symengine_saved_LDFLAGS"
  LIBS="$symengine_saved_LIBS"
  AC_LANG_POP([C++])

  AC_DEFINE(HAVE_SYMENGINE, 1, [Whether SymEngine is available])

  if test "x$SYMENGINE_PHP_DEBUG_HELPERS" = "x1" || test "x$SYMENGINE_VARIANT" = "xdebug"; then
    AC_DEFINE(SYMENGINE_PHP_DEBUG_HELPERS, 1, [Whether SymEngine PHP debug ownership helpers are enabled])
  fi

  dnl Generated glue goes to the build directory ($abs_builddir/generated),
  dnl never into the tracked source tree. phpize builds are usually in-tree,
  dnl so symengine.php/.gitignore ignores /generated/ for that case. A
  dnl standalone wrapper checkout supplies BINDING_CODEGEN_ROOT explicitly;
  dnl the normal super-project layout is discovered from the source parent.
  AC_ARG_VAR([BINDING_CODEGEN_ROOT], [super-project root containing binding-spec/])
  AC_ARG_VAR([BINDING_CODEGEN_PYTHON], [Python interpreter for shared binding generation])
  if test -z "$BINDING_CODEGEN_ROOT"; then
    BINDING_CODEGEN_ROOT=`cd "$srcdir/.." 2>/dev/null && pwd || true`
  fi
  if test ! -f "$BINDING_CODEGEN_ROOT/binding-spec/api.yaml"; then
    AC_MSG_ERROR([binding-spec/api.yaml not found; set BINDING_CODEGEN_ROOT to the super-project root])
  fi
  if test -z "$BINDING_CODEGEN_PYTHON"; then
    BINDING_CODEGEN_PYTHON=python3
  fi
  SYMENGINE_GENERATED_DIR="$abs_builddir/generated"
  PHP_ADD_BUILD_DIR([$SYMENGINE_GENERATED_DIR], [1])
  AC_MSG_NOTICE([generating shared PHP binding glue into $SYMENGINE_GENERATED_DIR])
  PYTHONPATH="$BINDING_CODEGEN_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    "$BINDING_CODEGEN_PYTHON" -m tools.binding_codegen generate \
      --language php --output "$SYMENGINE_GENERATED_DIR" \
      || AC_MSG_ERROR([shared PHP binding generation failed])

  dnl src/symengine_php.cpp includes the generated .inc files by bare name.
  PHP_ADD_INCLUDE([$SYMENGINE_GENERATED_DIR])

  dnl The same generation call emits shared_cases.phpt; give it a numbered name
  dnl so run-tests.php orders it with the hand-written tests/*.phpt suite.
  cp "$SYMENGINE_GENERATED_DIR/shared_cases.phpt" \
     "$SYMENGINE_GENERATED_DIR/090-shared-cases.phpt" \
    || AC_MSG_ERROR([naming generated shared_cases.phpt failed])

  PHP_NEW_EXTENSION(symengine, src/module.cpp src/symengine_php.cpp src/cooperative_hooks.cpp, $ext_shared, , -std=c++17)

  dnl Objects for src/*.cpp are written to $abs_builddir/src, which only exists
  dnl by accident for the usual in-tree phpize build.
  PHP_ADD_BUILD_DIR([src])
fi
