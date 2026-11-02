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

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_scene_obj import BaseSceneObj
else:
    from .base_scene_obj import BaseSceneObj


class BaseFilter(BaseSceneObj):
    """
    The base class for optical elements with wavelength filter functionality,
    including mirrors (which have the dichroic feature) and blockers.

    Attributes:
        filter: Whether the filter feature is enabled.
        invert: If True, the element interacts with the ray only if its wavelength
                is outside the bandwidth of the filter. If False, the element
                interacts with the ray only if its wavelength is within the
                bandwidth of the filter.
        wavelength: The target wavelength of the filter. The unit is nm.
        bandwidth: The bandwidth of the filter. The unit is nm.

    Observations:
    obj_bar is a placeholder for a UI widget - specifically the "object bar" or property panel in the simulator's user interface.
    In the original JavaScript application, when a user selects an optical element (like a mirror or lens), 
    the obj_bar appears as a sidebar/panel with controls to adjust that object's properties. 
    The populate_obj_bar() method is called to dynamically create UI controls for the object's properties. 
    For example, in BaseFilter: obj_bar.create_boolean() - Creates a checkbox for enabling/disabling the filter 
    obj_bar.create_number() - Creates a number input/slider for wavelength and bandwidth values 
    The methods like create_boolean(), create_number(), etc. are part of the UI framework and generate interactive controls that: 
    - Display the current property value 
    - Allow the user to modify it 
    - Call the provided callback function when the value changes 
    
    Since we're translating to Python for the simulation engine, these populate_obj_bar() methods are currently just stubs that define the interface. 
    If we want to create a Python GUI (using something like PyQt, Tkinter, or a web interface), we'd implement an obj_bar class that actually creates those UI controls. 
    For now, they serve as documentation of what properties should be exposed to users and how they should be configured.        
    """

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with filter-related UI controls.

        This method adds UI controls for:
        - Enabling/disabling the filter
        - Inverting the filter behavior
        - Setting the target wavelength
        - Setting the bandwidth

        Args:
            obj_bar: The object bar to be populated.
        """
        if self.scene.simulate_colors:
            obj_bar.create_boolean(
                "Filter",  # In JS version this uses i18next.t('simulator:sceneObjs.BaseFilter.filter')
                self.filter,
                lambda obj, value: self._set_filter(obj, value),
                None,
                True
            )

            if self.filter:
                obj_bar.create_boolean(
                    "Invert",  # i18next.t('simulator:sceneObjs.BaseFilter.invert')
                    self.invert,
                    lambda obj, value: self._set_invert(obj, value)
                )

                # Import constants here to avoid circular imports
                from ..constants import UV_WAVELENGTH, INFRARED_WAVELENGTH

                obj_bar.create_number(
                    "Wavelength (nm)",  # i18next.t('simulator:sceneObjs.common.wavelength') + ' (nm)'
                    UV_WAVELENGTH,
                    INFRARED_WAVELENGTH,
                    1,
                    self.wavelength,
                    lambda obj, value: setattr(obj, 'wavelength', value)
                )

                obj_bar.create_number(
                    "± Bandwidth (nm)",  # "± " + i18next.t('simulator:sceneObjs.BaseFilter.bandwidth') + ' (nm)'
                    0,
                    INFRARED_WAVELENGTH - UV_WAVELENGTH,
                    1,
                    self.bandwidth,
                    lambda obj, value: setattr(obj, 'bandwidth', value)
                )

    def _set_filter(self, obj, value):
        """Helper method to set filter and related properties."""
        obj.filter = value
        obj.wavelength = obj.wavelength  # Trigger any property setters
        obj.invert = obj.invert
        obj.bandwidth = obj.bandwidth

    def _set_invert(self, obj, value):
        """Helper method to set invert property only if filter is enabled."""
        if obj.filter:
            obj.invert = value

    def check_ray_intersect_filter(self, ray):
        """
        Checks if the ray interacts with the filter at the level of the wavelength.

        This method determines whether a ray should interact with the optical element
        based on its wavelength and the filter settings. The filter can be configured
        to allow or block specific wavelength ranges.

        Args:
            ray: The ray to be checked.

        Returns:
            bool: True if the ray interacts with the filter at the level of the
                  wavelength, False otherwise.
        """
        dichroic_enabled = self.scene.simulate_colors and self.filter and self.wavelength

        # If dichroic is not enabled, always allow interaction
        if not dichroic_enabled:
            return True

        # Check if ray wavelength matches filter (handle None wavelength)
        if ray.wavelength is None:
            # White light - doesn't match any specific wavelength filter
            ray_hue_matches_mirror = False
        else:
            ray_hue_matches_mirror = abs(self.wavelength - ray.wavelength) <= self.bandwidth

        # If enabled, allow interaction when:
        # - (ray matches AND not inverted) OR (ray doesn't match AND inverted)
        return ray_hue_matches_mirror != self.invert


# Example usage
if __name__ == "__main__":
    # Example class combining BaseFilter with BaseSceneObj
    class FilterObject(BaseFilter, BaseSceneObj):
        type = 'filter_object'
        serializable_defaults = {
            'filter': False,
            'invert': False,
            'wavelength': 532,  # Green wavelength
            'bandwidth': 10
        }
        is_optical = True

        def __init__(self, scene, json_obj=None):
            super().__init__(scene, json_obj)

    # Mock scene with color simulation
    class MockScene:
        def __init__(self):
            self.error = None
            self.simulate_colors = True

    # Mock ray for testing
    class MockRay:
        def __init__(self, wavelength):
            self.wavelength = wavelength

    scene = MockScene()
    obj = FilterObject(scene)

    print("Initial filter object:")
    print(f"  filter enabled: {obj.filter}")
    print(f"  invert: {obj.invert}")
    print(f"  wavelength: {obj.wavelength} nm")
    print(f"  bandwidth: {obj.bandwidth} nm")

    # Test with filter disabled (should always allow)
    print("\n--- Testing with filter disabled ---")
    ray_green = MockRay(532)  # Green
    ray_red = MockRay(650)    # Red
    print(f"Green ray (532 nm): {obj.check_ray_intersect_filter(ray_green)}")
    print(f"Red ray (650 nm): {obj.check_ray_intersect_filter(ray_red)}")

    # Enable filter and test
    print("\n--- Testing with filter enabled (532 nm ±10 nm) ---")
    obj.filter = True
    ray_match_exact = MockRay(532)     # Exact match
    ray_match_edge = MockRay(540)      # Within bandwidth (532 + 8)
    ray_outside = MockRay(550)         # Outside bandwidth (532 + 18)
    ray_red = MockRay(650)             # Far outside

    print(f"Exact match (532 nm): {obj.check_ray_intersect_filter(ray_match_exact)}")
    print(f"Within bandwidth (540 nm): {obj.check_ray_intersect_filter(ray_match_edge)}")
    print(f"Outside bandwidth (550 nm): {obj.check_ray_intersect_filter(ray_outside)}")
    print(f"Far outside (650 nm): {obj.check_ray_intersect_filter(ray_red)}")

    # Test with inverted filter
    print("\n--- Testing with inverted filter ---")
    obj.invert = True
    print(f"Exact match (532 nm): {obj.check_ray_intersect_filter(ray_match_exact)}")
    print(f"Within bandwidth (540 nm): {obj.check_ray_intersect_filter(ray_match_edge)}")
    print(f"Outside bandwidth (550 nm): {obj.check_ray_intersect_filter(ray_outside)}")
    print(f"Far outside (650 nm): {obj.check_ray_intersect_filter(ray_red)}")

    # Test serialization
    print("\n--- Testing serialization ---")
    obj2 = FilterObject(scene, {
        'type': 'filter_object',
        'filter': True,
        'wavelength': 650,
        'bandwidth': 20
    })
    print(f"Object 2 wavelength: {obj2.wavelength} nm")
    print(f"Object 2 bandwidth: {obj2.bandwidth} nm")
    print(f"Serialized: {obj2.serialize()}")

    print("\nBaseFilter test completed successfully!")
