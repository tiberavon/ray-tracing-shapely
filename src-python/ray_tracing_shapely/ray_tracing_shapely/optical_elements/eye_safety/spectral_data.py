"""
Python-specific module: Spectral power distributions (Eye safety framework)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

===============================================================================
PYTHON-SPECIFIC MODULE: SpectralPowerDistribution
===============================================================================
A tabulated (wavelength, value) spectrum -- spectral irradiance (W/m^2/nm)
or spectral radiance (W/(m^2*sr*nm)) -- plus `integrate()` against a hazard
weighting function, the prerequisite for IEC
62471's broadband exposure-limit equations (Eq. 4.1 and its siblings are
all `Sum E_lambda(lambda,t) * hazard_fn(lambda) * dt * dlambda` over a
source's spectrum). Not needed for IEC 60825-1's monochromatic laser path,
which takes a single `wavelength_nm` directly.

`interp_log()` is a standalone function, not a `SpectralPowerDistribution`
method, because it is meant for the hazard-weighting tables
(S_UV(lambda), B(lambda), R(lambda) -- always positive, and justified
by Sec. 5.3.1's own text: the weighting curves are "reasonably linear in
any local region on semi-log coordinates," so the standard specifies
"linear interpolation on the log of ... values"), NOT for a source's own
measured spectrum, which can legitimately be zero (e.g. a red LED has no
blue emission) where log() is undefined. `SpectralPowerDistribution.
value_at()` therefore uses plain linear interpolation on the source's own
tabulated values, deliberately not `interp_log()`.

This log-space-vs-linear distinction is C-EYE-01
(dev_doc/architecture/contracts/C-EYE-01.md). Design rationale:
dev_doc/architecture/components/eye_safety.md
===============================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple


def _validate_grid(wavelengths_nm: Sequence[float], values: Sequence[float]) -> None:
    if len(wavelengths_nm) != len(values):
        raise ValueError("wavelengths_nm and values must be the same length.")
    if len(wavelengths_nm) < 2:
        raise ValueError("Need at least 2 points to interpolate.")
    for a, b in zip(wavelengths_nm, wavelengths_nm[1:]):
        if b <= a:
            raise ValueError("wavelengths_nm must be strictly increasing.")


def _bracket_index(wavelengths_nm: Sequence[float], query_nm: float) -> int:
    """Return i such that wavelengths_nm[i] <= query_nm <= wavelengths_nm[i+1].

    Assumes `query_nm` is already known to be within
    [wavelengths_nm[0], wavelengths_nm[-1]].
    """
    n = len(wavelengths_nm)
    if query_nm >= wavelengths_nm[-1]:
        return n - 2
    for i in range(n - 1):
        if wavelengths_nm[i] <= query_nm <= wavelengths_nm[i + 1]:
            return i
    raise ValueError("query_nm not found within domain (unreachable after a bounds check).")


def interp_log(wavelengths_nm: Sequence[float], values: Sequence[float], query_nm: float) -> float:
    """Linear interpolation in log-space, per IEC 62471 Sec. 5.3.1.

    "The weighting curves ... are reasonably linear in any local region on
    semi-log coordinates. Therefore to standardize interpolated values, use
    linear interpolation on the log of given values to obtain intermediate
    points at the wavelength intervals desired ... Anti-logarithm of the
    interpolated numbers result in the values needed for the interpolated
    weighting factors." [IEC 62471 Sec. 5.3.1]

    This matters because it is not a stylistic choice: `S_UV(lambda)`
    changes by 250% over 3 nm near 300 nm [IEC 62471 Annexes A-D], so a plain
    linear interpolation on the raw tabulated values would misrepresent the
    curve's shape between sample points far more than log-linear does.

    Args:
        wavelengths_nm: Strictly increasing wavelength grid, in nm.
        values: Tabulated values at each wavelength. Must all be strictly
            positive -- log-space interpolation is undefined for zero or
            negative values. True for the hazard-weighting functions this
            is meant for (S_UV, B, R); not necessarily true for a measured
            source spectrum (use `SpectralPowerDistribution.value_at`
            for that instead).
        query_nm: Wavelength to interpolate at, in nm.

    Returns:
        The log-interpolated value at `query_nm`.

    Raises:
        ValueError: If `wavelengths_nm`/`values` are malformed (see
            `_validate_grid`), contain a non-positive value, or if
            `query_nm` is outside [wavelengths_nm[0], wavelengths_nm[-1]].
    """
    _validate_grid(wavelengths_nm, values)
    for v in values:
        if v <= 0.0:
            raise ValueError(
                "interp_log requires strictly positive tabulated values "
                "(log-space interpolation is undefined at zero or below)."
            )
    if query_nm < wavelengths_nm[0] or query_nm > wavelengths_nm[-1]:
        raise ValueError(
            f"query_nm={query_nm} is outside the tabulated domain "
            f"[{wavelengths_nm[0]}, {wavelengths_nm[-1]}] nm."
        )

    i = _bracket_index(wavelengths_nm, query_nm)
    w0, w1 = wavelengths_nm[i], wavelengths_nm[i + 1]
    v0, v1 = values[i], values[i + 1]
    if query_nm == w0:
        return v0
    if query_nm == w1:
        return v1
    frac = (query_nm - w0) / (w1 - w0)
    log_v0, log_v1 = math.log10(v0), math.log10(v1)
    return 10.0 ** (log_v0 + frac * (log_v1 - log_v0))


@dataclass
class SpectralPowerDistribution:
    """A tabulated spectral irradiance or spectral radiance distribution.

    Args:
        wavelength_nm: Strictly increasing wavelength grid, in nm.
        values: Spectral value at each wavelength -- W/m^2/nm if
            `quantity='irradiance'`, W/(m^2*sr*nm) if `quantity='radiance'`.
            Same length as `wavelength_nm`. May include zero (unlike
            `interp_log`'s tables).
        quantity: 'irradiance' or 'radiance'.

    Raises:
        ValueError: If the grid is malformed (see `_validate_grid`), or
            `quantity` is not 'irradiance' or 'radiance'.
    """

    wavelength_nm: List[float]
    values: List[float]
    quantity: str

    def __post_init__(self) -> None:
        _validate_grid(self.wavelength_nm, self.values)
        if self.quantity not in ('irradiance', 'radiance'):
            raise ValueError(
                f"quantity must be 'irradiance' or 'radiance', got {self.quantity!r}."
            )

    @property
    def unit(self) -> str:
        """Unit string for `values`."""
        return 'W/m^2/nm' if self.quantity == 'irradiance' else 'W/(m^2*sr*nm)'

    @property
    def domain_nm(self) -> Tuple[float, float]:
        """(min, max) wavelength this distribution is defined over, in nm."""
        return (self.wavelength_nm[0], self.wavelength_nm[-1])

    def value_at(self, wavelength_nm: float) -> float:
        """Plain linear interpolation of this SPD's own tabulated spectrum.

        Deliberately not `interp_log`: a source spectrum can be legitimately
        zero at some wavelengths (see module docstring), where log-space
        interpolation is undefined.

        Args:
            wavelength_nm: Wavelength to query, in nm.

        Returns:
            The interpolated value, in `unit`.

        Raises:
            ValueError: If `wavelength_nm` is outside `domain_nm`.
        """
        lo, hi = self.domain_nm
        if wavelength_nm < lo or wavelength_nm > hi:
            raise ValueError(
                f"wavelength_nm={wavelength_nm} is outside this distribution's "
                f"domain [{lo}, {hi}] nm."
            )
        i = _bracket_index(self.wavelength_nm, wavelength_nm)
        w0, w1 = self.wavelength_nm[i], self.wavelength_nm[i + 1]
        v0, v1 = self.values[i], self.values[i + 1]
        frac = (wavelength_nm - w0) / (w1 - w0)
        return v0 + frac * (v1 - v0)

    def integrate(self, hazard_fn: Callable[[float], float], step_nm: Optional[float] = None) -> float:
        """Weighted sum of this SPD against a hazard weighting function.

        Approximates IEC 62471's discrete-sum equations (e.g. Eq. 4.1:
        `E_s*t = Sum E_lambda(lambda,t)*S_UV(lambda)*dt*dlambda`) over this
        SPD's own wavelength domain, using the trapezoidal rule on a grid
        resampled at (approximately) `step_nm`. Per Sec. 5.3.2, "this
        standard suggests interpolation or summing to one nanometer (1 nm)
        for the spectra below 400 nm ... Above 400 nm, a step size of 5 nm
        is recommended" -- when `step_nm` is not given, 1 nm is used if
        this SPD's domain starts below 400 nm, else 5 nm.

        The resampled step is adjusted slightly so it evenly divides the
        domain width (so the last sample lands exactly on the domain's
        upper bound rather than a partial trailing interval being dropped
        or double-counted) -- a deliberate, documented deviation from a
        literal fixed-step transcription of the standard's own notation,
        not a silent one.

        Args:
            hazard_fn: Callable mapping wavelength (nm) to a dimensionless
                weighting value (e.g. `interp_log` against a hazard-function
                table). Must accept every wavelength in this SPD's domain.
            step_nm: Target resampling step in nm. Defaults per Sec. 5.3.2
                above.

        Returns:
            The weighted sum. Units are `unit` times `hazard_fn`'s (usually
            dimensionless) output times nm -- e.g. W/m^2/nm * [-] * nm =
            W/m^2 for spectral irradiance integrated against a dimensionless
            hazard function.

        Raises:
            ValueError: If `step_nm` is given and not positive.
        """
        lo, hi = self.domain_nm
        if step_nm is None:
            step_nm = 1.0 if lo < 400.0 else 5.0
        if step_nm <= 0.0:
            raise ValueError("step_nm must be positive.")

        n_steps = max(1, round((hi - lo) / step_nm))
        actual_step = (hi - lo) / n_steps
        samples = [lo + k * actual_step for k in range(n_steps + 1)]
        weighted = [self.value_at(w) * hazard_fn(w) for w in samples]

        total = 0.0
        for k in range(n_steps):
            total += 0.5 * (weighted[k] + weighted[k + 1]) * actual_step
        return total
