"""
Original work Copyright 2024 The Ray Optics Simulation authors and contributors
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

"""
Equation evaluation module using SymPy.

This module provides functionality to evaluate LaTeX mathematical expressions,
replacing the JavaScript evaluatex library with Python's SymPy.

Key features:
- Parses LaTeX mathematical notation (e.g., \\sin(t), \\pi, \\frac{a}{b})
- Handles implicit multiplication (e.g., "2t" → "2*t")
- Supports common mathematical functions and constants
- Returns callable Python functions for efficient evaluation
- No dependency on antlr4 (uses SymPy's parse_expr with transformations)
"""

import sympy as sp
import math
import re
from typing import Callable, Dict, Any
from functools import lru_cache
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor
)


# Define sech as a SymPy function for symbolic computation
# This allows it to work with both symbolic expressions and numeric values
class sech(sp.Function):
    """
    Hyperbolic secant function as a SymPy function.

    This is needed to make tanh work in GRIN lens, whose derivative is sech^2.
    Defined as 1/cosh(x).
    """

    @classmethod
    def eval(cls, x):
        """Evaluate sech symbolically."""
        # For numeric values, compute directly
        if x.is_Number:
            return 1 / sp.cosh(x)
        # For symbolic expressions, return unevaluated
        return None

    def _eval_evalf(self, prec):
        """Evaluate numerically."""
        return (1 / sp.cosh(self.args[0])).evalf(prec)


# Helper function for numeric evaluation (used in lambdify)
def sech_numeric(x):
    """Numeric sech function for use in lambdify."""
    return 1.0 / math.cosh(x)


# Default constants and functions available in expressions
DEFAULT_CONTEXT = {
    'pi': math.pi,
    'e': math.e,
    'PI': math.pi,
    'E': math.e,
    'sech': sech,  # SymPy function for symbolic computation
}


def preprocess_latex(latex: str) -> str:
    """
    Preprocess LaTeX string to replace special operators and functions.

    This function converts LaTeX notation to a format suitable for SymPy's sympify parser.
    It converts LaTeX to standard mathematical notation.

    Args:
        latex: LaTeX expression string

    Returns:
        Preprocessed string suitable for sympify

    Raises:
        ValueError: If LaTeX contains malformed constructs
    """
    # Replace operators and functions with SymPy-compatible equivalents
    replacements = {
        # Basic operators
        r'\cdot': '*',
        r'\times': '*',

        # Constants
        r'\pi': 'pi',
        r'\mathrm{e}': 'E',

        # Logarithm and exponential
        r'\log': 'log',
        r'\ln': 'log',
        r'\exp': 'exp',

        # Trigonometric functions
        r'\sin': 'sin',
        r'\cos': 'cos',
        r'\tan': 'tan',
        r'\arcsin': 'asin',
        r'\arccos': 'acos',
        r'\arctan': 'atan',

        # Hyperbolic functions
        r'\sinh': 'sinh',
        r'\cosh': 'cosh',
        r'\tanh': 'tanh',

        # Inverse hyperbolic functions
        r'\operatorname{asin}': 'asin',
        r'\operatorname{acos}': 'acos',
        r'\operatorname{atan}': 'atan',
        r'\operatorname{asinh}': 'asinh',
        r'\operatorname{acosh}': 'acosh',
        r'\operatorname{atanh}': 'atanh',
        r'\operatorname{arcsinh}': 'asinh',
        r'\operatorname{arccosh}': 'acosh',
        r'\operatorname{arctanh}': 'atanh',

        # Special functions
        r'\operatorname{floor}': 'floor',
        r'\operatorname{ceil}': 'ceiling',
        r'\operatorname{round}': 'round',
        r'\operatorname{trunc}': 'trunc',
        r'\operatorname{sign}': 'sign',
        r'\operatorname{sgn}': 'sign',
        r'\max': 'Max',
        r'\min': 'Min',
        r'\operatorname{abs}': 'Abs',

        # Absolute value
        r'\left|': 'Abs(',
        r'\right|': ')',

        # Custom functions
        r'\mathrm{sech}': 'sech',

        # Brackets (convert to parentheses)
        r'\left(': '(',
        r'\right)': ')',
        r'\left[': '(',
        r'\right]': ')',
        r'\left\{': '(',
        r'\right\}': ')',
    }

    result = latex
    for old, new in replacements.items():
        result = result.replace(old, new)

    # Handle power notation: \sin^2(t) -> (sin(t))**2
    # This needs to be done AFTER replacing \sin with sin, but BEFORE replacing ^ with **
    # We need to match the function with its complete argument list

    # Function to handle power notation with proper parenthesis matching
    def replace_power_notation(text):
        """Replace sin^2(x) with (sin(x))**2, handling nested parentheses."""
        funcs = r'(sin|cos|tan|sec|csc|cot|sinh|cosh|tanh|sech|csch|coth|log|ln|exp|sqrt)'
        pattern = re.compile(rf'{funcs}\s*\^(\{{)?(\d+)(\}})?', re.IGNORECASE)

        match = pattern.search(text)
        while match:
            func_name = match.group(1)
            power = match.group(3)
            start_idx = match.start()
            end_idx = match.end()

            # Find the argument list after the function
            # Look for opening parenthesis
            i = end_idx
            while i < len(text) and text[i].isspace():
                i += 1

            if i < len(text) and text[i] == '(':
                # Count parentheses to find matching close
                paren_count = 1
                j = i + 1
                while j < len(text) and paren_count > 0:
                    if text[j] == '(':
                        paren_count += 1
                    elif text[j] == ')':
                        paren_count -= 1
                    j += 1

                # Extract the argument list including parentheses
                args = text[i:j]
                # Replace with (func(args))**power
                replacement = f'({func_name}{args})**{power}'
                text = text[:start_idx] + replacement + text[j:]
            else:
                # No arguments found, just move forward (shouldn't happen in valid input)
                break

            # Search for next match
            match = pattern.search(text, start_idx + len(replacement))

        return text

    result = replace_power_notation(result)

    # Handle square roots: \sqrt{x} -> sqrt(x)
    while r'\sqrt' in result:
        # Match \sqrt{...} with proper brace counting
        match = re.search(r'\\sqrt\{', result)
        if not match:
            break

        start_idx = match.start()
        brace_start = match.end() - 1  # Position of '{'

        # Count braces to find matching closing brace
        brace_count = 1
        i = brace_start + 1
        while i < len(result) and brace_count > 0:
            if result[i] == '{':
                brace_count += 1
            elif result[i] == '}':
                brace_count -= 1
            i += 1

        if brace_count != 0:
            raise ValueError(f"Malformed \\sqrt: unmatched braces in '{latex}'")

        content = result[brace_start + 1:i - 1]
        result = result[:start_idx] + f'sqrt({content})' + result[i:]

    # Handle fractions: \frac{a}{b} -> (a)/(b)
    while r'\frac' in result:
        frac_idx = result.find(r'\frac')
        if frac_idx == -1:
            break

        # Find the numerator {...}
        start_num = result.find('{', frac_idx)
        if start_num == -1:
            raise ValueError(f"Malformed \\frac: missing opening brace for numerator in '{latex}'")

        brace_count = 1
        end_num = start_num + 1
        while end_num < len(result) and brace_count > 0:
            if result[end_num] == '{':
                brace_count += 1
            elif result[end_num] == '}':
                brace_count -= 1
            end_num += 1

        if brace_count != 0:
            raise ValueError(f"Malformed \\frac: unmatched braces in numerator in '{latex}'")

        numerator = result[start_num + 1:end_num - 1]

        # Find the denominator {...}
        start_den = end_num
        if start_den >= len(result) or result[start_den] != '{':
            raise ValueError(f"Malformed \\frac: missing denominator in '{latex}'")

        brace_count = 1
        end_den = start_den + 1
        while end_den < len(result) and brace_count > 0:
            if result[end_den] == '{':
                brace_count += 1
            elif result[end_den] == '}':
                brace_count -= 1
            end_den += 1

        if brace_count != 0:
            raise ValueError(f"Malformed \\frac: unmatched braces in denominator in '{latex}'")

        denominator = result[start_den + 1:end_den - 1]

        # Replace \frac{...}{...} with (...)/(...)
        result = result[:frac_idx] + f'(({numerator})/({denominator}))' + result[end_den:]

    # Handle exponents: x^{...} -> x**(...)
    # SymPy uses ** for exponentiation, not ^
    result = result.replace('^', '**')

    # Now handle remaining braces - convert to parentheses
    # Be careful not to break things that are already correct
    while '{' in result:
        result = result.replace('{', '(', 1).replace('}', ')', 1)

    return result


@lru_cache(maxsize=128)
def _evaluate_latex_cached(latex: str, context_tuple: tuple = None) -> Callable:
    """
    Internal cached version of evaluate_latex.
    Uses tuple for context to make it hashable for caching.
    """
    # Convert context tuple back to dict
    additional_context = dict(context_tuple) if context_tuple else None
    return _evaluate_latex_impl(latex, additional_context)


def _evaluate_latex_impl(latex: str, additional_context: Dict[str, Any] = None) -> Callable:
    """
    Evaluate a LaTeX mathematical expression and return a callable function.

    This function parses LaTeX math expressions and returns a Python function that can
    be called with variable values. It's the Python equivalent of the JavaScript
    evaluatex library.

    Args:
        latex: LaTeX expression string (e.g., "t^2 + 2t + 1")
        additional_context: Additional variables/functions to make available in the expression

    Returns:
        A callable function that takes keyword arguments for variables

    Example:
        >>> fn = evaluate_latex("t^2 + 2t + 1")
        >>> result = fn(t=3)  # Returns 16

        >>> fn_xy = evaluate_latex("x^2 + y^2")
        >>> result = fn_xy(x=3, y=4)  # Returns 25
    """
    # Preprocess the LaTeX
    preprocessed = preprocess_latex(latex)

    try:
        # Combine default context with additional context
        context = DEFAULT_CONTEXT.copy()
        if additional_context:
            context.update(additional_context)

        # Parse the expression using parse_expr with implicit multiplication support
        # Create symbols for common variables
        locals_dict = {
            't': sp.Symbol('t'),
            'x': sp.Symbol('x'),
            'y': sp.Symbol('y'),
            'z': sp.Symbol('z'),
            'r': sp.Symbol('r'),
            'theta': sp.Symbol('theta'),
            'phi': sp.Symbol('phi'),
        }
        locals_dict.update(context)

        # Use parse_expr with transformations for implicit multiplication
        # This allows expressions like "2t" to be interpreted as "2*t"
        transformations = standard_transformations + (implicit_multiplication_application, convert_xor)
        expr = parse_expr(preprocessed, local_dict=locals_dict, transformations=transformations)

        # Get the free symbols (variables) in the expression
        symbols = expr.free_symbols

        # Filter out known constants (they shouldn't be treated as variables)
        constant_names = {'pi', 'e', 'E', 'PI'}
        symbols = {s for s in symbols if s.name not in constant_names}

        # Create a lambdified function
        # Convert SymPy expression to a numerical function
        if symbols:
            # Sort symbols by name for consistent parameter order
            sorted_symbols = sorted(symbols, key=lambda s: s.name)

            # Lambdify the expression with math module for better performance
            # Create custom namespace with our custom functions
            # Use sech_numeric for lambdify (numeric evaluation)
            custom_namespace = {
                'sech': sech_numeric,  # Use numeric version for lambdify
                'pi': math.pi,
                'e': math.e,
                'E': math.e,
                'PI': math.pi,
            }

            func = sp.lambdify(sorted_symbols, expr, modules=[custom_namespace, 'math'])

            # Create a wrapper that accepts keyword arguments
            def wrapper(**kwargs):
                # Extract values for each symbol in the correct order
                args = []
                for sym in sorted_symbols:
                    if sym.name not in kwargs:
                        raise ValueError(f"Missing required variable: {sym.name}")
                    args.append(kwargs[sym.name])

                return func(*args)

            return wrapper
        else:
            # Expression has no variables, just return the constant value
            value = float(expr.evalf(subs={sp.Symbol(k): v for k, v in context.items() if isinstance(v, (int, float))}))
            return lambda **_kwargs: value

    except Exception as e:
        # If parsing fails, try to provide helpful error message
        raise ValueError(f"Failed to parse expression '{latex}' (preprocessed: '{preprocessed}'): {str(e)}")


def evaluate_latex(latex: str, additional_context: Dict[str, Any] = None) -> Callable:
    """
    Evaluate a LaTeX mathematical expression and return a callable function.

    This is the public interface that wraps the cached implementation.
    Results are cached for performance - repeated calls with the same LaTeX expression
    will return the cached compiled function.

    Args:
        latex: LaTeX expression string (e.g., "t^2 + 2t + 1")
        additional_context: Additional variables/functions to make available in the expression

    Returns:
        A callable function that takes keyword arguments for variables

    Example:
        >>> fn = evaluate_latex("t^2 + 2t + 1")
        >>> result = fn(t=3)  # Returns 16
    """
    # Convert dict to tuple for caching (dicts aren't hashable)
    context_tuple = tuple(sorted(additional_context.items())) if additional_context else None
    return _evaluate_latex_cached(latex, context_tuple)


# Convenience function for single-variable expressions
def evaluate_latex_single_var(latex: str, var_name: str = 't') -> Callable[[float], float]:
    """
    Evaluate a LaTeX expression with a single variable.

    This is a convenience function for the common case of single-variable expressions.

    Args:
        latex: LaTeX expression string
        var_name: Name of the variable (default: 't')

    Returns:
        A function that takes a single float argument

    Example:
        >>> fn = evaluate_latex_single_var("t^2 + 2t + 1")
        >>> result = fn(3.0)  # Returns 16.0
    """
    multi_var_fn = evaluate_latex(latex)

    def single_var_fn(value: float) -> float:
        return multi_var_fn(**{var_name: value})

    return single_var_fn


# Example usage and testing
if __name__ == "__main__":
    print("Testing equation evaluation with SymPy:")
    print("=" * 50)

    # Test 1: Simple polynomial
    print("\nTest 1: Simple polynomial")
    latex1 = "t^2 + 2t + 1"
    fn1 = evaluate_latex(latex1)
    for t in [0, 1, 2, 3]:
        result = fn1(t=t)
        expected = t**2 + 2*t + 1
        print(f"  t={t}: fn(t) = {result}, expected = {expected}, match = {abs(result - expected) < 1e-10}")

    # Test 2: Trigonometric functions
    print("\nTest 2: Trigonometric functions")
    latex2 = r"\sin(t) + \cos(t)"
    fn2 = evaluate_latex(latex2)
    for t in [0, math.pi/4, math.pi/2]:
        result = fn2(t=t)
        expected = math.sin(t) + math.cos(t)
        print(f"  t={t:.4f}: fn(t) = {result:.6f}, expected = {expected:.6f}, match = {abs(result - expected) < 1e-10}")

    # Test 3: Special constants
    print("\nTest 3: Special constants")
    latex3 = r"\pi \cdot t"
    fn3 = evaluate_latex(latex3)
    result = fn3(t=2)
    expected = math.pi * 2
    print(f"  t=2: fn(t) = {result:.6f}, expected = {expected:.6f}, match = {abs(result - expected) < 1e-10}")

    # Test 4: Exponential and logarithm
    print("\nTest 4: Exponential and logarithm")
    latex4 = r"\exp(t) + \log(t+1)"
    fn4 = evaluate_latex(latex4)
    for t in [0, 1, 2]:
        result = fn4(t=t)
        expected = math.exp(t) + math.log(t+1)
        print(f"  t={t}: fn(t) = {result:.6f}, expected = {expected:.6f}, match = {abs(result - expected) < 1e-10}")

    # Test 5: Hyperbolic functions
    print("\nTest 5: Hyperbolic functions (sech)")
    latex5 = r"\mathrm{sech}(t)"
    fn5 = evaluate_latex(latex5)
    for t in [0, 0.5, 1]:
        result = fn5(t=t)
        expected = sech_numeric(t)  # Use numeric version for comparison
        print(f"  t={t}: fn(t) = {result:.6f}, expected = {expected:.6f}, match = {abs(result - expected) < 1e-10}")

    # Test 6: Multi-variable expression
    print("\nTest 6: Multi-variable expression")
    latex6 = "x^2 + y^2"
    fn6 = evaluate_latex(latex6)
    result = fn6(x=3, y=4)
    expected = 3**2 + 4**2
    print(f"  x=3, y=4: fn(x,y) = {result}, expected = {expected}, match = {abs(result - expected) < 1e-10}")

    # Test 7: Preprocessed operators
    print("\nTest 7: LaTeX operators")
    latex7 = r"t \cdot 2"
    fn7 = evaluate_latex(latex7)
    result = fn7(t=5)
    expected = 5 * 2
    print(f"  t=5: fn(t) = {result}, expected = {expected}, match = {abs(result - expected) < 1e-10}")

    # Test 8: Single variable convenience function
    print("\nTest 8: Single variable convenience function")
    latex8 = "t^3 - 2t + 1"
    fn8 = evaluate_latex_single_var(latex8)
    result = fn8(2.0)
    expected = 2**3 - 2*2 + 1
    print(f"  t=2.0: fn(2.0) = {result}, expected = {expected}, match = {abs(result - expected) < 1e-10}")

    # Test 9: Square root
    print("\nTest 9: Square root")
    latex9 = r"\sqrt{t}"
    fn9 = evaluate_latex(latex9)
    for t in [1, 4, 9]:
        result = fn9(t=t)
        expected = math.sqrt(t)
        print(f"  t={t}: fn(t) = {result:.6f}, expected = {expected:.6f}, match = {abs(result - expected) < 1e-10}")

    # Test 10: Power notation (sin^2)
    print("\nTest 10: Power notation (sin^2)")
    latex10 = r"\sin^2(t) + \cos^2(t)"
    fn10 = evaluate_latex(latex10)
    for t in [0, math.pi/4, math.pi/2]:
        result = fn10(t=t)
        expected = math.sin(t)**2 + math.cos(t)**2  # Should be 1
        print(f"  t={t:.4f}: fn(t) = {result:.6f}, expected = {expected:.6f}, match = {abs(result - expected) < 1e-10}")

    # Test 11: Fraction
    print("\nTest 11: Fraction")
    latex11 = r"\frac{1}{t}"
    fn11 = evaluate_latex(latex11)
    for t in [1, 2, 4]:
        result = fn11(t=t)
        expected = 1.0 / t
        print(f"  t={t}: fn(t) = {result:.6f}, expected = {expected:.6f}, match = {abs(result - expected) < 1e-10}")

    # Test 12: Caching performance
    print("\nTest 12: Caching performance")
    import time
    latex12 = "t^3 + 5*t^2 - 3*t + 7"

    # First call (not cached)
    start = time.time()
    fn12a = evaluate_latex(latex12)
    first_time = time.time() - start

    # Second call (cached)
    start = time.time()
    fn12b = evaluate_latex(latex12)
    second_time = time.time() - start

    print(f"  First call:  {first_time*1000:.3f} ms")
    print(f"  Second call: {second_time*1000:.3f} ms (cached)")
    if second_time > 0:
        print(f"  Speedup: {first_time/second_time:.1f}x")
    else:
        print(f"  Speedup: >1000x (too fast to measure)")
    print(f"  Same function object: {fn12a is fn12b}")

    # Test 13: Error handling - malformed fraction
    print("\nTest 13: Error handling - malformed fraction")
    try:
        latex13 = r"\frac{1}"  # Missing denominator
        fn13 = evaluate_latex(latex13)
        print("  ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"  Correctly raised ValueError: {str(e)[:60]}...")

    print("\n" + "=" * 50)
    print("All tests completed!")
