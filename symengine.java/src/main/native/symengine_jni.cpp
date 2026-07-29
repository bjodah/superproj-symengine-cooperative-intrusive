#include "symengine_jni_runtime.h"

#include <atomic>
#include <exception>
#include <stdexcept>
#include <string>

#include <symengine/add.h>
#include <symengine/integer.h>
#include <symengine/symbol.h>

namespace {
std::atomic<long> live_handles{0};
jclass exception_class = nullptr;
jmethodID exception_constructor = nullptr;

struct HandleCell {
    explicit HandleCell(SymEngine::RCP<const SymEngine::Basic> value) : value(std::move(value)) {}
    SymEngine::RCP<const SymEngine::Basic> value;
};
} // namespace

namespace symengine_java {
jlong make_handle(BasicHandle value)
{
    auto *cell = new HandleCell(std::move(value));
    ++live_handles;
    return reinterpret_cast<jlong>(cell);
}

jlongArray make_handle_array(JNIEnv *env, const std::vector<BasicHandle> &values)
{
    jlongArray result = env->NewLongArray(static_cast<jsize>(values.size()));
    if (result == nullptr) return nullptr;
    std::vector<jlong> handles;
    handles.reserve(values.size());
    for (const auto &value : values) handles.push_back(make_handle(value));
    if (!handles.empty()) {
        env->SetLongArrayRegion(result, 0, static_cast<jsize>(handles.size()), handles.data());
    }
    return result;
}

const BasicHandle &require_handle(jlong handle)
{
    if (handle == 0) throw std::invalid_argument("Basic handle is null or closed");
    return reinterpret_cast<HandleCell *>(handle)->value;
}

void throw_exception(JNIEnv *env, const char *message) noexcept
{
    // NewStringUTF expects Modified UTF-8; exception messages are ASCII/C++
    // what() text in practice, so that limitation is accepted here.
    if (!env->ExceptionCheck() && exception_class != nullptr && exception_constructor != nullptr) {
        jstring text = env->NewStringUTF(message);
        if (text != nullptr) {
            jobject exception = env->NewObject(exception_class, exception_constructor, text);
            env->DeleteLocalRef(text);
            if (exception != nullptr) {
                env->Throw(static_cast<jthrowable>(exception));
                env->DeleteLocalRef(exception);
            }
        }
    }
}
} // namespace symengine_java

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *)
{
    JNIEnv *env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_8) != JNI_OK) return JNI_ERR;
    jclass local = env->FindClass("org/symengine/SymEngineException");
    if (local == nullptr) return JNI_ERR;
    exception_class = static_cast<jclass>(env->NewGlobalRef(local));
    env->DeleteLocalRef(local);
    if (exception_class == nullptr) return JNI_ERR;
    exception_constructor = env->GetMethodID(exception_class, "<init>", "(Ljava/lang/String;)V");
    return exception_constructor == nullptr ? JNI_ERR : JNI_VERSION_1_8;
}

extern "C" JNIEXPORT jlong JNICALL
Java_org_symengine_SymEngineJNI_symbol(JNIEnv *env, jclass, jbyteArray utf8)
{
    try {
        if (utf8 == nullptr) throw std::invalid_argument("symbol name is null");
        const jsize length = env->GetArrayLength(utf8);
        std::string name(static_cast<size_t>(length), '\0');
        if (length != 0) env->GetByteArrayRegion(utf8, 0, length, reinterpret_cast<jbyte *>(name.data()));
        if (env->ExceptionCheck()) return 0;
        return symengine_java::make_handle(SymEngine::symbol(name));
    } catch (const std::exception &error) {
        symengine_java::throw_exception(env, error.what());
        return 0;
    }
}

extern "C" JNIEXPORT jlong JNICALL
Java_org_symengine_SymEngineJNI_integer(JNIEnv *env, jclass, jlong value)
{
    try {
        return symengine_java::make_handle(SymEngine::integer(static_cast<long>(value)));
    } catch (const std::exception &error) {
        symengine_java::throw_exception(env, error.what());
        return 0;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_org_symengine_SymEngineJNI_release(JNIEnv *, jclass, jlong handle)
{
    if (handle != 0) {
        delete reinterpret_cast<HandleCell *>(handle);
        --live_handles;
    }
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_symengine_SymEngineJNI_equal(JNIEnv *env, jclass, jlong left, jlong right)
{
    try {
        return SymEngine::eq(*symengine_java::require_handle(left), *symengine_java::require_handle(right));
    } catch (const std::exception &error) {
        symengine_java::throw_exception(env, error.what());
        return JNI_FALSE;
    }
}

extern "C" JNIEXPORT jlong JNICALL
Java_org_symengine_SymEngineJNI_hash(JNIEnv *env, jclass, jlong handle)
{
    try {
        return static_cast<jlong>(symengine_java::require_handle(handle)->hash());
    } catch (const std::exception &error) {
        symengine_java::throw_exception(env, error.what());
        return 0;
    }
}

extern "C" JNIEXPORT jbyteArray JNICALL
Java_org_symengine_SymEngineJNI_string(JNIEnv *env, jclass, jlong handle)
{
    try {
        std::string text = symengine_java::require_handle(handle)->__str__();
        jbyteArray result = env->NewByteArray(static_cast<jsize>(text.size()));
        if (result == nullptr) return nullptr;
        env->SetByteArrayRegion(result, 0, static_cast<jsize>(text.size()),
                                 reinterpret_cast<const jbyte *>(text.data()));
        return result;
    } catch (const std::exception &error) {
        symengine_java::throw_exception(env, error.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_symengine_SymEngineJNI_sameInstance(JNIEnv *env, jclass, jlong left, jlong right)
{
    try {
        return symengine_java::require_handle(left).get() == symengine_java::require_handle(right).get();
    } catch (const std::exception &error) {
        symengine_java::throw_exception(env, error.what());
        return JNI_FALSE;
    }
}

extern "C" JNIEXPORT jlong JNICALL
Java_org_symengine_SymEngineJNI_liveHandleCount(JNIEnv *, jclass)
{
    return live_handles.load();
}
