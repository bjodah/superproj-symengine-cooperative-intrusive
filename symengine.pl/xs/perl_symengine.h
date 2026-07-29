#pragma once

#include "EXTERN.h"
#include "perl.h"
#include "XSUB.h"

#ifdef seed
#undef seed
#endif

#include <symengine/basic.h>
#include <symengine/symengine_rcp.h>

#include <vector>

namespace SymEnginePerl {

// The holder lives inside the blessed inner SV and stores a *raw* pointer to
// the SymEngine object.  Ownership is cooperative: each wrapped object is
// handed off to the cooperative_intrusive counter via set_self_external(), so
// the inner SV itself becomes the object's reference-count anchor.  The C++
// object is deleted from DESTROY once the inner SV's SvREFCNT reaches zero.
struct BasicHolder {
    const SymEngine::Basic *ptr;
};

void initialize();
SV *wrap_basic(const SymEngine::RCP<const SymEngine::Basic> &value);
SV *wrap_basic_perl_owned(const SymEngine::RCP<const SymEngine::Basic> &value);
// Generic result shapes an entry can have besides a single expression: Perl's
// undef for "no result", and a reference to an array of wrapped handles for a
// list result.  Both are per-language spellings only; no entry-specific code.
SV *undefined();
SV *wrap_basic_list(const std::vector<SymEngine::RCP<const SymEngine::Basic>> &values);
SymEngine::RCP<const SymEngine::Basic> unwrap_basic(SV *sv);
std::string stringify(SV *sv);
bool equals(SV *left, SV *right);
bool same_object(SV *left, SV *right);
unsigned int cpp_use_count(SV *sv);
unsigned int perl_refcount(SV *sv);
bool is_external_owned(SV *sv);
void destroy_basic(SV *sv);

} // namespace SymEnginePerl
