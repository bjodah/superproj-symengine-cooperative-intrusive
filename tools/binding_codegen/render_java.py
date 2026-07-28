"""Render Java's mechanical JNI call-throughs and public API surface.

Handle allocation, release, and exception translation intentionally live in
``symengine_jni.cpp``.  This renderer only deals with spec-owned calls.
"""

from __future__ import annotations

from .model import BindingSpec, Function
from .render_common import functions_for_language, header


SUPPORTED_FAMILIES = frozenset(("singleton", "unary_basic", "binary_basic"))


def java_functions(spec: BindingSpec) -> tuple[Function, ...]:
    """Return generated Java entries in a stable order or name the gap."""
    return functions_for_language(spec, "java", SUPPORTED_FAMILIES)


def _native_parameters(function: Function) -> str:
    return ", ".join(f"long {argument.name}" for argument in function.arguments)


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
        lines.append(f"    static native long {function.public_name('java')}({_native_parameters(function)});")
    lines.extend(["}", ""])
    return "\n".join(lines)


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
        name = function.public_name("java")
        parameters = ", ".join(f"Basic {argument.name}" for argument in function.arguments)
        handle_arguments = ", ".join(
            f"Basic.requireHandle({argument.name})" for argument in function.arguments
        )
        lines.extend(["", f"    public static Basic {name}({parameters}) {{"])
        lines.append(
            f"        return Basic.fromHandle(SymEngineJNI.{name}({handle_arguments}));"
        )
        lines.append("    }")
    lines.extend(["}", ""])
    return "\n".join(lines)


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
        name = function.public_name("java")
        jni_parameters = ", ".join(f"jlong {argument.name}" for argument in function.arguments)
        if jni_parameters:
            jni_parameters = ", " + jni_parameters
        lines.extend([
            "",
            "extern \"C\" JNIEXPORT jlong JNICALL",
            f"Java_org_symengine_SymEngineJNI_{name}(JNIEnv *env, jclass{jni_parameters})",
            "{",
            "    try {",
        ])
        if function.behavior == "singleton":
            assert function.cpp.expression is not None
            call = function.cpp.expression
        else:
            assert function.cpp.name is not None
            arguments = ", ".join(
                f"symengine_java::require_handle({argument.name})" for argument in function.arguments
            )
            call = f"{function.cpp.name}({arguments})"
        lines.extend([
            f"        return symengine_java::make_handle({call});",
            "    } catch (const std::exception &error) {",
            "        symengine_java::throw_exception(env, error.what());",
            "        return 0;",
            "    } catch (...) {",
            "        symengine_java::throw_exception(env, \"unknown SymEngine exception\");",
            "        return 0;",
            "    }",
            "}",
        ])
    return "\n".join(lines) + "\n"
