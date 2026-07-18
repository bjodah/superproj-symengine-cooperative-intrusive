#include "symengine_php.h"

namespace {

bool g_cooperative_hooks_registered = false;
bool g_php_destructing = false;

void symengine_php_inc_hook(void *ptr) noexcept
{
    if (g_php_destructing) {
        return;
    }
    GC_ADDREF(reinterpret_cast<zend_object *>(ptr));
}

void symengine_php_dec_hook(void *ptr) noexcept
{
    if (g_php_destructing) {
        return;
    }
    OBJ_RELEASE(reinterpret_cast<zend_object *>(ptr));
}

} // namespace

void symengine_register_cooperative_hooks() {
    if (g_cooperative_hooks_registered) {
        return;
    }
    g_php_destructing = false;
    SymEngine::cooperative_intrusive_init(symengine_php_inc_hook,
                                          symengine_php_dec_hook);
    g_cooperative_hooks_registered = true;
}

bool symengine_is_destructing()
{
    return g_php_destructing;
}

void symengine_mark_destructing()
{
    g_php_destructing = true;
}
