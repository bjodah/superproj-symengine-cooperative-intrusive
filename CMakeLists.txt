# Super-project CMakeLists.txt
#
# Unified build entry point for SymEngine + nbsymengine bindings.
#
# Usage:
#   cmake -S . -B build -G Ninja \
#         -DSYMENGINE_RCP_BACKEND=cooperative_intrusive
#   cmake --build build

cmake_minimum_required(VERSION 3.18...4.2.0)
project(symengine_superproject LANGUAGES C CXX)

enable_testing()

if (NOT nanobind_DIR)
    set(SYMENGINE_VENDORED_NANOBIND_DIR
        "${CMAKE_SOURCE_DIR}/nbsymengine/external/nanobind/cmake")
    if (EXISTS "${SYMENGINE_VENDORED_NANOBIND_DIR}/nanobind-config.cmake")
        set(nanobind_DIR "${SYMENGINE_VENDORED_NANOBIND_DIR}" CACHE PATH
            "Path to the vendored nanobind CMake package")
    endif ()
endif ()

# --- SymEngine C++ library --------------------------------------------------
add_subdirectory(symengine)

# --- Java JNI bindings (symengine.java) ------------------------------------
option(BUILD_JAVA_JNI
       "Build Java JNI bindings (requires the ordinary thread-safe symengine RCP backend)" OFF)

if (BUILD_JAVA_JNI)
    if (NOT SYMENGINE_RCP_BACKEND STREQUAL "symengine")
        message(FATAL_ERROR
            "BUILD_JAVA_JNI requires SYMENGINE_RCP_BACKEND=symengine")
    endif ()
    if (NOT WITH_SYMENGINE_THREAD_SAFE)
        message(FATAL_ERROR
            "BUILD_JAVA_JNI requires WITH_SYMENGINE_THREAD_SAFE=ON")
    endif ()
    add_subdirectory(symengine.java)
endif ()

# --- Python nanobind bindings (nbsymengine) ---------------------------------
option(BUILD_PYTHON_NANOBIND
       "Build Python nanobind bindings (requires cooperative_intrusive backend)" OFF)

if (BUILD_PYTHON_NANOBIND)
    if (NOT SYMENGINE_RCP_BACKEND STREQUAL "cooperative_intrusive")
        message(FATAL_ERROR
            "BUILD_PYTHON_NANOBIND requires SYMENGINE_RCP_BACKEND=cooperative_intrusive")
    endif ()
    add_subdirectory(nbsymengine)
endif ()

# --- Perl XS bindings (symengine.pl) ---------------------------------------
option(BUILD_PERL_XS
       "Build Perl XS bindings (currently validated with cooperative_intrusive backend)" OFF)

if (BUILD_PERL_XS)
    if (NOT SYMENGINE_RCP_BACKEND STREQUAL "cooperative_intrusive")
        message(FATAL_ERROR
            "BUILD_PERL_XS currently requires SYMENGINE_RCP_BACKEND=cooperative_intrusive")
    endif ()

    find_package(Perl REQUIRED)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    find_program(SYMENGINE_PERL_MAKE_EXECUTABLE
        NAMES gmake make
        REQUIRED)

    set(SYMENGINE_PERL_SOURCE_DIR "${CMAKE_SOURCE_DIR}/symengine.pl")
    set(SYMENGINE_PERL_BUILD_DIR "${CMAKE_BINARY_DIR}/symengine.pl")
    set(SYMENGINE_PERL_MAKEFILE "${SYMENGINE_PERL_BUILD_DIR}/Makefile")
    set(SYMENGINE_PERL_BLIB "${SYMENGINE_PERL_BUILD_DIR}/blib")
    set(SYMENGINE_BINDING_CODEGEN_DIR "${CMAKE_BINARY_DIR}/binding-generated")
    set(SYMENGINE_PERL_GENERATED_DIR "${SYMENGINE_BINDING_CODEGEN_DIR}/perl")
    set(SYMENGINE_PERL_GENERATED_XS "${SYMENGINE_PERL_BUILD_DIR}/xs/SymEngine.generated.xs.inc")
    set(SYMENGINE_PERL_GENERATED_SHARED_TEST "${SYMENGINE_PERL_BUILD_DIR}/t/07-shared-cases.t")

    add_custom_command(
        OUTPUT "${SYMENGINE_PERL_MAKEFILE}" "${SYMENGINE_PERL_GENERATED_XS}" "${SYMENGINE_PERL_GENERATED_SHARED_TEST}"
        COMMAND "${CMAKE_COMMAND}" -E rm -rf "${SYMENGINE_PERL_BUILD_DIR}"
        COMMAND "${CMAKE_COMMAND}" -E copy_directory
                "${SYMENGINE_PERL_SOURCE_DIR}"
                "${SYMENGINE_PERL_BUILD_DIR}"
        COMMAND "${CMAKE_COMMAND}" -E env
                "PYTHONPATH=${CMAKE_SOURCE_DIR}"
                "${Python3_EXECUTABLE}" -m tools.binding_codegen generate
                --language perl --output "${SYMENGINE_PERL_GENERATED_DIR}"
        COMMAND "${CMAKE_COMMAND}" -E copy
                "${SYMENGINE_PERL_GENERATED_DIR}/SymEngine.generated.xs.inc"
                "${SYMENGINE_PERL_GENERATED_XS}"
        COMMAND "${CMAKE_COMMAND}" -E copy
                "${SYMENGINE_PERL_GENERATED_DIR}/shared_cases.t"
                "${SYMENGINE_PERL_GENERATED_SHARED_TEST}"
        COMMAND "${CMAKE_COMMAND}" -E chdir "${SYMENGINE_PERL_BUILD_DIR}"
                "${CMAKE_COMMAND}" -E env
                "SYMENGINE_SOURCE_DIR=${CMAKE_SOURCE_DIR}/symengine"
                "SYMENGINE_BUILD_DIR=${CMAKE_BINARY_DIR}/symengine"
                "${PERL_EXECUTABLE}" Makefile.PL
        WORKING_DIRECTORY "${CMAKE_BINARY_DIR}"
        DEPENDS symengine
                "${SYMENGINE_PERL_SOURCE_DIR}/Makefile.PL"
                "${SYMENGINE_PERL_SOURCE_DIR}/lib/SymEngine.pm"
                "${SYMENGINE_PERL_SOURCE_DIR}/xs/SymEngine.xs"
                "${SYMENGINE_PERL_SOURCE_DIR}/xs/perl_symengine.cpp"
                "${SYMENGINE_PERL_SOURCE_DIR}/xs/perl_symengine.h"
                "${CMAKE_SOURCE_DIR}/binding-spec/api.yaml"
                "${CMAKE_SOURCE_DIR}/binding-spec/schema.json"
                "${CMAKE_SOURCE_DIR}/binding-spec/test-cases.yaml"
                "${CMAKE_SOURCE_DIR}/binding-spec/test-cases.schema.json"
                "${CMAKE_SOURCE_DIR}/tools/binding_codegen/__main__.py"
                "${CMAKE_SOURCE_DIR}/tools/binding_codegen/model.py"
                "${CMAKE_SOURCE_DIR}/tools/binding_codegen/render_perl.py"
                "${CMAKE_SOURCE_DIR}/tools/binding_codegen/render_tests.py"
                "${CMAKE_SOURCE_DIR}/tools/binding_codegen/test_cases.py"
        COMMENT "Configuring symengine.pl Perl XS extension"
        VERBATIM)

    add_custom_command(
        OUTPUT "${SYMENGINE_PERL_BLIB}"
        COMMAND "${SYMENGINE_PERL_MAKE_EXECUTABLE}"
        WORKING_DIRECTORY "${SYMENGINE_PERL_BUILD_DIR}"
        DEPENDS "${SYMENGINE_PERL_MAKEFILE}" symengine
        COMMENT "Building symengine.pl Perl XS extension"
        VERBATIM)

    add_custom_target(perl_xs ALL
        DEPENDS "${SYMENGINE_PERL_BLIB}")

    add_test(
        NAME perl_symengine
        COMMAND "${SYMENGINE_PERL_MAKE_EXECUTABLE}" test
        WORKING_DIRECTORY "${SYMENGINE_PERL_BUILD_DIR}")
    set_tests_properties(perl_symengine PROPERTIES
        DEPENDS perl_xs
        ENVIRONMENT "LD_LIBRARY_PATH=${CMAKE_BINARY_DIR}/symengine/symengine:$ENV{LD_LIBRARY_PATH}")
endif ()
