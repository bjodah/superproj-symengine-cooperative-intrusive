# Shared binding specification

`api.yaml` is the small declarative description of the C++ API exposed by the
language wrappers. It is intentionally not a second copy of SymEngine's C++
signatures: every entry names the owning header and validation uses srcML to
verify the selected free-function overload or constant declaration.

Run validation from the super-project root:

```bash
python -m tools.binding_codegen validate
```

The YAML is parsed once into `tools.binding_codegen.model.BindingSpec`; future
renderers must consume that typed model rather than arbitrary YAML mappings.

Each function requires an `id`, exactly one C++ selector (`cpp.name` or
`cpp.expression`), its header, `arguments`, `returns`, adapter `behavior`, and
`expose` languages. Type identifiers refer to `types`. Schema version 1 admits
only the proven adapter families: `singleton`, `unary_basic`, `binary_basic`,
`binary_boolean`, `integer_unary`, `integer_binary`,
`status_optional_unary`, and `list_integer_to_basic`.

Names default to the ID for Python and Perl, `symengine_` plus the ID for PHP,
and lower camel case for Swift and Java. Add `names.<language>` only for a real
public API divergence. Validation rejects duplicate resolved names and reserved
words unless the latter has an explicit name override (Perl's `sub` is the
intentional example).

Do not add raw C++ snippets, templates, ownership operations, language runtime
pointers, or exception policy to this file. Those remain renderer/runtime
concerns. Version 1 also rejects argument defaults: introduce a supported
adapter family first, then document and implement its default-value policy.
