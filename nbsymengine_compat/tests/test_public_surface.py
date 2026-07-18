"""Test that the public surface of symengine_py_compat is unchanged."""
from __future__ import annotations

import pytest


_EXPECTED_PUBLIC_NAMES = {
    'ACos', 'ACosh', 'ACot', 'ACoth', 'ACsc', 'ACsch', 'ASec', 'ASech',
    'ASin', 'ASinh', 'ATan', 'ATan2', 'ATanh', 'Abs', 'Add', 'And', 'Basic',
    'Beta', 'Boolean', 'BooleanAtom', 'CCodePrinter', 'Catalan', 'Ceiling',
    'Complement', 'ComplexDouble', 'ComplexMPC', 'Complexes', 'ConditionSet',
    'Conjugate', 'Constant', 'Contains', 'Cos', 'Cosh', 'Cot', 'Coth', 'Csc',
    'Csch', 'DenseMatrix', 'DenseMatrixWrapper', 'Derivative', 'DictBasic',
    'Dirichlet_eta', 'Dummy', 'E', 'EmptySet', 'Eq', 'Equality', 'Erf',
    'Erfc', 'EulerGamma', 'FiniteSet', 'Float', 'Floor', 'Fraction',
    'Function', 'FunctionSymbol', 'Gamma', 'Ge', 'GoldenRatio', 'Gt',
    'HAS_SYMPY', 'I', 'ImageSet', 'ImmutableDenseMatrix', 'ImmutableMatrix',
    'ImmutableSparseMatrix', 'Integer', 'Integers', 'Integral', 'Intersection',
    'Interval', 'KroneckerDelta', 'Lambda', 'Lambdify', 'LambertW', 'Le',
    'LessThan', 'LeviCivita', 'Log', 'LogGamma', 'LowerGamma', 'Lt', 'Matrix',
    'Max', 'Min', 'Mul', 'MutableDenseMatrix', 'MutableSparseMatrix', 'Nand',
    'Naturals', 'Naturals0', 'Ne', 'NonSquareMatrixError', 'Nor', 'Not',
    'Number', 'One', 'Or', 'Piecewise', 'PolyGamma', 'Pow', 'Product',
    'PyFunction', 'PyNumber', 'Rational', 'Rational_type', 'Rationals',
    'RealDouble', 'RealMPFR', 'Reals', 'Relational', 'S', 'Sec', 'Sech',
    'SeriesCoeffInterface', 'Set', 'ShapeError', 'Sieve', 'Sieve_iterator',
    'Sign', 'Sin', 'Sinh', 'SparseMatrix', 'StrictLessThan', 'Subs', 'Sum',
    'Symbol', 'Symbol_function', 'SympifyError', 'Tan', 'Tanh', 'Truncate',
    'Unequality', 'UnevaluatedExpr', 'Union', 'UniversalSet', 'UpperGamma',
    'Xnor', 'Xor', 'Zeta', 'abs', 'acos', 'acosh', 'acot', 'acoth', 'acsc',
    'acsch', 'add', 'add_as_coefficients_dict', 'annotations',
    'apply_compat_patches', 'asec', 'asech', 'asin', 'asinh', 'atan',
    'atan2', 'atanh', 'basic_as_coefficients_dict', 'basic_as_numer_denom',
    'basic_as_powers_dict', 'basic_as_real_imag', 'basic_atoms',
    'basic_diff', 'basic_eq', 'basic_free_symbols', 'basic_has',
    'basic_msubs', 'basic_n', 'basic_ne', 'basic_subs', 'basic_xreplace',
    'bernoulli', 'beta', 'binomial', 'carmichael', 'cartes', 'cast_to_number',
    'ccode', 'ceiling', 'collections', 'complexes', 'conditionset',
    'conjugate', 'contains', 'cos', 'cosh', 'cot', 'coth', 'count_ops',
    'cpp_use_count', 'crt', 'csc', 'csch', 'cse', 'diag', 'diff',
    'digamma', 'dirichlet_eta', 'div', 'divides', 'drop_rcps_on_cpp_threads',
    'e', 'e_fn', 'emptyset', 'erf', 'erfc', 'euler_gamma', 'euler_gamma_fn',
    'exp', 'expand', 'eye', 'factor', 'factor_lehman_method',
    'factor_pollard_pm1_method', 'factor_pollard_rho_method',
    'factor_trial_division', 'factorial', 'false', 'false_const',
    'fibonacci', 'fibonacci2', 'finiteset', 'floor', 'from_sympy',
    'function_symbol', 'functools', 'gamma', 'gcd', 'gcd_ext', 'harmonic',
    'has_basic', 'has_symbol', 'have_flint', 'have_llvm',
    'have_llvm_long_double', 'have_mpc', 'have_mpfr', 'have_numpy',
    'have_piranha', 'imageset', 'init_printing', 'integer',
    'integer_nthroot', 'integers', 'interval', 'is_square', 'isprime',
    'jacobi', 'kronecker', 'lambdify', 'lambertw', 'latex', 'lcm',
    'legendre', 'limit', 'linsolve', 'log', 'loggamma', 'logical_and',
    'logical_not', 'logical_or', 'logical_xor', 'lowergamma', 'lucas',
    'lucas2', 'mod', 'mod_f', 'mod_inverse', 'msubs', 'mul',
    'mul_as_coefficients_dict', 'mul_as_powers_dict', 'multiplicative_order',
    'name', 'nan', 'nan_const', 'naturals', 'naturals0',
    'nb_isinstance_DenseMatrix', 'neg', 'nextprime', 'nthroot_mod',
    'nthroot_mod_list', 'obj', 'one', 'ones', 'oo', 'perfect_power', 'pi',
    'pi_fn', 'polygamma', 'pow', 'pow_as_powers_dict', 'powermod',
    'powermod_list', 'prime_factor_multiplicities', 'prime_factors',
    'primitive_root', 'primitive_root_list', 'probab_prime_p', 'quotient',
    'quotient_f', 'quotient_mod', 'quotient_mod_f', 'rationals', 're',
    'real_double', 'reals', 'sage_module', 'same_object', 'sec', 'sech',
    'series', 'set_complement', 'set_intersection', 'set_union', 'sign',
    'sin', 'sinh', 'solve', 'sqrt', 'sqrt_mod', 'str', 'string', 'sub',
    'subs', 'symarray', 'symbol', 'symbols', 'sympify', 'tan', 'tanh',
    'to_sympy', 'totient', 'trigamma', 'true', 'true_const',
    'unevaluated_expr', 'unicode', 'universalset', 'unwrap', 'uppergamma',
    'var', 'wrap', 'wrap_sage_function', 'xreplace', 'zero', 'zeros', 'zeta',
    'zoo',
}


def test_public_surface_snapshot():
    """Verify the public API surface of symengine_py_compat is unchanged."""
    from nbsymengine_compat import symengine_py_compat as m
    actual = {n for n in dir(m) if not n.startswith('_')}
    assert actual == _EXPECTED_PUBLIC_NAMES, (
        f"Public surface changed.\n"
        f"Missing: {sorted(_EXPECTED_PUBLIC_NAMES - actual)}\n"
        f"Extra: {sorted(actual - _EXPECTED_PUBLIC_NAMES)}"
    )
