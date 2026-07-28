# BindingCodegen.cmake - one way to invoke the shared binding generator.
#
# Every wrapper that renders glue from `binding-spec/` goes through
# `symengine_binding_codegen()` so that the DEPENDS list (spec, schema, test
# cases and every generator source) is maintained in exactly one place.
#
#   symengine_binding_codegen(
#       LANGUAGE <python|perl|php|swift|java>
#       OUTPUT_DIR <dir>                # generated files land here (build tree)
#       [ARTIFACT <all|cpp|api|tests>]  # forwarded verbatim; swift-only selector
#       [OUTPUTS <files...>]            # generated files this command produces
#       [TARGET <name>]                 # convenience target depending on OUTPUTS
#       [ALL]                           # attach TARGET to the default build
#       [PYTHON <interpreter>]          # default: Python3_EXECUTABLE
#       [ENVIRONMENT <VAR=value>...]    # extra environment for the generator
#       [DEPENDS <extra-deps...>]
#       [COMMENT <text>])
#
# OUTPUTS carries the files the generator writes for this language; they become
# the custom command's OUTPUT so that consumers can depend on them by path.
# (CMake's own BYPRODUCTS keyword means "side effect that does not drive the
# dependency graph", which is not what these files are.)
#
# The roadmap rule is that generated files go to build directories, never into
# a source tree; callers are expected to pass an OUTPUT_DIR below their build
# directory.

include_guard(GLOBAL)

function(symengine_binding_codegen)
    set(_options ALL)
    set(_one_value LANGUAGE OUTPUT_DIR ARTIFACT TARGET PYTHON COMMENT)
    set(_multi_value OUTPUTS DEPENDS ENVIRONMENT)
    cmake_parse_arguments(PARSE_ARGV 0 SBC "${_options}" "${_one_value}" "${_multi_value}")

    if (SBC_UNPARSED_ARGUMENTS)
        message(FATAL_ERROR
            "symengine_binding_codegen: unexpected arguments: ${SBC_UNPARSED_ARGUMENTS}")
    endif ()
    if (NOT SBC_LANGUAGE)
        message(FATAL_ERROR "symengine_binding_codegen: LANGUAGE is required")
    endif ()
    if (NOT SBC_LANGUAGE MATCHES "^(python|perl|php|swift|java)$")
        message(FATAL_ERROR
            "symengine_binding_codegen: unsupported LANGUAGE '${SBC_LANGUAGE}'")
    endif ()
    if (NOT SBC_OUTPUT_DIR)
        message(FATAL_ERROR "symengine_binding_codegen: OUTPUT_DIR is required")
    endif ()
    if (NOT SBC_OUTPUTS)
        message(FATAL_ERROR "symengine_binding_codegen: OUTPUTS is required")
    endif ()
    if (SBC_ALL AND NOT SBC_TARGET)
        message(FATAL_ERROR "symengine_binding_codegen: ALL requires TARGET")
    endif ()

    # Anchor on this module rather than on CMAKE_SOURCE_DIR so the function
    # works from any subdirectory (and from a wrapper added standalone).
    get_filename_component(_codegen_root "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/.." ABSOLUTE)

    # The one canonical dependency list: the shared spec plus every generator
    # source. Editing any renderer must regenerate every wrapper's glue.
    set(_codegen_depends "")
    foreach (_spec_file IN ITEMS
             api.yaml
             schema.json
             test-cases.yaml
             test-cases.schema.json)
        list(APPEND _codegen_depends "${_codegen_root}/binding-spec/${_spec_file}")
    endforeach ()
    foreach (_tool_file IN ITEMS
             __init__.py
             __main__.py
             coverage.py
             inspect_cpp.py
             model.py
             render_common.py
             render_java.py
             render_nbsymengine.py
             render_perl.py
             render_php.py
             render_swift.py
             render_tests.py
             test_cases.py)
        list(APPEND _codegen_depends "${_codegen_root}/tools/binding_codegen/${_tool_file}")
    endforeach ()

    if (SBC_PYTHON)
        set(_python "${SBC_PYTHON}")
    elseif (Python3_EXECUTABLE)
        set(_python "${Python3_EXECUTABLE}")
    elseif (Python_EXECUTABLE)
        set(_python "${Python_EXECUTABLE}")
    else ()
        find_package(Python3 COMPONENTS Interpreter REQUIRED)
        set(_python "${Python3_EXECUTABLE}")
    endif ()

    set(_artifact_arguments "")
    if (SBC_ARTIFACT)
        set(_artifact_arguments --artifact "${SBC_ARTIFACT}")
    endif ()

    if (SBC_COMMENT)
        set(_comment "${SBC_COMMENT}")
    else ()
        set(_comment "Generating shared ${SBC_LANGUAGE} bindings from binding-spec")
    endif ()

    add_custom_command(
        OUTPUT ${SBC_OUTPUTS}
        COMMAND "${CMAKE_COMMAND}" -E make_directory "${SBC_OUTPUT_DIR}"
        COMMAND "${CMAKE_COMMAND}" -E env
                "PYTHONPATH=${_codegen_root}"
                ${SBC_ENVIRONMENT}
                "${_python}" -m tools.binding_codegen generate
                --language "${SBC_LANGUAGE}"
                ${_artifact_arguments}
                --output "${SBC_OUTPUT_DIR}"
        WORKING_DIRECTORY "${_codegen_root}"
        DEPENDS ${_codegen_depends} ${SBC_DEPENDS}
        COMMENT "${_comment}"
        VERBATIM)

    if (SBC_TARGET)
        if (SBC_ALL)
            add_custom_target(${SBC_TARGET} ALL DEPENDS ${SBC_OUTPUTS})
        else ()
            add_custom_target(${SBC_TARGET} DEPENDS ${SBC_OUTPUTS})
        endif ()
    endif ()
endfunction()
