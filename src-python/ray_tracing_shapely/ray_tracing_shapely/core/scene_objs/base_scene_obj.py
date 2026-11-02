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

import json
import copy
import uuid as uuid_module
from typing import Optional, Dict, Any, List, TypedDict, Union, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from ..ray import Ray
    from ..geometry import Point


class ConstructReturn(TypedDict, total=False):
    """
    Return value for construction-related methods.

    Attributes:
        isDone: Whether the construction is done.
        requiresObjBarUpdate: Whether the object bar should be updated.
        isCancelled: Whether the construction is cancelled.
    """
    isDone: bool
    requiresObjBarUpdate: bool
    isCancelled: bool


class SimulationReturn(TypedDict, total=False):
    """
    Return value for simulation-related methods.

    Attributes:
        isAbsorbed: Whether the object absorbs the ray.
        newRays: The new rays to be added.
        truncation: The brightness of truncated rays due to numerical cutoff
                   (e.g. after a large number of partial internal reflections within a glass).
                   This is used to estimate the error of the simulation.
        brightnessScale: The actual brightness of the ray divided by the brightness inferred
                        from the properties of the object. This should be 1 when "ray density"
                        is high enough. When "ray density" is low, the calculated brightness of
                        the individual rays will be too high (alpha value for rendering will be
                        larger than 1). In this case, the object should rescale all the brightness
                        of the rays by a factor to keep the maximum alpha value to be 1. This
                        factor should be returned here and is used to generate warnings.
        isUndefinedBehavior: Whether the behavior of the ray is undefined. For example, when
                            the ray is incident on a corner of a glass.
    """
    isAbsorbed: bool
    newRays: List[Any]  # List of Ray objects
    truncation: float
    brightnessScale: float
    isUndefinedBehavior: bool


class BaseSceneObj:
    """
    Base class for objects (optical elements, decorations, etc.) in the scene.

    This class provides the fundamental interface for all scene objects, including:
    - Serialization/deserialization
    - Drawing and rendering
    - User interaction (construction, dragging, etc.)
    - Ray tracing interface (for optical objects)
    """

    # Class attributes (similar to static properties in JavaScript)
    type: str = ''
    """The type of the object."""

    serializable_defaults: Dict[str, Any] = {}
    """
    The default values of the properties of the object which are to be serialized.
    The keys are the property names and the values are the default values.
    If some property is default, it will not be serialized and will be deserialized to the default values.

    IMPORTANT: Points should be stored as dictionaries {'x': ..., 'y': ...}, not as Point instances.
    This follows the JavaScript implementation and ensures:
    - Simple JSON serialization/deserialization
    - Consistent with the JavaScript version which uses plain objects
    - Minimal conversion overhead

    Example:
        serializable_defaults = {
            'p1': {'x': 0, 'y': 0},      # Store points as dicts
            'p2': {'x': 100, 'y': 100},
            'reflectivity': 1.0
        }

        # In methods, convert dict points to Point objects for geometry operations:
        def some_method(self):
            # Convert to Point objects for use with geometry module
            p1 = geometry.point(self.p1['x'], self.p1['y'])
            p2 = geometry.point(self.p2['x'], self.p2['y'])
            distance = geometry.distance(p1, p2)

            # Direct dict access for coordinates
            x = self.p1['x']
            y = self.p1['y']
    """

    is_optical: bool = False
    """Whether the object is optical (i.e. is a light source, interacts with rays, or detects rays)."""

    merges_with_glass: bool = False
    """
    Whether the object can merge its surface with the surfaces of glasses
    (here "glass" means a subclass of `BaseGlass`). For glasses this is always true.
    Suppose a ray is incident on the overlapping surfaces of N+1 objects. If all objects
    have this property set to true, and N of them are glasses, then `on_ray_incident`
    will be called only on the other one (glass or not), with the N glasses being in
    `surface_merging_objs`. Otherwise, the behavior is undefined, and a warning will be shown.
    """

    # =========================================================================
    # PYTHON-SPECIFIC FEATURE: Object Identification
    # =========================================================================
    # Provides unique identifiers and human-readable names for objects.
    # - uuid: Auto-generated unique identifier for each object instance
    # - name: Optional human-readable name for easy identification
    # These are useful for debugging, logging, XML export, and referencing
    # objects programmatically.
    # =========================================================================

    def __init__(self, scene, json_obj: Optional[Dict[str, Any]] = None):
        """
        Initialize the base scene object.

        Args:
            scene: The scene the object belongs to.
            json_obj: The JSON object to be deserialized, if any.
        """
        self.scene = scene
        self.error: Optional[str] = None
        """The error message of the object."""

        self.warning: Optional[str] = None
        """The warning message of the object."""

        # Python-specific: Object identification
        self._uuid: str = str(uuid_module.uuid4())
        """Auto-generated unique identifier for this object instance."""

        self._name: Optional[str] = None
        """Optional human-readable name for the object."""

        self._role = None
        """Optional Role tag (optical_elements.roles.Role) for structural path
        auditing -- what this object does in a device, independent of name."""

        # Check for unknown keys in the json_obj
        if json_obj:
            serializable_defaults = self.__class__.serializable_defaults
            known_keys = ['type'] + list(serializable_defaults.keys())

            for key in json_obj:
                if key not in known_keys:
                    # Store error in the scene, not the object, to prevent further errors
                    # from replacing it, and also because this error likely indicates an
                    # incompatible scene version.
                    if hasattr(self.scene, 'error'):
                        self.scene.error = (
                            f"Unknown object key '{key}' for type '{self.__class__.type}'"
                        )

            # Set the properties of the object
            for prop_name, default_value in serializable_defaults.items():
                if prop_name in json_obj:
                    # Deep copy to avoid reference issues
                    setattr(self, prop_name, copy.deepcopy(json_obj[prop_name]))
                else:
                    # Use default value
                    setattr(self, prop_name, copy.deepcopy(default_value))
        else:
            # No json_obj, use defaults
            serializable_defaults = self.__class__.serializable_defaults
            for prop_name, default_value in serializable_defaults.items():
                setattr(self, prop_name, copy.deepcopy(default_value))

    def serialize(self) -> Dict[str, Any]:
        """
        Serializes the object to a JSON-compatible dictionary.

        Returns:
            The serialized dictionary object.
        """
        json_obj = {'type': self.__class__.type}
        serializable_defaults = self.__class__.serializable_defaults

        for prop_name, default_value in serializable_defaults.items():
            current_value = getattr(self, prop_name)
            # Only serialize if different from default
            if json.dumps(current_value, sort_keys=True) != json.dumps(default_value, sort_keys=True):
                json_obj[prop_name] = copy.deepcopy(current_value)

        return json_obj

    def are_properties_default(self, property_names: List[str]) -> bool:
        """
        Check whether the given properties of the object are all the default values.

        Args:
            property_names: The property names to be checked.

        Returns:
            Whether the properties are all the default values.
        """
        serializable_defaults = self.__class__.serializable_defaults

        for prop_name in property_names:
            current_value = getattr(self, prop_name)
            default_value = serializable_defaults.get(prop_name)

            if json.dumps(current_value, sort_keys=True) != json.dumps(default_value, sort_keys=True):
                return False

        return True

    # ==================== UI and Drawing Methods ====================

    def populate_obj_bar(self, obj_bar) -> None:
        """
        Populate the object bar.

        Called when the user selects the object (it is selected automatically when
        the user creates it, so the construction may not be completed at this stage).

        Args:
            obj_bar: The object bar to be populated.
        """
        # Do nothing by default
        pass

    def get_z_index(self) -> int:
        """
        Get the z-index of the object for the sequence of drawing.

        Called before the simulator starts to draw the scene.

        Returns:
            The z-index. The smaller the number is, the earlier `draw` is called.
        """
        return 0

    def draw(self, canvas_renderer, is_above_light: bool, is_hovered: bool) -> None:
        """
        Draw the object on the canvas.

        Called once before the simulator renders the light with `is_above_light == False`
        and once after with `is_above_light == True`.

        Args:
            canvas_renderer: The canvas renderer.
            is_above_light: Whether the rendering layer is above the light layer.
            is_hovered: Whether the object is hovered by the mouse, which determines
                       the style of the object to be drawn, e.g., with highlighted color.
        """
        # Do nothing by default
        pass

    # ==================== Transformation Methods ====================

    def move(self, diff_x: float, diff_y: float) -> bool:
        """
        Move the object by the given displacement.

        Called when the user uses arrow keys to move the object.

        Args:
            diff_x: The x-coordinate displacement.
            diff_y: The y-coordinate displacement.

        Returns:
            True if the movement is done properly in the sense that if every object
            is moved by the same displacement, the resulting scene should look essentially
            the same as if the viewport is moved by the opposite displacement. False otherwise.
        """
        return False

    def rotate(self, angle: float, center=None) -> bool:
        """
        Rotate the object by the given angle.

        Args:
            angle: The angle in radians. Positive for counter-clockwise.
            center: The center of rotation (Point object). If None, there should be
                   a default center of rotation (which is used when the user uses the
                   +/- keys to rotate the object).

        Returns:
            True if the rotation is done properly in the sense that if every object
            is rotated by the same angle and center, the resulting scene should look
            essentially the same as if the viewport is rotated by the opposite angle.
            False otherwise.
        """
        return False

    def scale(self, scale: float, center=None) -> bool:
        """
        Scale the object by the given scale factor.

        Args:
            scale: The scale factor.
            center: The center of scaling (Point object). If None, there should be
                   a default center of scaling.

        Returns:
            True if the scaling is done properly in the sense that if every object
            is scaled by the same scale factor and center, the resulting scene should
            look essentially the same as if the viewport is scaled by the same scale factor.
            False otherwise.
        """
        return False

    def get_default_center(self) -> Optional['Point']:
        """
        Get the default center of rotation or scaling.

        Returns:
            The default center of rotation or scaling (Point object), or None.
        """
        return None

    # ==================== Construction Methods ====================

    def on_construct_mouse_down(self, mouse, ctrl: bool, shift: bool) -> Optional[ConstructReturn]:
        """
        Mouse down event when the object is being constructed by the user.

        Args:
            mouse: The mouse object.
            ctrl: Whether the control key is pressed.
            shift: Whether the shift key is pressed.

        Returns:
            The ConstructReturn dictionary, or None.
        """
        # Do nothing by default
        return None

    def on_construct_mouse_move(self, mouse, ctrl: bool, shift: bool) -> Optional[ConstructReturn]:
        """
        Mouse move event when the object is being constructed by the user.

        Args:
            mouse: The mouse object.
            ctrl: Whether the control key is pressed.
            shift: Whether the shift key is pressed.

        Returns:
            The ConstructReturn dictionary, or None.
        """
        # Do nothing by default
        return None

    def on_construct_mouse_up(self, mouse, ctrl: bool, shift: bool) -> Optional[ConstructReturn]:
        """
        Mouse up event when the object is being constructed by the user.

        Args:
            mouse: The mouse object.
            ctrl: Whether the control key is pressed.
            shift: Whether the shift key is pressed.

        Returns:
            The ConstructReturn dictionary, or None.
        """
        # Do nothing by default
        return None

    def on_construct_undo(self) -> ConstructReturn:
        """
        Undo event when the object is being constructed by the user.

        Returns:
            The ConstructReturn dictionary.
        """
        return {'isCancelled': True}

    # ==================== Interaction Methods ====================

    def check_mouse_over(self, mouse: Any) -> Optional[Dict[str, Any]]:
        """
        Check whether the mouse is over the object.

        Called when the user moves the mouse over the scene. This is used for deciding
        the highlighting of the object, and also for deciding that if the user starts
        dragging at this position, which part of the object should be dragged.

        Args:
            mouse: The mouse object.

        Returns:
            The drag context if the user starts dragging at this position,
            or None if the mouse is not over the object.
        """
        return None

    def on_drag(self, mouse, drag_context, ctrl: bool, shift: bool) -> None:
        """
        The event when the user drags the object.

        Fired on every step during the dragging. The object should be updated according
        to `drag_context` which is returned by `check_mouse_over`. `drag_context` can
        be modified during the dragging.

        Args:
            mouse: The mouse object.
            drag_context: The drag context.
            ctrl: Whether the control key is pressed.
            shift: Whether the shift key is pressed.
        """
        # Do nothing by default
        pass

    # ==================== Simulation Methods ====================

    def on_simulation_start(self) -> Optional[SimulationReturn]:
        """
        The event when the simulation starts.

        If this object is a light source, it should emit rays here by setting `newRays`.
        If the object is a detector, it may do some initialization here.

        Returns:
            The SimulationReturn dictionary, or None.
        """
        # Do nothing by default
        return None

    def check_ray_intersects(self, ray: 'Ray') -> Optional['Point']:
        """
        Check whether the object intersects with the given ray.

        Called during the ray tracing when `ray` is to be tested whether it intersects
        with the object. Find whether they intersect and find the nearest intersection if so.
        Implemented only by optical elements that affect or detect rays.

        Args:
            ray: The ray object.

        Returns:
            The intersection (closest to the beginning of the ray) if they intersect,
            or None otherwise (Point object).
        """
        return None

    def on_ray_incident(
        self,
        ray: 'Ray',
        ray_index: int,
        incident_point: Union['Point', Dict[str, float]],
        surface_merging_objs: List['BaseSceneObj'],
        verbose: int = 0
    ) -> Optional[SimulationReturn]:
        """
        The event when a ray is incident on the object.

        Called during the ray tracing when `ray` has been calculated to be incident on
        the object at the `incident_point`. Perform the interaction between `ray` and
        the object. Implemented only by optical elements that affect or detect rays.

        If `ray` is absorbed by the object, return `{ 'isAbsorbed': True }`.

        If there is a primary outgoing ray, directly modify `ray` to be the outgoing ray.
        This includes the case when the object is a detector that does not modify the
        direction of the ray.

        If there are secondary rays to be emitted, return `{ 'newRays': [ray1, ray2, ...] }`.
        Note that if there are more than one secondary rays, image detection does not work
        in the current version, and `ray.gap` should be set to `True`. But for future support,
        the secondary ray which is to be of the same continuous bunch of rays should have
        consistent index in the `newRays` array.

        Sometimes keeping track of all the rays may result in infinite loop (such as in a glass).
        Depending on the situation, some rays with brightness below a certain threshold
        (such as 0.01) may be truncated. In this case, the brightness of the truncated rays
        should be returned as `truncation`.

        Args:
            ray: The ray object.
            ray_index: The index of the ray in the array of all rays currently in the scene
                      in the simulator. In particular, in a bunch of continuous rays, the rays
                      are ordered by the time they are emitted, and the index is the order of
                      emission. This can be used to downsample the rays and increase the
                      individual brightness if it is too low.
            incident_point: The point where the ray is incident on the object, which is the
                           intersection point found by `check_ray_intersects` (Point object).
            surface_merging_objs: The glass objects that are merged with the current object.
                                 When a ray is incident on the overlapping surfaces of N+1 objects
                                 with `merges_with_glass == True`, and N of them are glasses, then
                                 this function will be called only on the other one (glass or not),
                                 with the N glasses being in this array. The function will need to
                                 handle the combination of the surfaces. Note that treating them as
                                 two very close surfaces may not give the correct result due to an
                                 essential discontinuity of ray optics (which is smoothed out at
                                 the scale of the wavelength in reality).
            verbose: Verbosity level (default: 0)
                    0 = silent (no debug output)
                    1 = verbose (show ray processing info)
                    2 = very verbose/debug (show detailed refraction calculations)

        Returns:
            The SimulationReturn dictionary, or None.
        """
        # Do nothing by default
        return None

    # ==================== Error/Warning Methods ====================

    def get_error(self) -> Optional[str]:
        """
        Get the error message of the object.

        Returns:
            The error message, or None.
        """
        return self.error

    def get_warning(self) -> Optional[str]:
        """
        Get the warning message of the object.

        Returns:
            The warning message, or None.
        """
        return self.warning

    # ==================== Python-Specific: Object Identification ====================

    @property
    def uuid(self) -> str:
        """
        Get the unique identifier for this object.

        The UUID is auto-generated when the object is created and remains
        constant for the lifetime of the object instance.

        Returns:
            The UUID string (e.g., "550e8400-e29b-41d4-a716-446655440000").
        """
        return self._uuid

    @property
    def name(self) -> Optional[str]:
        """
        Get the human-readable name of the object.

        Returns:
            The name if set, or None.
        """
        return self._name

    @name.setter
    def name(self, value: Optional[str]) -> None:
        """
        Set the human-readable name of the object.

        Args:
            value: The name to set, or None to clear.
        """
        self._name = value

    @property
    def role(self):
        """
        Get the structural Role tag of the object (optical_elements.roles.Role).

        Returns:
            The Role if set, or None.
        """
        return self._role

    @role.setter
    def role(self, value) -> None:
        """
        Set the structural Role tag of the object.

        Args:
            value: An optical_elements.roles.Role, or None to clear.
        """
        self._role = value

    def get_display_name(self) -> str:
        """
        Get a display name for the object.

        Returns the user-defined name if set, otherwise returns a combination
        of the object type and a short UUID suffix for identification.

        Returns:
            A string suitable for display (e.g., "Main Prism" or "Glass_a1b2c3d4").
        """
        if self._name:
            return self._name
        # Use type + short UUID suffix
        type_name = self.__class__.type or self.__class__.__name__
        short_uuid = self._uuid[:8]
        return f"{type_name}_{short_uuid}"

    def __repr__(self) -> str:
        """
        Return a string representation of the object.

        Returns:
            String with type, name/uuid, and key properties.
        """
        display = self.get_display_name()
        type_name = self.__class__.type or self.__class__.__name__
        return f"<{type_name} '{display}'>"


# Example of how to create a subclass
if __name__ == "__main__":
    # Import geometry for demonstration
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from geometry import geometry

    # Example subclass demonstrating the pattern
    class ExampleOpticalObject(BaseSceneObj):
        type = 'example_optical'
        serializable_defaults = {
            'p1': {'x': 0, 'y': 0},      # Points stored as dicts
            'p2': {'x': 100, 'y': 100},  # Not Point instances
            'reflectivity': 1.0
        }
        is_optical = True

        def __init__(self, scene, json_obj=None):
            super().__init__(scene, json_obj)

        def check_ray_intersects(self, ray):
            # Example implementation would go here
            return None

        def get_length(self):
            """Demonstrate using points with geometry module."""
            # Convert dict points to Point objects for geometry operations
            p1 = geometry.point(self.p1['x'], self.p1['y'])
            p2 = geometry.point(self.p2['x'], self.p2['y'])
            return geometry.distance(p1, p2)

    # Create a mock scene
    class MockScene:
        def __init__(self):
            self.error = None

    scene = MockScene()

    # Create object with defaults
    obj1 = ExampleOpticalObject(scene)
    print("Object 1 (defaults):")
    print(f"  p1: {obj1.p1}")
    print(f"  p2: {obj1.p2}")
    print(f"  reflectivity: {obj1.reflectivity}")
    print(f"  Length: {obj1.get_length()}")
    print(f"  Serialized: {obj1.serialize()}")
    print()

    # Create object from JSON
    json_data = {
        'type': 'example_optical',
        'p1': {'x': 50, 'y': 50},
        'reflectivity': 0.8
    }
    obj2 = ExampleOpticalObject(scene, json_data)
    print("Object 2 (from JSON):")
    print(f"  p1: {obj2.p1}")
    print(f"  p2: {obj2.p2}")  # Should use default
    print(f"  reflectivity: {obj2.reflectivity}")
    print(f"  Length: {obj2.get_length()}")
    print(f"  Serialized: {obj2.serialize()}")
    print()

    # Test are_properties_default
    print(f"Are p1, p2 default in obj1? {obj1.are_properties_default(['p1', 'p2'])}")
    print(f"Are p1, p2 default in obj2? {obj2.are_properties_default(['p1', 'p2'])}")
    print()

    # Demonstrate that points work with geometry module
    print("Demonstrating geometry module compatibility:")
    print(f"  Direct dict access: p1['x'] = {obj1.p1['x']}, p1['y'] = {obj1.p1['y']}")

    # Convert to Point objects for geometry operations
    p1 = geometry.point(obj1.p1['x'], obj1.p1['y'])
    p2 = geometry.point(obj1.p2['x'], obj1.p2['y'])
    midpoint = geometry.midpoint(p1, p2)
    print(f"  Midpoint of p1 and p2: {midpoint}")
    print(f"  Midpoint type: {type(midpoint).__name__}")  # Returns Point instance
