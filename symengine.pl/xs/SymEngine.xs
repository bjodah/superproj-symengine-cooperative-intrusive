#include "EXTERN.h"
#include "perl.h"
#include "XSUB.h"

#include "perl_symengine.h"

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

#include <exception>
#include <string>

static void croak_current_exception()
{
    try {
        throw;
    } catch (const std::exception &e) {
        croak("%s", e.what());
    } catch (...) {
        croak("unknown C++ exception");
    }
}

MODULE = SymEngine  PACKAGE = SymEngine

PROTOTYPES: DISABLE

BOOT:
    SymEnginePerl::initialize();

SV *
symbol(name)
    const char *name
  CODE:
    try {
        RETVAL = SymEnginePerl::wrap_basic_perl_owned(
            SymEngine::symbol(std::string(name)));
    } catch (...) {
        croak_current_exception();
    }
  OUTPUT:
    RETVAL

SV *
integer(value)
    IV value
  CODE:
    try {
        RETVAL = SymEnginePerl::wrap_basic_perl_owned(
            SymEngine::integer(static_cast<long>(value)));
    } catch (...) {
        croak_current_exception();
    }
  OUTPUT:
    RETVAL

INCLUDE: SymEngine.generated.xs.inc

bool
same_object(left, right)
    SV *left
    SV *right
  CODE:
    try {
        RETVAL = SymEnginePerl::same_object(left, right);
    } catch (...) {
        croak_current_exception();
    }
  OUTPUT:
    RETVAL

unsigned int
cpp_use_count(value)
    SV *value
  CODE:
    try {
        RETVAL = SymEnginePerl::cpp_use_count(value);
    } catch (...) {
        croak_current_exception();
    }
  OUTPUT:
    RETVAL

unsigned int
perl_refcount(value)
    SV *value
  CODE:
    try {
        RETVAL = SymEnginePerl::perl_refcount(value);
    } catch (...) {
        croak_current_exception();
    }
  OUTPUT:
    RETVAL

bool
is_external_owned(value)
    SV *value
  CODE:
    try {
        RETVAL = SymEnginePerl::is_external_owned(value);
    } catch (...) {
        croak_current_exception();
    }
  OUTPUT:
    RETVAL

MODULE = SymEngine  PACKAGE = SymEngine::Basic

SV *
_stringify(self)
    SV *self
  CODE:
    try {
        const std::string result = SymEnginePerl::stringify(self);
        RETVAL = newSVpv(result.c_str(), result.size());
    } catch (...) {
        croak_current_exception();
    }
  OUTPUT:
    RETVAL

bool
_equals(self, other)
    SV *self
    SV *other
  CODE:
    try {
        RETVAL = SymEnginePerl::equals(self, other);
    } catch (...) {
        croak_current_exception();
    }
  OUTPUT:
    RETVAL

void
DESTROY(self)
    SV *self
  CODE:
    SymEnginePerl::destroy_basic(self);
