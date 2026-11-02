"""
Python-specific package: Eye-safety hazard routines (IEC 62471 / IEC 60825-1).

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
PYTHON-SPECIFIC PACKAGE: Eye safety
===============================================================================
Pure post-processing on PhysicalScene's existing irradiance/radiance output
(no core/ dependency): "given a source's spectral radiance/irradiance at the
cornea, is it safe to look at, for how long, and under which
classification?" Sibling to optical_elements/physics/, not inside it -- the
output here is a hazard ratio/classification, not a transducer readout.

This package's current scope (see
dev_doc/architecture/components/eye_safety.md and
dev_doc/architecture/contracts/{C-EYE-01,C-EYE-02,C-EYE-03,C-EYE-04}.md):
shared, standard-agnostic scaffolding (angular subtense, per-standard
limiting-aperture selection and averaging, per-standard exposure-duration
time-regime helpers, LimitResult, SpectralPowerDistribution + interp_log --
together P-HAZARD-ROUTINES), IEC 60825-1's retinal (thermal and
photochemical), corneal/lens UV, and skin-thermal MPE/AEL/classification
chains -- deliberately not all of IEC 60825-1 (no far-IR >1400 nm AEL, no
ultrashort-pulse retinal-thermal MPE, no multiple-pulse criteria, no full
multi-condition classification -- see `iec60825_1.py`'s module docstring) --
and IEC 62471's broadband (lamp/LED) hazard-function
tables and risk-group classification (`hazard_functions.py`, `iec62471.py`)
-- deliberately not all of IEC 62471 either (no ultrashort retinal-thermal
pulses, no IRA-only short-pulse bracket, no "IR without strong visual
stimulus" criterion -- see `iec62471.py`'s module docstring). Agentic
exposure is a later phase and is not implemented here.

**C-EYE-04: neither `iec60825_1`'s nor `iec62471`'s `mpe_*`/
`classify_measurement` are re-exported at this package's top level.**
Both modules define functions named `mpe_retinal_thermal`/
`mpe_skin_thermal`/`classify_measurement` for the same hazard concept
under different, non-interchangeable standards (different formulas,
wavelength bands, and angular-subtense conventions). This was once
asymmetric -- only the laser standard's functions were flattened here --
which left a real, safety-relevant footgun: the *bare, easiest-to-reach* name
silently resolved to the **laser** standard, even though this project's
own stated audience (LEDs/lamps into concentrators) is closer to IEC
62471 [KC6: the easiest-to-type name is a default whether or not anyone
chose it]. Symmetrized once the asymmetry was pointed out: neither standard
gets a privileged bare name, so nothing is "the default" a careless call
could land on by accident. Call either via its submodule, explicitly, at
every call site:

    from ray_tracing_shapely.optical_elements.eye_safety import (
        iec60825_1, iec62471,
    )
    iec60825_1.mpe_retinal_thermal(...)   # laser
    iec62471.mpe_retinal_thermal(...)     # lamp/LED

`hazard_functions.py`'s `S_actinic_uv`/`B_blue_light`/`R_retinal_thermal`
have no such collision risk (nothing else in this package shares those
names) and remain flattened.

Architecture: dev_doc/architecture/components/eye_safety.md,
dev_doc/architecture/contracts/{C-EYE-01,C-EYE-02,C-EYE-03,C-EYE-04}.md.
Design rationale and phase history: dev_doc/architecture/components/eye_safety.md,
dev_doc/architecture/components/eye_safety.md,
dev_doc/architecture/components/eye_safety.md.
===============================================================================
"""

from . import iec60825_1
from . import iec62471
from .result import LimitResult
from .angular_subtense import (
    ALPHA_MIN_IEC62471_RAD,
    ALPHA_MIN_IEC60825_1_RAD,
    ALPHA_MAX_RAD,
    clip_alpha,
    alpha_from_axes,
    angle_from_size_distance,
)
from .radiometry_conversions import (
    radiance_from_irradiance,
    irradiance_from_radiance,
)
from .exposure_duration import (
    GAMMA_TH_IEC60825_1_RAD,
    alpha_eff_iec62471,
    t2_iec60825_1,
    gamma_ph_iec60825_1,
)
from .pupil_aperture import (
    limiting_aperture_diameter_iec62471,
    limiting_aperture_diameter_iec60825_1,
    average_over_aperture,
)
from .spectral_data import SpectralPowerDistribution, interp_log
from .hazard_functions import S_actinic_uv, B_blue_light, R_retinal_thermal
from .correction_factors import (
    c3_iec60825_1,
    c4_iec60825_1,
    c6_iec60825_1,
    c7_iec60825_1,
)

__all__ = [
    'iec60825_1',
    'iec62471',
    'LimitResult',
    'ALPHA_MIN_IEC62471_RAD',
    'ALPHA_MIN_IEC60825_1_RAD',
    'ALPHA_MAX_RAD',
    'clip_alpha',
    'alpha_from_axes',
    'angle_from_size_distance',
    'radiance_from_irradiance',
    'irradiance_from_radiance',
    'GAMMA_TH_IEC60825_1_RAD',
    'alpha_eff_iec62471',
    't2_iec60825_1',
    'gamma_ph_iec60825_1',
    'limiting_aperture_diameter_iec62471',
    'limiting_aperture_diameter_iec60825_1',
    'average_over_aperture',
    'SpectralPowerDistribution',
    'interp_log',
    'S_actinic_uv',
    'B_blue_light',
    'R_retinal_thermal',
    'c3_iec60825_1',
    'c4_iec60825_1',
    'c6_iec60825_1',
    'c7_iec60825_1',
]
