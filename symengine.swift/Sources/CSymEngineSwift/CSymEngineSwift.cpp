#include "CSymEngineSwift.h"

#include <symengine/add.h>
#include <symengine/constants.h>
#include <symengine/functions.h>
#include <symengine/integer.h>
#include <symengine/logic.h>
#include <symengine/mul.h>
#include <symengine/ntheory.h>
#include <symengine/pow.h>
#include <symengine/symbol.h>
#include <symengine/symengine_exception.h>
#include <symengine/symengine_rcp.h>
#include <symengine/symengine_config.h>

#include <atomic>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <mutex>
#include <new>
#include <string>
#include <vector>

#if !defined(WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP)
#error "symengine.swift requires SYMENGINE_RCP_BACKEND=cooperative_intrusive"
#endif

using SymEngine::Basic;
using SymEngine::RCP;

namespace {

thread_local std::string last_error;
std::mutex initialization_mutex;
std::mutex wrapper_mutex;
symengine_swift_ref_hook swift_retain_hook = nullptr;
symengine_swift_ref_hook swift_release_hook = nullptr;
std::atomic<bool> initialized{false};

void retain_trampoline(void *owner) noexcept
{
    swift_retain_hook(owner);
}

void release_trampoline(void *owner) noexcept
{
    swift_release_hook(owner);
}

symengine_swift_status fail(symengine_swift_status status,
                            const char *message) noexcept
{
    try {
        last_error = message;
    } catch (...) {
        // Preserve the C/noexcept boundary even if recording the error fails.
    }
    return status;
}

symengine_swift_status fail_current_exception() noexcept
{
    try {
        throw;
    } catch (const std::bad_alloc &) {
        return fail(SYMENGINE_SWIFT_OUT_OF_MEMORY, "out of memory");
    } catch (const SymEngine::SymEngineException &error) {
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR, error.what());
    } catch (const std::exception &error) {
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR, error.what());
    } catch (...) {
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR, "unknown C++ exception");
    }
}

const Basic *require_basic(symengine_swift_basic_ref value)
{
    if (value == nullptr)
        throw std::invalid_argument("null SymEngine object");
    return static_cast<const Basic *>(value);
}

symengine_swift_basic_ref return_owned(RCP<const Basic> value)
{
    const Basic *basic = value.get();
    basic->inc_ref();
    return basic;
}

template <typename Function>
symengine_swift_basic_ref make_result(Function &&function) noexcept
{
    if (!initialized.load(std::memory_order_acquire)) {
        fail(SYMENGINE_SWIFT_RUNTIME_ERROR,
             "Swift cooperative hooks are not initialized");
        return nullptr;
    }
    try {
        last_error.clear();
        return return_owned(function());
    } catch (...) {
        fail_current_exception();
        return nullptr;
    }
}

// Generic result shapes for generated entries that can report "no result" or a
// list of results.  `function` returns a possibly-null RCP, respectively a
// vector of RCPs; success is SYMENGINE_SWIFT_OK with `*result` left null, or
// with an owned reference per element in a malloc'd buffer.
template <typename Function>
symengine_swift_status make_optional_result(symengine_swift_basic_ref *result,
                                            Function &&function) noexcept
{
    if (result == nullptr)
        return fail(SYMENGINE_SWIFT_INVALID_ARGUMENT,
                    "result pointer must be non-null");
    *result = nullptr;
    if (!initialized.load(std::memory_order_acquire))
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR,
                    "Swift cooperative hooks are not initialized");
    try {
        last_error.clear();
        RCP<const Basic> value = function();
        if (!value.is_null())
            *result = return_owned(value);
        return SYMENGINE_SWIFT_OK;
    } catch (...) {
        return fail_current_exception();
    }
}

template <typename Function>
symengine_swift_status make_list_result(symengine_swift_basic_ref **values,
                                        size_t *count,
                                        Function &&function) noexcept
{
    if (values == nullptr || count == nullptr)
        return fail(SYMENGINE_SWIFT_INVALID_ARGUMENT,
                    "result pointers must be non-null");
    *values = nullptr;
    *count = 0;
    if (!initialized.load(std::memory_order_acquire))
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR,
                    "Swift cooperative hooks are not initialized");
    try {
        last_error.clear();
        const std::vector<RCP<const Basic>> items = function();
        if (items.empty())
            return SYMENGINE_SWIFT_OK;
        auto *buffer = static_cast<symengine_swift_basic_ref *>(
            std::malloc(items.size() * sizeof(symengine_swift_basic_ref)));
        if (buffer == nullptr)
            return fail(SYMENGINE_SWIFT_OUT_OF_MEMORY, "out of memory");
        for (size_t index = 0; index < items.size(); ++index)
            buffer[index] = return_owned(items[index]);
        *values = buffer;
        *count = items.size();
        return SYMENGINE_SWIFT_OK;
    } catch (...) {
        return fail_current_exception();
    }
}

} // namespace

extern "C" {

symengine_swift_status
symengine_swift_initialize(symengine_swift_ref_hook retain_hook,
                           symengine_swift_ref_hook release_hook)
{
    try {
        std::lock_guard<std::mutex> guard(initialization_mutex);
        if (retain_hook == nullptr || release_hook == nullptr)
            return fail(SYMENGINE_SWIFT_INVALID_ARGUMENT,
                        "retain and release hooks must be non-null");
        if (initialized.load(std::memory_order_relaxed)) {
            if (retain_hook == swift_retain_hook
                && release_hook == swift_release_hook)
                return SYMENGINE_SWIFT_OK;
            return fail(SYMENGINE_SWIFT_RUNTIME_ERROR,
                        "cooperative hooks are already initialized");
        }

        swift_retain_hook = retain_hook;
        swift_release_hook = release_hook;
        SymEngine::cooperative_intrusive_init(retain_trampoline,
                                              release_trampoline);
        initialized.store(true, std::memory_order_release);
        last_error.clear();
        return SYMENGINE_SWIFT_OK;
    } catch (...) {
        return fail_current_exception();
    }
}

const char *symengine_swift_version(void)
{
    return SYMENGINE_VERSION;
}

const char *symengine_swift_last_error(void)
{
    return last_error.c_str();
}

symengine_swift_basic_ref symengine_swift_symbol(const char *name)
{
    if (name == nullptr) {
        fail(SYMENGINE_SWIFT_INVALID_ARGUMENT, "symbol name must be non-null");
        return nullptr;
    }
    return make_result([&] { return SymEngine::symbol(std::string(name)); });
}

symengine_swift_basic_ref symengine_swift_integer(int64_t value)
{
    return make_result([&] {
        return SymEngine::integer(SymEngine::integer_class(
            std::to_string(value)));
    });
}

// Generated into SYMENGINE_BINDING_GENERATED_DIR by
// symengine.swift/tools/generate-bindings.sh before SwiftPM compiles this TU.
#include "SymEngineSwiftGenerated.inc"

symengine_swift_status
symengine_swift_equal(symengine_swift_basic_ref left,
                      symengine_swift_basic_ref right, int *result)
{
    if (!initialized.load(std::memory_order_acquire))
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR,
                    "Swift cooperative hooks are not initialized");
    if (result == nullptr)
        return fail(SYMENGINE_SWIFT_INVALID_ARGUMENT,
                    "equality result must be non-null");
    try {
        *result = SymEngine::eq(*require_basic(left), *require_basic(right));
        last_error.clear();
        return SYMENGINE_SWIFT_OK;
    } catch (...) {
        return fail_current_exception();
    }
}

symengine_swift_status
symengine_swift_string(symengine_swift_basic_ref value, char **result)
{
    if (!initialized.load(std::memory_order_acquire))
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR,
                    "Swift cooperative hooks are not initialized");
    if (result == nullptr)
        return fail(SYMENGINE_SWIFT_INVALID_ARGUMENT,
                    "string result must be non-null");
    *result = nullptr;
    try {
        std::string text = require_basic(value)->__str__();
        char *copy = static_cast<char *>(std::malloc(text.size() + 1));
        if (copy == nullptr)
            return fail(SYMENGINE_SWIFT_OUT_OF_MEMORY, "out of memory");
        std::memcpy(copy, text.c_str(), text.size() + 1);
        *result = copy;
        last_error.clear();
        return SYMENGINE_SWIFT_OK;
    } catch (...) {
        return fail_current_exception();
    }
}

void symengine_swift_string_free(char *value)
{
    std::free(value);
}

void symengine_swift_basic_list_free(symengine_swift_basic_ref *values)
{
    // Only the buffer: each element's reference was handed to the caller.
    std::free(values);
}

symengine_swift_status symengine_swift_wrapper_lock(void)
{
    if (!initialized.load(std::memory_order_acquire))
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR,
                    "Swift cooperative hooks are not initialized");
    try {
        wrapper_mutex.lock();
        return SYMENGINE_SWIFT_OK;
    } catch (...) {
        return fail_current_exception();
    }
}

void symengine_swift_wrapper_unlock(void)
{
    try {
        wrapper_mutex.unlock();
    } catch (...) {
        // Unlock failure is not recoverable, but no C++ exception may cross
        // the C ABI. A subsequent adoption will report or expose the failure.
    }
}

void *symengine_swift_external_owner(symengine_swift_basic_ref value)
{
    return value == nullptr ? nullptr
                            : static_cast<const Basic *>(value)->self_external();
}

symengine_swift_status
symengine_swift_externalize(symengine_swift_basic_ref value, void *owner)
{
    if (!initialized.load(std::memory_order_acquire))
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR,
                    "Swift cooperative hooks are not initialized");
    if (value == nullptr || owner == nullptr)
        return fail(SYMENGINE_SWIFT_INVALID_ARGUMENT,
                    "object and external owner must be non-null");
    if ((reinterpret_cast<uintptr_t>(owner) & 1U) != 0)
        return fail(SYMENGINE_SWIFT_INVALID_ARGUMENT,
                    "external owner pointer is not sufficiently aligned");

    const Basic *basic = static_cast<const Basic *>(value);
    if (basic->self_external() != nullptr)
        return fail(SYMENGINE_SWIFT_RUNTIME_ERROR,
                    "SymEngine object already has an external owner");
    basic->set_self_external(owner);
    last_error.clear();
    return SYMENGINE_SWIFT_OK;
}

void symengine_swift_release_owned(symengine_swift_basic_ref value)
{
    if (value == nullptr)
        return;
    const Basic *basic = static_cast<const Basic *>(value);
    if (basic->dec_ref())
        delete basic;
}

void symengine_swift_delete_external(symengine_swift_basic_ref value,
                                     void *expected_owner)
{
    if (value == nullptr || expected_owner == nullptr)
        return;
    const Basic *basic = static_cast<const Basic *>(value);
    if (basic->self_external() == expected_owner)
        delete basic;
}

symengine_swift_basic_kind
symengine_swift_kind(symengine_swift_basic_ref value)
{
    if (value == nullptr)
        return SYMENGINE_SWIFT_BASIC;
    const Basic &basic = *static_cast<const Basic *>(value);
    if (SymEngine::is_a<SymEngine::Integer>(basic))
        return SYMENGINE_SWIFT_INTEGER;
    if (SymEngine::is_a<SymEngine::Symbol>(basic))
        return SYMENGINE_SWIFT_SYMBOL;
    return SYMENGINE_SWIFT_BASIC;
}

int symengine_swift_is_external_owned(symengine_swift_basic_ref value)
{
    return value != nullptr
           && static_cast<const Basic *>(value)->is_external_owned();
}

} // extern "C"
