#pragma once

#include <jni.h>
#include <symengine/basic.h>
// The generated JNI translation unit only includes this header plus the
// spec-declared SymEngine headers, so the types every generated typed-argument
// guard needs (Integer, SymEngineException) are provided here once.
#include <symengine/integer.h>
#include <symengine/symengine_exception.h>

#include <vector>

namespace symengine_java {
using BasicHandle = SymEngine::RCP<const SymEngine::Basic>;

jlong make_handle(BasicHandle value);
// Generic list-result spelling: one Java long[] of freshly allocated handles.
// "No result" needs no helper -- the generated code simply returns handle 0.
jlongArray make_handle_array(JNIEnv *env, const std::vector<BasicHandle> &values);
const BasicHandle &require_handle(jlong handle);
void throw_exception(JNIEnv *env, const char *message) noexcept;
} // namespace symengine_java
