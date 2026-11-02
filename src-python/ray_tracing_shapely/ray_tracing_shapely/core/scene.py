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
import random
import uuid as uuid_module
from typing import Optional

class Scene:
    """
    Container for scene objects and simulation settings.

    This class manages all objects in the simulation and provides
    scene-level configuration parameters like ray density, color mode,
    and length scale.

    Attributes:
        objs (list): All objects in the scene
        optical_objs (list): Only optical objects (those with is_optical=True)
        ray_mode_density (float): Angular density of rays in 'rays'/'extended' modes
        image_mode_density (float): Angular density of rays in 'images'/'observer' modes
        color_mode (str): Color rendering mode. Options:
            - 'default': Standard rendering (brightness controls opacity when simulate_colors=False)
            - 'linear': Linear value mapping
            - 'linearRGB': Linear RGB mapping
            - 'reinhard': Reinhard tone mapping
            - 'colorizedIntensity': Color-coded intensity visualization
        mode (str): Simulation mode ('rays', 'extended', 'images', 'observer')
        length_scale (float): Scale factor for all lengths in the scene
        simulate_colors (bool): Whether to simulate wavelength-dependent behavior
        show_ray_arrows (bool): Whether to display direction arrows on rays
        error (str or None): Error message if simulation encountered an error
        warning (str or None): Warning message if simulation has warnings
        name (str or None): Optional name for the scene (used in exports)

    Properties:
        ray_density (float): Mode-dependent ray density (returns ray_mode_density
            for 'rays'/'extended' modes, image_mode_density otherwise)
        min_brightness_exp (int or None): [PYTHON-SPECIFIC FEATURE] Exponent for minimum
            brightness threshold. The threshold is 10^(-min_brightness_exp). For example:
            - 2 means threshold = 10^(-2) = 0.01 = 1%
            - 6 means threshold = 10^(-6) = 0.000001 = 1ppm
            If None (default), the threshold is automatically determined by color_mode:
            - 'default' mode uses 0.01 (exp=2)
            - Other modes use 1e-6 (exp=6)
    """

    # Valid color modes
    VALID_COLOR_MODES = ('default', 'linear', 'linearRGB', 'reinhard', 'colorizedIntensity')

    # Valid simulation modes
    VALID_MODES = ('rays', 'extended', 'images', 'observer')

    def __init__(self):
        """Initialize an empty scene with default settings."""
        self.objs = []
        self.optical_objs = []
        self.ray_mode_density = 0.1    # radians between rays for 'rays'/'extended' modes
        self.image_mode_density = 1.0  # radians between rays for 'images'/'observer' modes
        self._color_mode = 'default'
        self._mode = 'rays'
        self.length_scale = 1.0
        self.simulate_colors = False
        self.show_ray_arrows = False   # Display direction arrows on rays
        self.error = None
        self.warning = None
        self.name = None               # Optional scene name for exports
        self._rng_state = None         # For reproducible random numbers
        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Scene Identification
        # =====================================================================
        # Unique identifier for the scene, useful for tracking simulation runs
        # and correlating results with scene configurations.
        # =====================================================================
        self._uuid: str = str(uuid_module.uuid4())
        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Explicit brightness threshold control
        # =====================================================================
        # In the JavaScript version, the brightness threshold is implicitly
        # determined by color_mode ('default' uses 0.01, others use 1e-6).
        # This Python implementation allows explicit control via min_brightness_exp.
        # When None, it falls back to the JavaScript behavior based on color_mode.
        # =====================================================================
        self._min_brightness_exp = None  # None = auto (based on color_mode)

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Grazing Incidence Detection Thresholds
        # =====================================================================
        # These thresholds control when rays are flagged as experiencing grazing
        # incidence (near-critical-angle refraction). Three independent criteria:
        #
        # 1. Angle threshold: incidence angle above this value (degrees)
        #    Default 85° means angles within 5° of critical angle are flagged
        #
        # 2. Polarization ratio threshold: brightness_p / brightness_s after refraction
        #    Default 10.0 means p-polarized transmits 10x more than s-polarized
        #
        # 3. Transmission ratio threshold: total transmitted / total incident
        #    Default 0.1 means less than 10% of incident energy is transmitted
        # =====================================================================
        self.grazing_angle_threshold: float = 85.0  # degrees
        self.grazing_polarization_ratio_threshold: float = 10.0  # brightness_p / brightness_s
        self.grazing_transmission_threshold: float = 0.1  # T_ratio = transmitted / incident

    @property
    def color_mode(self):
        """Get the color rendering mode."""
        return self._color_mode

    @color_mode.setter
    def color_mode(self, value):
        """Set the color rendering mode with validation."""
        if value not in self.VALID_COLOR_MODES:
            raise ValueError(
                f"Invalid color_mode '{value}'. "
                f"Valid options: {self.VALID_COLOR_MODES}"
            )
        self._color_mode = value

    @property
    def mode(self):
        """Get the simulation mode."""
        return self._mode

    @mode.setter
    def mode(self, value):
        """Set the simulation mode with validation."""
        if value not in self.VALID_MODES:
            raise ValueError(
                f"Invalid mode '{value}'. "
                f"Valid options: {self.VALID_MODES}"
            )
        self._mode = value

    @property
    def ray_density(self):
        """
        Get the mode-dependent ray density.

        Returns ray_mode_density for 'rays' and 'extended' modes,
        image_mode_density for 'images' and 'observer' modes.
        """
        if self._mode in ('rays', 'extended'):
            return self.ray_mode_density
        else:
            return self.image_mode_density

    @ray_density.setter
    def ray_density(self, value):
        """
        Set the mode-dependent ray density.

        Sets ray_mode_density for 'rays' and 'extended' modes,
        image_mode_density for 'images' and 'observer' modes.
        """
        if self._mode in ('rays', 'extended'):
            self.ray_mode_density = value
        else:
            self.image_mode_density = value

    # =========================================================================
    # PYTHON-SPECIFIC FEATURE: Explicit brightness threshold control
    # =========================================================================
    # The following properties allow explicit control over the minimum brightness
    # threshold used to decide when to stop tracing reflected/refracted rays.
    # This feature is specific to the Python implementation and does not exist
    # in the JavaScript version, where the threshold is implicitly tied to color_mode.
    # =========================================================================

    @property
    def min_brightness_exp(self):
        """
        Get the minimum brightness exponent.

        [PYTHON-SPECIFIC FEATURE]

        Returns the exponent for the minimum brightness threshold.
        If None, the threshold is automatically determined by color_mode.

        Returns:
            int or None: The exponent value, or None for automatic mode.
        """
        return self._min_brightness_exp

    @min_brightness_exp.setter
    def min_brightness_exp(self, value):
        """
        Set the minimum brightness exponent.

        [PYTHON-SPECIFIC FEATURE]

        The brightness threshold is calculated as 10^(-value). For example:
        - value=2 means threshold = 10^(-2) = 0.01 = 1%
        - value=6 means threshold = 10^(-6) = 0.000001 = 1ppm

        Set to None to use automatic mode (based on color_mode).

        Args:
            value: int or None. If int, must be positive.

        Raises:
            ValueError: If value is not None and not a positive integer.
        """
        if value is not None:
            if not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(
                    f"min_brightness_exp must be a positive number or None, got {value}"
                )
        self._min_brightness_exp = value

    def get_min_brightness_threshold(self):
        """
        Get the actual minimum brightness threshold value.

        [PYTHON-SPECIFIC FEATURE]

        Returns the computed threshold based on min_brightness_exp if set,
        or falls back to the JavaScript-compatible behavior based on color_mode.

        Returns:
            float: The minimum brightness threshold (e.g., 0.01 or 1e-6)
        """
        if self._min_brightness_exp is not None:
            # Use explicit threshold: 10^(-exp)
            return 10 ** (-self._min_brightness_exp)
        else:
            # Fall back to JavaScript behavior based on color_mode
            if self._color_mode == 'default':
                return 0.01  # 1% threshold for default mode
            else:
                return 1e-6  # 0.0001% threshold for other modes

    # =========================================================================
    # END PYTHON-SPECIFIC FEATURE
    # =========================================================================

    # =========================================================================
    # PYTHON-SPECIFIC FEATURE: Scene Identification
    # =========================================================================

    @property
    def uuid(self) -> str:
        """
        Get the unique identifier for this scene.

        [PYTHON-SPECIFIC FEATURE]

        The UUID is auto-generated when the scene is created and remains
        constant for the lifetime of the scene instance.

        Returns:
            The UUID string (e.g., "550e8400-e29b-41d4-a716-446655440000").
        """
        return self._uuid

    def get_display_name(self) -> str:
        """
        Get a display name for the scene.

        [PYTHON-SPECIFIC FEATURE]

        Returns the user-defined name if set, otherwise returns a combination
        of "Scene" and a short UUID suffix for identification.

        Returns:
            A string suitable for display (e.g., "TIR Demo" or "Scene_a1b2c3d4").
        """
        if self.name:
            return self.name
        short_uuid = self._uuid[:8]
        return f"Scene_{short_uuid}"

    # =========================================================================
    # END PYTHON-SPECIFIC FEATURE: Scene Identification
    # =========================================================================

    def rng(self):
        """
        Generate a random number between 0 and 1.

        Returns:
            A random float between 0 and 1.
        """
        return random.random()

    def add_object(self, obj):
        """
        Add an object to the scene.

        Automatically adds optical objects (those with is_optical=True)
        to the optical_objs list for efficient simulation.

        Args:
            obj: The scene object to add
        """
        self.objs.append(obj)
        if hasattr(obj, 'is_optical') and obj.is_optical:
            self.optical_objs.append(obj)

    def remove_object(self, obj):
        """
        Remove an object from the scene.

        Args:
            obj: The scene object to remove
        """
        if obj in self.objs:
            self.objs.remove(obj)
        if obj in self.optical_objs:
            self.optical_objs.remove(obj)

    def clear(self):
        """Remove all objects from the scene."""
        self.objs.clear()
        self.optical_objs.clear()
        self.error = None
        self.warning = None

    # =========================================================================
    # PYTHON-SPECIFIC FEATURE: Bulk Edge Labeling
    # =========================================================================
    # Convenience method to auto-label all glass objects in the scene.
    # =========================================================================

    def get_object_by_name(self, name: str) -> Optional[object]:
        """
        Return the first object whose name matches the given string, or None.

        Args:
            name: The name to search for (exact match, case-sensitive).

        Returns:
            The matching object, or None if no object has that name.
        """
        for obj in self.objs:
            if hasattr(obj, 'name') and obj.name == name:
                return obj
        return None

    def auto_label_all_glass_cardinal(self):
        """
        Automatically label all glass objects with cardinal directions.

        [PYTHON-SPECIFIC FEATURE]

        Iterates through all objects in the scene and calls auto_label_cardinal()
        on any object that has this method (i.e., glass objects inheriting from
        BaseGlass).

        Returns:
            int: The number of glass objects that were labeled.

        Example:
            scene = Scene()
            scene.add_object(prism1)
            scene.add_object(prism2)
            scene.add_object(lens)  # Not a glass, will be skipped
            count = scene.auto_label_all_glass_cardinal()
            print(f"Labeled {count} glass objects")
        """
        count = 0
        for obj in self.objs:
            if hasattr(obj, 'auto_label_cardinal') and callable(obj.auto_label_cardinal):
                obj.auto_label_cardinal()
                count += 1
        return count


# Example usage and testing
if __name__ == "__main__":
    print("Testing Scene class...\n")

    # Mock optical object
    class MockLightSource:
        def __init__(self, name):
            self.name = name
            self.is_optical = True

        def __repr__(self):
            return f"MockLightSource({self.name})"

    # Mock non-optical object (e.g., annotation)
    class MockAnnotation:
        def __init__(self, text):
            self.text = text
            self.is_optical = False

        def __repr__(self):
            return f"MockAnnotation({self.text})"

    # Mock object without is_optical attribute (treated as non-optical)
    class MockDecorator:
        def __init__(self, label):
            self.label = label

        def __repr__(self):
            return f"MockDecorator({self.label})"

    # Test 1: Create empty scene
    print("Test 1: Create empty scene")
    scene = Scene()
    print(f"  Objects: {len(scene.objs)}")
    print(f"  Optical objects: {len(scene.optical_objs)}")
    print(f"  Ray density: {scene.ray_density}")
    print(f"  Ray mode density: {scene.ray_mode_density}")
    print(f"  Image mode density: {scene.image_mode_density}")
    print(f"  Color mode: {scene.color_mode}")
    print(f"  Mode: {scene.mode}")
    print(f"  Length scale: {scene.length_scale}")
    print(f"  Simulate colors: {scene.simulate_colors}")
    print(f"  Show ray arrows: {scene.show_ray_arrows}")

    # Test 2: Add optical objects
    print("\nTest 2: Add optical objects")
    source1 = MockLightSource("Source1")
    source2 = MockLightSource("Source2")
    scene.add_object(source1)
    scene.add_object(source2)
    print(f"  Added: {source1}, {source2}")
    print(f"  Total objects: {len(scene.objs)}")
    print(f"  Optical objects: {len(scene.optical_objs)}")
    print(f"  Optical objects list: {scene.optical_objs}")

    # Test 3: Add non-optical objects
    print("\nTest 3: Add non-optical objects")
    annotation = MockAnnotation("Note")
    decorator = MockDecorator("Grid")
    scene.add_object(annotation)
    scene.add_object(decorator)
    print(f"  Added: {annotation}, {decorator}")
    print(f"  Total objects: {len(scene.objs)}")
    print(f"  Optical objects: {len(scene.optical_objs)} (should not include non-optical)")
    print(f"  All objects: {scene.objs}")

    # Test 4: Remove objects
    print("\nTest 4: Remove objects")
    scene.remove_object(source1)
    print(f"  Removed: {source1}")
    print(f"  Total objects: {len(scene.objs)}")
    print(f"  Optical objects: {len(scene.optical_objs)}")
    print(f"  Remaining objects: {scene.objs}")

    # Test 5: Scene settings
    print("\nTest 5: Modify scene settings")
    scene.ray_density = 0.05
    scene.simulate_colors = True
    scene.color_mode = 'linear'  # Use valid color mode
    scene.length_scale = 10.0
    print(f"  Ray density: {scene.ray_density} (more rays)")
    print(f"  Simulate colors: {scene.simulate_colors}")
    print(f"  Color mode: {scene.color_mode}")
    print(f"  Length scale: {scene.length_scale}")

    # Test 6: Error and warning messages
    print("\nTest 6: Error and warning messages")
    scene.warning = "Ray count limit reached"
    scene.error = None
    print(f"  Warning: {scene.warning}")
    print(f"  Error: {scene.error}")

    # Test 7: Clear scene
    print("\nTest 7: Clear scene")
    print(f"  Before clear - objects: {len(scene.objs)}, optical: {len(scene.optical_objs)}")
    scene.clear()
    print(f"  After clear - objects: {len(scene.objs)}, optical: {len(scene.optical_objs)}")
    print(f"  Warning cleared: {scene.warning}")
    print(f"  Error cleared: {scene.error}")

    # Test 8: Build a simple scene
    print("\nTest 8: Build a simple optical scene")
    scene2 = Scene()
    scene2.ray_density = 0.2
    scene2.simulate_colors = False

    # Add multiple optical objects
    for i in range(3):
        scene2.add_object(MockLightSource(f"Source{i+1}"))

    # Add a non-optical annotation
    scene2.add_object(MockAnnotation("Experiment Setup"))

    print(f"  Scene configuration:")
    print(f"    Total objects: {len(scene2.objs)}")
    print(f"    Optical objects: {len(scene2.optical_objs)}")
    print(f"    Ray density: {scene2.ray_density} radians")
    print(f"    Objects: {scene2.objs}")

    # Test 9: Remove non-existent object (should not raise error)
    print("\nTest 9: Remove non-existent object")
    fake_obj = MockLightSource("NonExistent")
    scene2.remove_object(fake_obj)
    print(f"  Attempted to remove non-existent object: {fake_obj}")
    print(f"  Total objects (unchanged): {len(scene2.objs)}")

    # Test 10: Test mode-dependent ray density
    print("\nTest 10: Mode-dependent ray density")
    scene3 = Scene()
    scene3.ray_mode_density = 0.1
    scene3.image_mode_density = 1.0

    scene3.mode = 'rays'
    print(f"  Mode='rays': ray_density = {scene3.ray_density} (should be 0.1)")

    scene3.mode = 'extended'
    print(f"  Mode='extended': ray_density = {scene3.ray_density} (should be 0.1)")

    scene3.mode = 'images'
    print(f"  Mode='images': ray_density = {scene3.ray_density} (should be 1.0)")

    scene3.mode = 'observer'
    print(f"  Mode='observer': ray_density = {scene3.ray_density} (should be 1.0)")

    # Setting ray_density should affect the appropriate mode density
    scene3.mode = 'rays'
    scene3.ray_density = 0.05
    print(f"  After setting ray_density=0.05 in 'rays' mode:")
    print(f"    ray_mode_density = {scene3.ray_mode_density} (should be 0.05)")
    print(f"    image_mode_density = {scene3.image_mode_density} (should still be 1.0)")

    # Test 11: Test color mode validation
    print("\nTest 11: Color mode validation")
    scene4 = Scene()
    print(f"  Valid color modes: {Scene.VALID_COLOR_MODES}")

    for mode in Scene.VALID_COLOR_MODES:
        scene4.color_mode = mode
        print(f"  Set color_mode='{mode}': OK")

    # Test invalid color mode
    try:
        scene4.color_mode = 'invalid_mode'
        print("  Set color_mode='invalid_mode': FAILED (should have raised error)")
    except ValueError as e:
        print(f"  Set color_mode='invalid_mode': Correctly raised ValueError")

    # Test 12: Test mode validation
    print("\nTest 12: Simulation mode validation")
    print(f"  Valid simulation modes: {Scene.VALID_MODES}")

    for mode in Scene.VALID_MODES:
        scene4.mode = mode
        print(f"  Set mode='{mode}': OK")

    # Test invalid mode
    try:
        scene4.mode = 'invalid_mode'
        print("  Set mode='invalid_mode': FAILED (should have raised error)")
    except ValueError as e:
        print(f"  Set mode='invalid_mode': Correctly raised ValueError")

    # Test 13: Test viewing options
    print("\nTest 13: Viewing options")
    scene5 = Scene()
    print(f"  show_ray_arrows (default): {scene5.show_ray_arrows}")
    scene5.show_ray_arrows = True
    print(f"  show_ray_arrows (set True): {scene5.show_ray_arrows}")
    scene5.name = "Test Scene"
    print(f"  Scene name: {scene5.name}")

    # Test 14: Test min_brightness_exp (PYTHON-SPECIFIC FEATURE)
    print("\nTest 14: Minimum brightness threshold (PYTHON-SPECIFIC)")
    scene6 = Scene()

    # Default: None (auto mode)
    print(f"  min_brightness_exp (default): {scene6.min_brightness_exp}")
    print(f"  color_mode='default' -> threshold: {scene6.get_min_brightness_threshold()} (should be 0.01)")

    scene6.color_mode = 'linear'
    print(f"  color_mode='linear' -> threshold: {scene6.get_min_brightness_threshold()} (should be 1e-6)")

    # Explicit threshold: exp=2 means 10^(-2) = 0.01
    scene6.min_brightness_exp = 2
    print(f"  min_brightness_exp=2 -> threshold: {scene6.get_min_brightness_threshold()} (should be 0.01)")

    # Explicit threshold: exp=6 means 10^(-6) = 0.000001
    scene6.min_brightness_exp = 6
    print(f"  min_brightness_exp=6 -> threshold: {scene6.get_min_brightness_threshold()} (should be 1e-6)")

    # Explicit threshold: exp=3 means 10^(-3) = 0.001
    scene6.min_brightness_exp = 3
    print(f"  min_brightness_exp=3 -> threshold: {scene6.get_min_brightness_threshold()} (should be 0.001)")

    # Reset to auto mode
    scene6.min_brightness_exp = None
    print(f"  min_brightness_exp=None -> threshold: {scene6.get_min_brightness_threshold()} (auto, should be 1e-6 for linear)")

    # Test invalid value
    try:
        scene6.min_brightness_exp = -1
        print("  min_brightness_exp=-1: FAILED (should have raised error)")
    except ValueError as e:
        print(f"  min_brightness_exp=-1: Correctly raised ValueError")

    try:
        scene6.min_brightness_exp = 0
        print("  min_brightness_exp=0: FAILED (should have raised error)")
    except ValueError as e:
        print(f"  min_brightness_exp=0: Correctly raised ValueError")

    print("\nScene test completed successfully!")
