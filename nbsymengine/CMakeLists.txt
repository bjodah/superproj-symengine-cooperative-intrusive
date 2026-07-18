# Unified CMakeLists.txt for nbsymengine
#
# Supports both:
# 1. In-tree build (when added via add_subdirectory(nbsymengine) in the superproject)
# 2. Standalone build (when building a scikit-build-core wheel/pip install)

cmake_minimum_required(VERSION 3.18...4.2.0)
project(nbsymengine LANGUAGES CXX)

if (NOT nanobind_DIR)
    set(NBSYMENGINE_VENDORED_NANOBIND_DIR
        "${CMAKE_CURRENT_SOURCE_DIR}/external/nanobind/cmake")
    if (EXISTS "${NBSYMENGINE_VENDORED_NANOBIND_DIR}/nanobind-config.cmake")
        set(nanobind_DIR "${NBSYMENGINE_VENDORED_NANOBIND_DIR}" CACHE PATH
            "Path to the vendored nanobind CMake package")
    endif ()
endif ()

# --- Detect In-Tree vs Standalone Build ---
set(SYMENGINE_NANOBIND_IN_TREE OFF)
if (TARGET symengine)
    set(SYMENGINE_NANOBIND_IN_TREE ON)
endif ()

# --- Dependencies -----------------------------------------------------------
find_package(Python 3.13 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(Python3 3.13 COMPONENTS Interpreter QUIET)
find_package(nanobind CONFIG REQUIRED)

# --- Standalone: build SymEngine C++ from source ----------------------------
if (NOT SYMENGINE_NANOBIND_IN_TREE)
    # standalone sdist / pip install build mode
    if (NOT SYMENGINE_RCP_BACKEND STREQUAL "cooperative_intrusive")
        message(FATAL_ERROR
            "Standalone build requires -DSYMENGINE_RCP_BACKEND=cooperative_intrusive. "
            "This is normally configured by pyproject.toml cmake.args.")
    endif()

    set(SYMENGINE_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/symengine_src")
    if (NOT EXISTS "${SYMENGINE_SRC_DIR}/CMakeLists.txt")
        message(FATAL_ERROR
            "SymEngine C++ source not found at ${SYMENGINE_SRC_DIR}. "
            "Verify that you are building from a complete sdist tarball.")
    endif()

    set(SYMENGINE_INCLUDE_DIR "${CMAKE_BINARY_DIR}/symengine_build;${SYMENGINE_SRC_DIR}")

    # Disable recursive nanobind build during the C++ sub-build
    set(BUILD_PYTHON_NANOBIND OFF CACHE BOOL "" FORCE)
    add_subdirectory(${SYMENGINE_SRC_DIR} ${CMAKE_BINARY_DIR}/symengine_build)
else ()
    # in-tree build mode
    if (NOT SYMENGINE_RCP_BACKEND STREQUAL "cooperative_intrusive")
        message(FATAL_ERROR
            "nbsymengine requires SYMENGINE_RCP_BACKEND=cooperative_intrusive. "
            "Configure symengine C++ library with -DSYMENGINE_RCP_BACKEND=cooperative_intrusive.")
    endif ()
endif ()

# --- Binding code generation ------------------------------------------------
set(SYMENGINE_NB_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(SYMENGINE_NB_GENERATED_CPP "${SYMENGINE_NB_GENERATED_DIR}/symengine_pydef.cpp")
set(SYMENGINE_NB_GENERATED_PYI "${SYMENGINE_NB_GENERATED_DIR}/symengine.pyi")
set(SYMENGINE_NB_GENERATED
    ${SYMENGINE_NB_GENERATED_CPP}
    ${SYMENGINE_NB_GENERATED_PYI})

set(SYMENGINE_NB_SDIST_GENERATED "${CMAKE_CURRENT_SOURCE_DIR}/generated/symengine_pydef.cpp")

option(SYMENGINE_NB_FORCE_REGENERATE
       "Regenerate bindings with litgen even if pre-generated files exist" OFF)

if (SYMENGINE_NANOBIND_IN_TREE AND (SYMENGINE_NB_FORCE_REGENERATE OR NOT EXISTS "${SYMENGINE_NB_SDIST_GENERATED}"))
    # In-tree: generate bindings using the pinned litgen in this submodule
    set(SYMENGINE_LITGEN_DIR "${CMAKE_CURRENT_SOURCE_DIR}/external/litgen/src")
    if (NOT IS_DIRECTORY "${SYMENGINE_LITGEN_DIR}")
        message(FATAL_ERROR
            "Litgen not found at ${SYMENGINE_LITGEN_DIR}. "
            "Run git submodule update --init --recursive.")
    endif ()
    set(SYMENGINE_SRC_DIR "${CMAKE_SOURCE_DIR}/symengine")

    add_custom_command(
        OUTPUT ${SYMENGINE_NB_GENERATED}
        BYPRODUCTS
            ${SYMENGINE_NB_GENERATED_DIR}/symengine_pydef.cpp.d
        WORKING_DIRECTORY ${SYMENGINE_SRC_DIR}
        COMMAND ${CMAKE_COMMAND} -E make_directory ${SYMENGINE_NB_GENERATED_DIR}
        COMMAND ${CMAKE_COMMAND} -E env
                "PYTHONPATH=${SYMENGINE_LITGEN_DIR}"
                ${Python3_EXECUTABLE}
                ${CMAKE_CURRENT_SOURCE_DIR}/generator/generate.py
                ${CMAKE_CURRENT_SOURCE_DIR}/generator/generate.yaml
                --output-dir ${SYMENGINE_NB_GENERATED_DIR}
        DEPENDS
            ${CMAKE_CURRENT_SOURCE_DIR}/generator/generate.py
            ${CMAKE_CURRENT_SOURCE_DIR}/generator/generate.yaml
            ${CMAKE_CURRENT_SOURCE_DIR}/generator/litgen_extensions/__init__.py
            ${CMAKE_CURRENT_SOURCE_DIR}/generator/litgen_extensions/preprocess.py
            ${CMAKE_CURRENT_SOURCE_DIR}/generator/litgen_extensions/adapt_rcp_basic.py
        COMMENT "Generating C++ bindings with pinned litgen"
        VERBATIM)
    add_custom_target(symengine_nb_generate DEPENDS ${SYMENGINE_NB_GENERATED})

    # Generate shared-spec adapter-family bindings and matching declarations.
    set(SYMENGINE_NB_SIMPLE_INC "${SYMENGINE_NB_GENERATED_DIR}/symengine_simple_funcs.inc")
    set(SYMENGINE_NB_SIMPLE_PYI "${SYMENGINE_NB_GENERATED_DIR}/symengine_simple_funcs.pyi")
    add_custom_command(
        OUTPUT ${SYMENGINE_NB_SIMPLE_INC} ${SYMENGINE_NB_SIMPLE_PYI}
        COMMAND ${CMAKE_COMMAND} -E make_directory ${SYMENGINE_NB_GENERATED_DIR}
        COMMAND ${Python3_EXECUTABLE}
                -m tools.binding_codegen generate
                --language python
                --output ${SYMENGINE_NB_GENERATED_DIR}
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        DEPENDS
            ${CMAKE_SOURCE_DIR}/binding-spec/api.yaml
            ${CMAKE_SOURCE_DIR}/binding-spec/schema.json
            ${CMAKE_SOURCE_DIR}/tools/binding_codegen/model.py
            ${CMAKE_SOURCE_DIR}/tools/binding_codegen/inspect_cpp.py
            ${CMAKE_SOURCE_DIR}/tools/binding_codegen/render_nbsymengine.py
            ${CMAKE_SOURCE_DIR}/tools/binding_codegen/__main__.py
        COMMENT "Generating shared-spec Python adapter bindings"
        VERBATIM)
    add_custom_target(symengine_nb_simple_funcs DEPENDS ${SYMENGINE_NB_SIMPLE_INC})
else ()
    # Standalone or sdist build: use pre-generated files from generated/ directory
    set(SYMENGINE_NB_GENERATED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/generated")
    message(STATUS "Using pre-generated bindings from: ${SYMENGINE_NB_GENERATED_DIR}")
endif ()

if (SYMENGINE_NANOBIND_IN_TREE)
    nanobind_add_module(symengine_manual_ext
        src/rcp_ownership_test_module.cpp)
    set_target_properties(symengine_manual_ext PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
    target_include_directories(symengine_manual_ext PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/support
        ${CMAKE_SOURCE_DIR}/symengine
        ${CMAKE_BINARY_DIR}/symengine)

    find_path(BOOST_INCLUDE_DIR NAMES boost/multiprecision/cpp_int.hpp)
    if (BOOST_INCLUDE_DIR)
        target_include_directories(symengine_manual_ext SYSTEM PRIVATE
            ${BOOST_INCLUDE_DIR})
    endif ()
    target_link_libraries(symengine_manual_ext PRIVATE symengine)
endif ()

# --- The Generated _core Extension Module -----------------------------------
nanobind_add_module(_core
    src/core_module.cpp)

if (SYMENGINE_NANOBIND_IN_TREE)
    target_include_directories(_core PRIVATE
        ${SYMENGINE_NB_GENERATED_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/support
        ${CMAKE_SOURCE_DIR}/symengine
        ${CMAKE_BINARY_DIR}/symengine)

    find_path(BOOST_INCLUDE_DIR NAMES boost/multiprecision/cpp_int.hpp)
    if (BOOST_INCLUDE_DIR)
        target_include_directories(_core SYSTEM PRIVATE
            ${BOOST_INCLUDE_DIR})
    endif ()

    if (TARGET symengine_nb_generate)
        add_dependencies(_core symengine_nb_generate)
    endif ()
    if (TARGET symengine_nb_simple_funcs)
        add_dependencies(_core symengine_nb_simple_funcs)
    endif ()
else ()
    target_include_directories(_core PRIVATE
        ${SYMENGINE_NB_GENERATED_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/support
        ${SYMENGINE_INCLUDE_DIR})
endif ()

target_link_libraries(_core PRIVATE symengine)

# LLVM support detection
if (SYMENGINE_NANOBIND_IN_TREE)
    get_target_property(SYMENGINE_DEFS symengine INTERFACE_COMPILE_DEFINITIONS)
    if ("HAVE_SYMENGINE_LLVM" IN_LIST SYMENGINE_DEFS)
        set(NBSYMENGINE_HAVE_LLVM ON)
    endif()
else()
    if (HAVE_SYMENGINE_LLVM)
        set(NBSYMENGINE_HAVE_LLVM ON)
    endif()
endif()

if (NBSYMENGINE_HAVE_LLVM)
    message(STATUS "LLVM support enabled for nbsymengine")
    target_compile_definitions(_core PRIVATE HAVE_SYMENGINE_LLVM=1)
    find_package(LLVM CONFIG QUIET)
    if (LLVM_FOUND)
        target_link_directories(_core PRIVATE ${LLVM_LIBRARY_DIRS})
        target_link_libraries(_core PRIVATE ${LLVM_LIBRARIES})
        target_include_directories(_core PRIVATE ${LLVM_INCLUDE_DIRS})
    endif()
endif()

# --- Package Assembly and Installation --------------------------------------
if (SYMENGINE_NANOBIND_IN_TREE)
    # Assemble the Python package in the build tree so tests can run in-place
    set(NBSYMENGINE_PKG_DIR "${CMAKE_BINARY_DIR}/nbsymengine")
    set(NBSYMENGINE_PKG_STAMP "${NBSYMENGINE_PKG_DIR}/.pkg_stamp")

    add_custom_command(
        OUTPUT ${NBSYMENGINE_PKG_STAMP}
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            ${CMAKE_CURRENT_SOURCE_DIR}/nbsymengine/__init__.py
            ${NBSYMENGINE_PKG_DIR}/__init__.py
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            ${CMAKE_CURRENT_SOURCE_DIR}/nbsymengine/lambdify.py
            ${NBSYMENGINE_PKG_DIR}/lambdify.py
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            ${CMAKE_CURRENT_SOURCE_DIR}/nbsymengine/py.typed
            ${NBSYMENGINE_PKG_DIR}/py.typed
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            ${CMAKE_CURRENT_SOURCE_DIR}/tests/conftest.py
            ${CMAKE_BINARY_DIR}/conftest.py
        COMMAND ${CMAKE_COMMAND} -E touch ${NBSYMENGINE_PKG_STAMP}
        DEPENDS
            ${CMAKE_CURRENT_SOURCE_DIR}/nbsymengine/__init__.py
            ${CMAKE_CURRENT_SOURCE_DIR}/nbsymengine/lambdify.py
            ${CMAKE_CURRENT_SOURCE_DIR}/nbsymengine/py.typed
            ${CMAKE_CURRENT_SOURCE_DIR}/tests/conftest.py
        COMMENT "Assembling nbsymengine package in build tree")

    add_custom_target(nbsymengine_pkg ALL DEPENDS ${NBSYMENGINE_PKG_STAMP})
    add_dependencies(nbsymengine_pkg _core)

    # Copy generated stub into build tree package directory
    add_custom_command(
        TARGET _core POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${SYMENGINE_NB_GENERATED_DIR}/symengine.pyi"
            "${NBSYMENGINE_PKG_DIR}/_core.pyi"
        COMMENT "Copying _core.pyi into nbsymengine package")

    set_target_properties(_core PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${NBSYMENGINE_PKG_DIR}")
else ()
    # Standalone installation (scikit-build-core wheels)
    install(TARGETS _core
        LIBRARY DESTINATION nbsymengine
        COMPONENT python_package)

    if (EXISTS "${SYMENGINE_NB_GENERATED_DIR}/symengine.pyi")
        install(FILES "${SYMENGINE_NB_GENERATED_DIR}/symengine.pyi"
            DESTINATION nbsymengine
            RENAME _core.pyi
            COMPONENT python_package)
    endif ()
endif ()

# --- Tests (In-tree only) ---------------------------------------------------
if (SYMENGINE_NANOBIND_IN_TREE)
    option(BUILD_PYTHON_NANOBIND_REGEN_TESTS
           "Run generated binding reproducibility tests" OFF)

    if (BUILD_PYTHON_NANOBIND_REGEN_TESTS)
        execute_process(
            COMMAND ${Python_EXECUTABLE} -c "import litgen, yaml"
            RESULT_VARIABLE SYMENGINE_NANOBIND_REGEN_DEPS_RESULT
            OUTPUT_QUIET ERROR_QUIET)
        if (NOT SYMENGINE_NANOBIND_REGEN_DEPS_RESULT EQUAL 0)
            message(FATAL_ERROR
                "BUILD_PYTHON_NANOBIND_REGEN_TESTS is ON but generator dependencies are missing.")
        endif ()
    endif ()

    add_test(NAME nanobind_nbsymengine_import
        COMMAND ${Python_EXECUTABLE} -m pytest -x
            ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_import.py
        WORKING_DIRECTORY ${CMAKE_BINARY_DIR})
    set_tests_properties(nanobind_nbsymengine_import PROPERTIES
        ENVIRONMENT "PYTHONPATH=${CMAKE_BINARY_DIR}")

    add_test(NAME nanobind_ownership
        COMMAND ${Python_EXECUTABLE} -m pytest -x ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_manual_ownership.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
    set_tests_properties(nanobind_ownership PROPERTIES
        ENVIRONMENT "PYTHONPATH=$<TARGET_FILE_DIR:symengine_manual_ext>")

    add_test(NAME nanobind_generated_smoke
        COMMAND ${Python_EXECUTABLE} -m pytest -x ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_generated_smoke.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
    set_tests_properties(nanobind_generated_smoke PROPERTIES
        ENVIRONMENT "PYTHONPATH=${CMAKE_BINARY_DIR};SYMENGINE_NANOBIND_REGEN_TESTS=$<BOOL:${BUILD_PYTHON_NANOBIND_REGEN_TESTS}>")

    add_test(NAME nanobind_generated_rcp
        COMMAND ${Python_EXECUTABLE} -m pytest -x ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_generated_rcp.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
    set_tests_properties(nanobind_generated_rcp PROPERTIES
        ENVIRONMENT "PYTHONPATH=${CMAKE_BINARY_DIR};SYMENGINE_NANOBIND_REGEN_TESTS=$<BOOL:${BUILD_PYTHON_NANOBIND_REGEN_TESTS}>")

    add_test(NAME nanobind_shared_api_smoke
        COMMAND ${Python_EXECUTABLE} -m pytest -x
            ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_shared_api_smoke.py)
    set_tests_properties(nanobind_shared_api_smoke PROPERTIES
        ENVIRONMENT "PYTHONPATH=${CMAKE_BINARY_DIR}")

    add_test(NAME nanobind_shared_api_identity
        COMMAND ${Python_EXECUTABLE} -m pytest -x
            ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_shared_api_identity.py)
    set_tests_properties(nanobind_shared_api_identity PROPERTIES
        ENVIRONMENT "PYTHONPATH=${CMAKE_BINARY_DIR}")

    add_test(NAME nanobind_binding_api_fixture
        COMMAND ${Python_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tools/check_binding_api_fixtures.py
            --python-stub ${SYMENGINE_NB_GENERATED_PYI})
    set_tests_properties(nanobind_binding_api_fixture PROPERTIES
        WORKING_DIRECTORY ${CMAKE_BINARY_DIR})

    add_test(NAME nanobind_threading_stress
        COMMAND ${Python_EXECUTABLE} -m pytest -x ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_threading_stress.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
    set_tests_properties(nanobind_threading_stress PROPERTIES
        ENVIRONMENT "PYTHONPATH=${CMAKE_BINARY_DIR}"
        TIMEOUT 120)

    add_test(NAME nanobind_singleton_leaks
        COMMAND ${Python_EXECUTABLE} -m pytest -x ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_singleton_leaks.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
    set_tests_properties(nanobind_singleton_leaks PROPERTIES
        ENVIRONMENT "PYTHONPATH=${CMAKE_BINARY_DIR};$<TARGET_FILE_DIR:symengine_manual_ext>")

    add_test(NAME nanobind_singleton_shutdown
        COMMAND ${Python_EXECUTABLE} -m pytest -x ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_singleton_shutdown.py
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
    set_tests_properties(nanobind_singleton_shutdown PROPERTIES
        ENVIRONMENT "PYTHONPATH=${CMAKE_BINARY_DIR};$<TARGET_FILE_DIR:symengine_manual_ext>")

    add_test(NAME nanobind_core_bindings
        COMMAND ${Python_EXECUTABLE} -m pytest -x
            ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_core_bindings.py
        WORKING_DIRECTORY ${CMAKE_BINARY_DIR})
    set_tests_properties(nanobind_core_bindings PROPERTIES
        ENVIRONMENT "PYTHONPATH=${CMAKE_BINARY_DIR}")

    add_test(NAME nanobind_generated_policy
        COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/scripts/check_generated_policy.sh
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})
    set_tests_properties(nanobind_generated_policy PROPERTIES
        FAIL_REGULAR_EXPRESSION "ERROR")
endif ()
