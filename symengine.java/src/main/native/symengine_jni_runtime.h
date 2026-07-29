#pragma once

#include <jni.h>
#include <symengine/basic.h>
// The generated JNI translation unit only includes this header plus the
// spec-declared SymEngine headers, so the types every generated typed-argument
// guard needs (Integer, SymEngineException) are provided here once.
#include <symengine/integer.h>
#include <symengine/symengine_exception.h>

namespace symengine_java {
using BasicHandle = SymEngine::RCP<const SymEngine::Basic>;

jlong make_handle(BasicHandle value);
const BasicHandle &require_handle(jlong handle);
void throw_exception(JNIEnv *env, const char *message) noexcept;
} // namespace symengine_java
