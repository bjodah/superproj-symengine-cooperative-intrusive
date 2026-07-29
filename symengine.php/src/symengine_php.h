#ifndef SYMENGINE_PHP_H
#define SYMENGINE_PHP_H

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "php.h"
#include "php_ini.h"
#include "ext/standard/info.h"
#include "zend_exceptions.h"
#include "zend_interfaces.h"

#include <symengine/symengine_config.h>
#include <symengine/basic.h>
#include <symengine/integer.h>
#include <symengine/symbol.h>
#include <symengine/constants.h>
#include <symengine/infinity.h>
#include <symengine/nan.h>
#include <symengine/add.h>
#include <symengine/functions.h>
#include <symengine/logic.h>
#include <symengine/mul.h>
#include <symengine/ntheory.h>
#include <symengine/pow.h>
#include <symengine/symengine_exception.h>
#include <symengine/symengine_rcp.h>

#include <vector>

#if !defined(WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP)
#error "The SymEngine PHP extension requires SYMENGINE_RCP_BACKEND=cooperative_intrusive."
#endif

#define PHP_SYMENGINE_VERSION "0.1.0"
#define PHP_SYMENGINE_EXTNAME "symengine"

typedef struct _symengine_object {
    const SymEngine::Basic *ptr;
    zend_object std;
} symengine_object;

extern zend_class_entry *symengine_ce_basic;
extern zend_class_entry *symengine_ce_integer;
extern zend_class_entry *symengine_ce_symbol;

extern zend_object_handlers symengine_object_handlers;

symengine_object *symengine_object_from_obj(zend_object *obj);
zend_object *symengine_basic_new(zend_class_entry *ce);
void symengine_basic_free_obj(zend_object *object);

void symengine_register_cooperative_hooks();
bool symengine_is_destructing();
void symengine_mark_destructing();
void symengine_seed_singletons();
void symengine_reconcile_singletons();

void symengine_register_basic_class();
void symengine_register_integer_class();
void symengine_register_symbol_class();

zend_class_entry *symengine_class_for_basic(const SymEngine::Basic *basic);
void symengine_wrap_basic(zval *return_value,
                          const SymEngine::RCP<const SymEngine::Basic> &value);
// Generic list-result spelling: a PHP array of wrapped Basic objects.  Nothing
// here is entry-specific; "no result" needs no helper because it is RETURN_NULL.
void symengine_wrap_basic_list(
    zval *return_value,
    const std::vector<SymEngine::RCP<const SymEngine::Basic>> &values);
SymEngine::RCP<const SymEngine::Basic> symengine_unwrap_basic(zval *obj);

PHP_MINIT_FUNCTION(symengine);
PHP_MSHUTDOWN_FUNCTION(symengine);
PHP_RINIT_FUNCTION(symengine);
PHP_RSHUTDOWN_FUNCTION(symengine);
PHP_MINFO_FUNCTION(symengine);

PHP_FUNCTION(symengine_zero);
PHP_FUNCTION(symengine_one);
PHP_FUNCTION(symengine_pi);
PHP_FUNCTION(symengine_integer);
PHP_FUNCTION(symengine_symbol);
PHP_FUNCTION(symengine_add);
PHP_FUNCTION(symengine_sub);
PHP_FUNCTION(symengine_div);
PHP_FUNCTION(symengine_mul);
PHP_FUNCTION(symengine_neg);
PHP_FUNCTION(symengine_pow);
PHP_FUNCTION(symengine_str);
PHP_FUNCTION(symengine_eq);

#endif
