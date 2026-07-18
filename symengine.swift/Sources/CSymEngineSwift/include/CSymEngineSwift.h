#ifndef C_SYMENGINE_SWIFT_H
#define C_SYMENGINE_SWIFT_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef const void *symengine_swift_basic_ref;
typedef void (*symengine_swift_ref_hook)(void *);

typedef enum symengine_swift_status {
    SYMENGINE_SWIFT_OK = 0,
    SYMENGINE_SWIFT_INVALID_ARGUMENT = 1,
    SYMENGINE_SWIFT_RUNTIME_ERROR = 2,
    SYMENGINE_SWIFT_OUT_OF_MEMORY = 3,
} symengine_swift_status;

typedef enum symengine_swift_basic_kind {
    SYMENGINE_SWIFT_BASIC = 0,
    SYMENGINE_SWIFT_INTEGER = 1,
    SYMENGINE_SWIFT_SYMBOL = 2,
} symengine_swift_basic_kind;

/*
 * Install Swift ARC hooks. The C++ implementation adapts these ordinary C
 * callbacks to the noexcept callbacks required by cooperative_intrusive.
 */
symengine_swift_status
symengine_swift_initialize(symengine_swift_ref_hook retain_hook,
                           symengine_swift_ref_hook release_hook);

const char *symengine_swift_version(void);
const char *symengine_swift_last_error(void);

/* Result-producing functions return one owned cooperative reference. */
symengine_swift_basic_ref symengine_swift_symbol(const char *name);
symengine_swift_basic_ref symengine_swift_integer(int64_t value);

symengine_swift_status
symengine_swift_equal(symengine_swift_basic_ref left,
                      symengine_swift_basic_ref right, int *result);
symengine_swift_status
symengine_swift_string(symengine_swift_basic_ref value, char **result);
void symengine_swift_string_free(char *value);

/* Cooperative wrapper adoption and finalization support. */
symengine_swift_status symengine_swift_wrapper_lock(void);
void symengine_swift_wrapper_unlock(void);
void *symengine_swift_external_owner(symengine_swift_basic_ref value);
symengine_swift_status
symengine_swift_externalize(symengine_swift_basic_ref value, void *owner);
void symengine_swift_release_owned(symengine_swift_basic_ref value);
void symengine_swift_delete_external(symengine_swift_basic_ref value,
                                     void *expected_owner);
symengine_swift_basic_kind
symengine_swift_kind(symengine_swift_basic_ref value);
int symengine_swift_is_external_owned(symengine_swift_basic_ref value);

#ifdef __cplusplus
}
#endif

#endif
