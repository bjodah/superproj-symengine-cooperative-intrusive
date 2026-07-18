#pragma once

#include <jni.h>
#include <symengine/basic.h>

namespace symengine_java {
using BasicHandle = SymEngine::RCP<const SymEngine::Basic>;

jlong make_handle(BasicHandle value);
const BasicHandle &require_handle(jlong handle);
void throw_exception(JNIEnv *env, const char *message) noexcept;
} // namespace symengine_java
