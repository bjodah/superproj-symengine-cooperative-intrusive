"""Render Java's mechanical JNI call-throughs and public API surface.

Handle allocation, release, and exception translation intentionally live in
``symengine_jni.cpp``.  This renderer only deals with spec-owned calls.
"""

from __future__ import annotations

from .model import Argument, BindingSpec, Function
from .render_common import (
    RESULT_SHAPES,
    SCALAR_TYPES,
    cpp_result,
    functions_for_language,
    header,
)


SUPPORTED_FAMILIES = frozenset((
    "singleton", "unary_basic", "binary_basic", "binary_boolean",
    "integer_unary", "integer_binary", "status_optional_unary",
    "list_integer_to_basic",
))

# Java, JNI and public-facade spellings of the spec's non-handle argument types.
JAVA_SCALARS = {"double": ("double", "jdouble"), "unsigned": ("int", "jint")}

# What each result shape looks like on the three Java-side surfaces.
JAVA_NATIVE_RETURNS = {"handle": "long", "optional": "long", "list": "long[]"}
JAVA_PUBLIC_RETURNS = {"handle": "Basic", "optional": "Basic", "list": "Basic[]"}
JNI_RETURNS = {"handle": "jlong", "optional": "jlong", "list": "jlongArray"}
JNI_FAILURE = {"handle": "0", "optional": "0", "list": "nullptr"}
JAVADOC = {
    "optional": "    /** @return null when SymEngine reports that no result exists. */",
    "list": "    /** @return every result in SymEngine's order; empty when there are none. */",
}


def java_functions(spec: BindingSpec) -> tuple[Function, ...]:
    """Return generated Java entries in a stable order or name the gap."""
    return functions_for_language(spec, "java", SUPPORTED_FAMILIES)


def _native_parameters(function: Function) -> str:
    return ", ".join(
        f"{JAVA_SCALARS[argument.type_id][0]} {argument.name}"
        if argument.type_id in SCALAR_TYPES
        else f"long {argument.name}"
        for argument in function.arguments
    )


def render_java_jni(spec: BindingSpec) -> str:
    """Render package-private native declarations used by the public facade."""
    lines = header(spec, "//")
    lines.extend([
        "package org.symengine;",
        "",
        "final class SymEngineJNI {",
        "    static { System.loadLibrary(\"symengine_jni\"); }",
        "    private SymEngineJNI() {}",
        "",
        "    static native long symbol(byte[] utf8);",
        "    static native long integer(long value);",
        "    static native void release(long handle);",
        "    static native boolean equal(long left, long right);",
        "    static native long hash(long handle);",
        "    static native byte[] string(long handle);",
        "    static native boolean sameInstance(long left, long right);",
        "    static native long liveHandleCount();",
    ])
    for function in java_functions(spec):
        returns = JAVA_NATIVE_RETURNS[RESULT_SHAPES[function.behavior]]
        lines.append(
            f"    static native {returns} {function.public_name('java')}"
            f"({_native_parameters(function)});"
        )
    lines.extend(["}", ""])
    return "\n".join(lines)


def _public_parameter(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return f"{JAVA_SCALARS[argument.type_id][0]} {argument.name}"
    return f"Basic {argument.name}"


def _forwarded(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return argument.name
    return f"Basic.requireHandle({argument.name})"


def render_java_api(spec: BindingSpec) -> str:
    """Render public factories and forwarding methods over manual Basic lifecycle."""
    lines = header(spec, "//")
    lines.extend([
        "package org.symengine;",
        "",
        "import java.nio.charset.StandardCharsets;",
        "import java.util.Objects;",
        "",
        "public final class SymEngine {",
        "    private SymEngine() {}",
        "",
        "    public static Basic symbol(String name) {",
        "        Objects.requireNonNull(name, \"name\");",
        "        return Basic.fromHandle(SymEngineJNI.symbol(name.getBytes(StandardCharsets.UTF_8)));",
        "    }",
        "",
        "    public static Basic integer(long value) {",
        "        return Basic.fromHandle(SymEngineJNI.integer(value));",
        "    }",
    ])
    for function in java_functions(spec):
        shape = RESULT_SHAPES[function.behavior]
        name = function.public_name("java")
        parameters = ", ".join(_public_parameter(argument) for argument in function.arguments)
        handle_arguments = ", ".join(_forwarded(argument) for argument in function.arguments)
        lines.append("")
        if shape in JAVADOC:
            lines.append(JAVADOC[shape])
        lines.append(
            f"    public static {JAVA_PUBLIC_RETURNS[shape]} {name}({parameters}) {{"
        )
        if shape == "optional":
            # A pending JNI exception is delivered before this handle is read,
            # so 0 here can only mean "SymEngine found no result".
            lines.extend([
                f"        long handle = SymEngineJNI.{name}({handle_arguments});",
                "        return handle == 0 ? null : Basic.fromHandle(handle);",
            ])
        elif shape == "list":
            lines.append(
                f"        return Basic.fromHandles(SymEngineJNI.{name}({handle_arguments}));"
            )
        else:
            lines.append(
                f"        return Basic.fromHandle(SymEngineJNI.{name}({handle_arguments}));"
            )
        lines.append("    }")
    lines.extend(["}", ""])
    return "\n".join(lines)


def _jni_parameter(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return f"{JAVA_SCALARS[argument.type_id][1]} {argument.name}"
    return f"jlong {argument.name}"


def render_java_cpp(spec: BindingSpec) -> str:
    """Render JNI implementations that call SymEngine directly."""
    lines = header(spec, "//")
    lines.extend([
        "#include \"symengine_jni_runtime.h\"",
        "#include <exception>",
    ])
    headers = sorted({function.cpp.header for function in java_functions(spec)})
    lines.extend(f"#include <{include}>" for include in headers)
    for function in java_functions(spec):
        shape = RESULT_SHAPES[function.behavior]
        name = function.public_name("java")
        jni_parameters = ", ".join(_jni_parameter(argument) for argument in function.arguments)
        if jni_parameters:
            jni_parameters = ", " + jni_parameters
        lines.extend([
            "",
            f"extern \"C\" JNIEXPORT {JNI_RETURNS[shape]} JNICALL",
            f"Java_org_symengine_SymEngineJNI_{name}(JNIEnv *env, jclass{jni_parameters})",
            "{",
            "    try {",
        ])
        result = cpp_result(
            function, lambda argument: f"symengine_java::require_handle({argument.name})"
        )
        lines.extend(result.statements)
        if shape == "optional":
            lines.append(
                f"        return {result.found} "
                f"? symengine_java::make_handle({result.value}) : 0;"
            )
        elif shape == "list":
            lines.append(f"        return symengine_java::make_handle_array(env, {result.value});")
        else:
            lines.append(f"        return symengine_java::make_handle({result.value});")
        failure = JNI_FAILURE[shape]
        lines.extend([
            "    } catch (const std::exception &error) {",
            "        symengine_java::throw_exception(env, error.what());",
            f"        return {failure};",
            "    } catch (...) {",
            "        symengine_java::throw_exception(env, \"unknown SymEngine exception\");",
            f"        return {failure};",
            "    }",
            "}",
        ])
    return "\n".join(lines) + "\n"
