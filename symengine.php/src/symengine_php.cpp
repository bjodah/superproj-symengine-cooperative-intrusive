#include "symengine_php.h"

#include <cassert>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

zend_class_entry *symengine_ce_basic = nullptr;
zend_class_entry *symengine_ce_integer = nullptr;
zend_class_entry *symengine_ce_symbol = nullptr;

zend_object_handlers symengine_object_handlers;

namespace {

std::vector<const SymEngine::Basic *> g_singletons;
bool g_singletons_seeded = false;

} // namespace

void symengine_throw_cpp_exception(const std::exception &error)
{
    zend_throw_exception(zend_ce_exception, error.what(), 0);
}

const SymEngine::Basic *symengine_require_basic_ptr(zval *obj)
{
    const SymEngine::Basic *ptr = symengine_object_from_obj(Z_OBJ_P(obj))->ptr;
    if (ptr == nullptr) {
        throw std::runtime_error("SymEngine object has no native pointer");
    }
    return ptr;
}

symengine_object *symengine_object_from_obj(zend_object *obj)
{
    return reinterpret_cast<symengine_object *>(
        reinterpret_cast<char *>(obj) - XtOffsetOf(symengine_object, std));
}

zend_class_entry *symengine_class_for_basic(const SymEngine::Basic *basic)
{
    if (basic != nullptr && SymEngine::is_a<SymEngine::Integer>(*basic)) {
        return symengine_ce_integer;
    }
    if (basic != nullptr && SymEngine::is_a<SymEngine::Symbol>(*basic)) {
        return symengine_ce_symbol;
    }
    return symengine_ce_basic;
}

void symengine_seed_singletons()
{
    if (g_singletons_seeded) {
        return;
    }

    const SymEngine::RCP<const SymEngine::Basic> seeds[] = {
        SymEngine::zero,       SymEngine::one,         SymEngine::minus_one,
        SymEngine::two,        SymEngine::I,           SymEngine::E,
        SymEngine::pi,         SymEngine::EulerGamma,  SymEngine::Catalan,
        SymEngine::GoldenRatio, SymEngine::Inf,        SymEngine::NegInf,
        SymEngine::ComplexInf, SymEngine::Nan,
    };

    g_singletons.reserve(sizeof(seeds) / sizeof(seeds[0]));
    for (const auto &seed : seeds) {
        g_singletons.push_back(seed.get());
    }
    g_singletons_seeded = true;
}

void symengine_reconcile_singletons()
{
    for (const SymEngine::Basic *basic : g_singletons) {
        void *external = basic->self_external();
        if (external == nullptr) {
            continue;
        }

        zend_object *object = reinterpret_cast<zend_object *>(external);
        uint32_t count = GC_REFCOUNT(object);

        basic->detach_external();
        for (uint32_t i = 0; i < count; ++i) {
            basic->inc_ref();
        }
    }
}

bool symengine_is_singleton(const SymEngine::Basic *ptr)
{
    for (const SymEngine::Basic *s : g_singletons) {
        if (s == ptr) {
            return true;
        }
    }
    return false;
}

void symengine_wrap_basic(zval *return_value,
                          const SymEngine::RCP<const SymEngine::Basic> &value)
{
    const SymEngine::Basic *basic = value.get();
    if (basic == nullptr) {
        ZVAL_NULL(return_value);
        return;
    }

    if (void *external = basic->self_external()) {
        zend_object *object = reinterpret_cast<zend_object *>(external);
        GC_ADDREF(object);
        ZVAL_OBJ(return_value, object);
        return;
    }

    object_init_ex(return_value, symengine_class_for_basic(basic));
    symengine_object *intern = symengine_object_from_obj(Z_OBJ_P(return_value));
    intern->ptr = basic;

#if !defined(NDEBUG)
    assert(symengine_class_for_basic(basic) == Z_OBJCE_P(return_value));
    assert(basic->self_external() == nullptr);
#endif

    basic->set_self_external(Z_OBJ_P(return_value));
}

void symengine_wrap_basic_list(
    zval *return_value,
    const std::vector<SymEngine::RCP<const SymEngine::Basic>> &values)
{
    array_init_size(return_value, static_cast<uint32_t>(values.size()));
    for (const auto &value : values) {
        zval item;
        symengine_wrap_basic(&item, value);
        add_next_index_zval(return_value, &item);
    }
}

SymEngine::RCP<const SymEngine::Basic> symengine_unwrap_basic(zval *obj)
{
    return SymEngine::rcp(symengine_require_basic_ptr(obj));
}

zend_object *symengine_basic_new(zend_class_entry *ce)
{
    auto *obj = static_cast<symengine_object *>(
        zend_object_alloc(sizeof(symengine_object), ce));
    obj->ptr = nullptr;
    zend_object_std_init(&obj->std, ce);
    object_properties_init(&obj->std, ce);
    obj->std.handlers = &symengine_object_handlers;
    return &obj->std;
}

void symengine_basic_free_obj(zend_object *object)
{
    symengine_object *obj = symengine_object_from_obj(object);

    if (obj->ptr != nullptr && !symengine_is_destructing()
        && obj->ptr->is_external_owned()) {
#if !defined(NDEBUG)
        assert(obj->ptr->self_external() == object);
#endif
        delete obj->ptr;
    }

    obj->ptr = nullptr;
    zend_object_std_dtor(&obj->std);
}

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_basic_tostring, 0, 0, IS_STRING, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_INFO_EX(arginfo_basic_construct, 0, 0, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_basic_is_external_owned, 0, 0, _IS_BOOL, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_basic_php_refcount, 0, 0, IS_LONG, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_basic_same_object, 0, 1, _IS_BOOL, 0)
    ZEND_ARG_OBJ_INFO(0, other, SymEngine\\Basic, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_basic_cpp_use_count, 0, 0, IS_LONG, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_basic_external_owner_address, 0, 0, IS_STRING, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_basic_is_singleton_seeded, 0, 0, _IS_BOOL, 0)
ZEND_END_ARG_INFO()

PHP_METHOD(SymEngine_Basic, __construct)
{
    ZEND_PARSE_PARAMETERS_NONE();

    zend_throw_exception(
        zend_ce_exception,
        "SymEngine objects cannot be constructed directly; use symengine_integer(), symengine_symbol(), or SymEngine factory functions",
        0);
    RETURN_THROWS();
}

PHP_METHOD(SymEngine_Basic, __toString)
{
    ZEND_PARSE_PARAMETERS_NONE();

    try {
        RETURN_STRING(symengine_require_basic_ptr(ZEND_THIS)->__str__().c_str());
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}

PHP_METHOD(SymEngine_Basic, isExternalOwned)
{
    ZEND_PARSE_PARAMETERS_NONE();

    try {
        RETURN_BOOL(symengine_require_basic_ptr(ZEND_THIS)->is_external_owned());
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}

PHP_METHOD(SymEngine_Basic, phpRefCount)
{
    ZEND_PARSE_PARAMETERS_NONE();
    RETURN_LONG(GC_REFCOUNT(Z_OBJ_P(ZEND_THIS)));
}

PHP_METHOD(SymEngine_Basic, sameObject)
{
    zval *other;

    if (zend_parse_parameters(ZEND_NUM_ARGS(), "O", &other, symengine_ce_basic)
        == FAILURE) {
        RETURN_THROWS();
    }

    try {
        RETURN_BOOL(symengine_require_basic_ptr(ZEND_THIS)
                    == symengine_require_basic_ptr(other));
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}

#if defined(SYMENGINE_PHP_DEBUG_HELPERS)
PHP_METHOD(SymEngine_Basic, cppUseCount)
{
    ZEND_PARSE_PARAMETERS_NONE();

    try {
        RETURN_LONG(symengine_require_basic_ptr(ZEND_THIS)->use_count());
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}

PHP_METHOD(SymEngine_Basic, externalOwnerAddress)
{
    ZEND_PARSE_PARAMETERS_NONE();

    try {
        const SymEngine::Basic *ptr = symengine_require_basic_ptr(ZEND_THIS);
        void *ext = ptr->self_external();
        if (ext == nullptr) {
            RETURN_STRING("inline");
        }
        char buf[32];
        snprintf(buf, sizeof(buf), "%p", ext);
        RETURN_STRING(buf);
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}

PHP_METHOD(SymEngine_Basic, isSingletonSeeded)
{
    ZEND_PARSE_PARAMETERS_NONE();

    try {
        const SymEngine::Basic *ptr = symengine_require_basic_ptr(ZEND_THIS);
        RETURN_BOOL(symengine_is_singleton(ptr));
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}
#endif

static const zend_function_entry symengine_basic_methods[] = {
    PHP_ME(SymEngine_Basic, __construct, arginfo_basic_construct, ZEND_ACC_PUBLIC)
    PHP_ME(SymEngine_Basic, __toString, arginfo_basic_tostring, ZEND_ACC_PUBLIC)
    PHP_ME(SymEngine_Basic, isExternalOwned, arginfo_basic_is_external_owned, ZEND_ACC_PUBLIC)
    PHP_ME(SymEngine_Basic, phpRefCount, arginfo_basic_php_refcount, ZEND_ACC_PUBLIC)
    PHP_ME(SymEngine_Basic, sameObject, arginfo_basic_same_object, ZEND_ACC_PUBLIC)
#if defined(SYMENGINE_PHP_DEBUG_HELPERS)
    PHP_ME(SymEngine_Basic, cppUseCount, arginfo_basic_cpp_use_count, ZEND_ACC_PUBLIC)
    PHP_ME(SymEngine_Basic, externalOwnerAddress, arginfo_basic_external_owner_address, ZEND_ACC_PUBLIC)
    PHP_ME(SymEngine_Basic, isSingletonSeeded, arginfo_basic_is_singleton_seeded, ZEND_ACC_PUBLIC)
#endif
    PHP_FE_END
};

void symengine_register_basic_class()
{
    zend_class_entry ce;

    INIT_CLASS_ENTRY(ce, "SymEngine\\Basic", symengine_basic_methods);
    ce.create_object = symengine_basic_new;
    symengine_ce_basic = zend_register_internal_class(&ce);

    memcpy(&symengine_object_handlers, zend_get_std_object_handlers(),
           sizeof(zend_object_handlers));
    symengine_object_handlers.offset = XtOffsetOf(symengine_object, std);
    symengine_object_handlers.free_obj = symengine_basic_free_obj;
}

void symengine_register_integer_class()
{
    zend_class_entry ce;

    INIT_CLASS_ENTRY(ce, "SymEngine\\Integer", nullptr);
    ce.create_object = symengine_basic_new;
    symengine_ce_integer = zend_register_internal_class_ex(&ce, symengine_ce_basic);
}

void symengine_register_symbol_class()
{
    zend_class_entry ce;

    INIT_CLASS_ENTRY(ce, "SymEngine\\Symbol", nullptr);
    ce.create_object = symengine_basic_new;
    symengine_ce_symbol = zend_register_internal_class_ex(&ce, symengine_ce_basic);
}

PHP_MINIT_FUNCTION(symengine)
{
    symengine_register_cooperative_hooks();
    symengine_seed_singletons();
    symengine_register_basic_class();
    symengine_register_integer_class();
    symengine_register_symbol_class();
    return SUCCESS;
}

PHP_MSHUTDOWN_FUNCTION(symengine)
{
    // From this point onward Zend objects must no longer be touched by
    // cooperative hooks. Static SymEngine singleton destructors can still run
    // later during process teardown, so make the hooks inert here.
    symengine_mark_destructing();
    return SUCCESS;
}

PHP_RINIT_FUNCTION(symengine)
{
    return SUCCESS;
}

PHP_RSHUTDOWN_FUNCTION(symengine)
{
    // Reconcile externalized singletons back to inline mode while their Zend
    // wrappers still exist and their refcounts are observable.
    symengine_reconcile_singletons();
    return SUCCESS;
}

PHP_MINFO_FUNCTION(symengine)
{
    php_info_print_table_start();
    php_info_print_table_header(2, "SymEngine support", "enabled");
    php_info_print_table_row(2, "Version", PHP_SYMENGINE_VERSION);
    php_info_print_table_row(2, "SymEngine version", SYMENGINE_VERSION);
    php_info_print_table_end();
}

ZEND_BEGIN_ARG_WITH_RETURN_OBJ_INFO_EX(arginfo_symengine_integer_ctor, 0, 1, SymEngine\\Integer, 0)
    ZEND_ARG_TYPE_INFO(0, val, IS_LONG, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_OBJ_INFO_EX(arginfo_symengine_symbol_ctor, 0, 1, SymEngine\\Symbol, 0)
    ZEND_ARG_TYPE_INFO(0, name, IS_STRING, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_OBJ_INFO_EX(arginfo_symengine_binary, 0, 2, SymEngine\\Basic, 0)
    ZEND_ARG_OBJ_INFO(0, a, SymEngine\\Basic, 0)
    ZEND_ARG_OBJ_INFO(0, b, SymEngine\\Basic, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_OBJ_INFO_EX(arginfo_symengine_unary_basic, 0, 1, SymEngine\\Basic, 0)
    ZEND_ARG_OBJ_INFO(0, value, SymEngine\\Basic, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_symengine_str, 0, 1, IS_STRING, 0)
    ZEND_ARG_OBJ_INFO(0, obj, SymEngine\\Basic, 0)
ZEND_END_ARG_INFO()

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_symengine_eq, 0, 2, _IS_BOOL, 0)
    ZEND_ARG_OBJ_INFO(0, a, SymEngine\\Basic, 0)
    ZEND_ARG_OBJ_INFO(0, b, SymEngine\\Basic, 0)
ZEND_END_ARG_INFO()

// Generated module-level constants and expression operations. configure writes
// this include into $abs_builddir/generated and adds that directory to
// INCLUDES; nothing generated is ever written into the tracked source tree.
#include "symengine_php_generated.inc"

PHP_FUNCTION(symengine_integer)
{
    zend_long value;

    if (zend_parse_parameters(ZEND_NUM_ARGS(), "l", &value) == FAILURE) {
        RETURN_THROWS();
    }

    try {
        symengine_wrap_basic(return_value, SymEngine::integer(value));
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}

PHP_FUNCTION(symengine_symbol)
{
    char *name;
    size_t name_len;

    if (zend_parse_parameters(ZEND_NUM_ARGS(), "s", &name, &name_len)
        == FAILURE) {
        RETURN_THROWS();
    }

    try {
        symengine_wrap_basic(return_value,
                             SymEngine::symbol(std::string(name, name_len)));
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}

PHP_FUNCTION(symengine_str)
{
    zval *obj;

    if (zend_parse_parameters(ZEND_NUM_ARGS(), "O", &obj, symengine_ce_basic)
        == FAILURE) {
        RETURN_THROWS();
    }

    try {
        RETURN_STRING(symengine_require_basic_ptr(obj)->__str__().c_str());
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}

PHP_FUNCTION(symengine_eq)
{
    zval *a;
    zval *b;

    if (zend_parse_parameters(ZEND_NUM_ARGS(), "OO", &a, symengine_ce_basic, &b,
                              symengine_ce_basic)
        == FAILURE) {
        RETURN_THROWS();
    }

    try {
        const SymEngine::Basic *left = symengine_require_basic_ptr(a);
        const SymEngine::Basic *right = symengine_require_basic_ptr(b);
        RETURN_BOOL(SymEngine::eq(*left, *right));
    } catch (const std::exception &error) {
        symengine_throw_cpp_exception(error);
        RETURN_THROWS();
    }
}

static const zend_function_entry symengine_functions[] = {
    #include "symengine_php_generated_functions.inc"
    PHP_FE(symengine_integer, arginfo_symengine_integer_ctor)
    PHP_FE(symengine_symbol, arginfo_symengine_symbol_ctor)
    PHP_FE(symengine_str, arginfo_symengine_str)
    PHP_FE(symengine_eq, arginfo_symengine_eq)
    PHP_FE_END
};

zend_module_entry symengine_module_entry = {
    STANDARD_MODULE_HEADER,
    PHP_SYMENGINE_EXTNAME,
    symengine_functions,
    PHP_MINIT(symengine),
    PHP_MSHUTDOWN(symengine),
    PHP_RINIT(symengine),
    PHP_RSHUTDOWN(symengine),
    PHP_MINFO(symengine),
    PHP_SYMENGINE_VERSION,
    STANDARD_MODULE_PROPERTIES
};
