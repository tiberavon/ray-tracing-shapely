"""
Python-specific module: uncoupled copled prisms
Copyright 2026 ray-tracing-shapely authors and contributors

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

import sys
import os
from typing import List
import csv
import math


# Add parent directories to path to from ray_tracing_shapely import core modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.glass.ideal_lens import IdealLens
from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.svg_renderer import SVGRenderer
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.ray import Ray


def save_csv(ray_segments, output_dir):
    # Export ray data to CSV
    csv_file = os.path.join(output_dir, 'rays.csv')
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ray_index', 'p1_x', 'p1_y', 'p2_x', 'p2_y', 'brightness_s', 'brightness_p', 'brightness_total', 'wavelength', 'gap', 'length'])
        for i, ray in enumerate(ray_segments):
            dx = ray.p2['x'] - ray.p1['x']
            dy = ray.p2['y'] - ray.p1['y']
            length = math.sqrt(dx*dx + dy*dy)
            writer.writerow([
                i,
                f"{ray.p1['x']:.4f}",
                f"{ray.p1['y']:.4f}",
                f"{ray.p2['x']:.4f}",
                f"{ray.p2['y']:.4f}",
                f"{ray.brightness_s:.6f}",
                f"{ray.brightness_p:.6f}",
                f"{ray.total_brightness:.6f}",
                ray.wavelength if ray.wavelength else '',
                ray.gap,
                f"{length:.4f}"
            ])
    print(f"CSV data exported to: {csv_file}")

def save_json(ray_segments, output_dir):
    pass

def uncoupled_demo(
        color_mode: str = 'default',
        simulation_mode: str = 'rays',
        show_ray_arrows: bool = False,
        verbose: bool = True,
        min_brightness_exp: int = None,
    ):
    """Uncoupled Coupled Prisms demonstration.

    Problem Statement
    Demonstrate the behavior of light rays passing through two uncoupled prisms
    placed in sequence, showing refraction at each interface.

    Physics Background
    Snell's Law: n₁ * sin(θ₁) = n₂ * sin(θ₂)
    Refraction occurs at each interface based on refractive indices

    Expected Behavior
    Ray enters first prism (n=1.5) from air (n=1.0) → refracts inward
    Ray exits first prism back to air → refracts outward
    Ray enters second prism (n=1.5) from air → refracts inward
    Ray exits second prism back to air → refracts outward

    Args:
        color_mode: Color rendering mode. Options: 'default', 'linear', 'linearRGB',
                   'reinhard', 'colorizedIntensity'. Default: 'default'
        simulation_mode: Simulation mode. Options: 'rays', 'extended', 'images',
                        'observer'. Default: 'rays'
        show_ray_arrows: Whether to display direction arrows on rays. Default: False
        verbose: Whether to print progress messages. Default: True
        min_brightness_exp: [PYTHON-SPECIFIC] Exponent for minimum brightness threshold.
                           The threshold is 10^(-min_brightness_exp). For example:
                           - 2 means threshold = 0.01 (1%)
                           - 6 means threshold = 1e-6 (1ppm)
                           If None (default), threshold is auto-determined by color_mode.
  """

    output_dir = os.path.join(os.path.dirname(__file__), 'output_uncoupled')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_file = output_dir + '/prisms_uncoupled.svg'

    if verbose:
        print("Setting up Uncoupled Prisms...\n")

    # Create scene
    scene = Scene()
    scene.ray_density = 0.1
    scene.color_mode = color_mode
    scene.mode = simulation_mode
    scene.show_ray_arrows = show_ray_arrows
    # PYTHON-SPECIFIC: Set explicit brightness threshold if provided
    if min_brightness_exp is not None:
        scene.min_brightness_exp = min_brightness_exp

    # Create measuring prism
    meas_prism = Glass(scene)
    meas_prism.path = [
        {'x': 167, 'y': 61, 'arc': False},
        {'x': 274, 'y': 61, 'arc': False},
        {'x': 188, 'y': 104, 'arc': False}
    ]
    meas_prism.not_done = False
    meas_prism.refIndex = 1.5

    # Create illumination prism
    ill_prism = Glass(scene)
    ill_prism.path = [
        {'x': 167, 'y': 55, 'arc': False},
        {'x': 274, 'y': 55, 'arc': False},
        {'x': 253, 'y': 13, 'arc': False}
    ]
    ill_prism.not_done = False
    ill_prism.refIndex = 1.5

    scene.add_object(meas_prism)
    scene.add_object(ill_prism)
    dict_ray={
        'ray1A': {'p1':[272,4],'p2':[258,15]}
    }

    ray_list: List[SingleRay] = []
    for ray in dict_ray:
        new_ray_source = SingleRay(scene)
        new_ray_source.p1 = {'x': dict_ray[ray]['p1'][0], 'y': dict_ray[ray]['p1'][1]}
        new_ray_source.p2 = {'x': dict_ray[ray]['p2'][0], 'y': dict_ray[ray]['p2'][1]}  #point along the ray
        new_ray_source.brightness = 1.0
        ray_list.append(new_ray_source)

    # Add sources to scene
    for ray_source in ray_list:
        scene.add_object(ray_source)

    # Run simulation
    # verbose levels: 0=silent (default), 1=verbose (ray processing), 2=debug (detailed refraction)
    simulator = Simulator(scene, max_rays=1000, verbose=0)
    segments = simulator.run()

    if verbose:
        print(f"Rays traced: {simulator.processed_ray_count}")
        print(f"Segments: {len(segments)}")

    # Render
    renderer = SVGRenderer(width=800, height=600, viewbox=(0, 0, 300, 200))
    renderer.draw_line_segment(meas_prism.path[0], meas_prism.path[1], color='blue', stroke_width=2, label='MeasPrism')
    renderer.draw_line_segment(meas_prism.path[1], meas_prism.path[2], color='blue', stroke_width=2)
    renderer.draw_line_segment(meas_prism.path[2], meas_prism.path[0], color='blue', stroke_width=2)

    renderer.draw_line_segment(ill_prism.path[0], ill_prism.path[1], color='blue', stroke_width=2, label='IllPrism')
    renderer.draw_line_segment(ill_prism.path[1], ill_prism.path[2], color='blue', stroke_width=2)
    renderer.draw_line_segment(ill_prism.path[2], ill_prism.path[0], color='blue', stroke_width=2)

    for seg in segments:
        # Use draw_ray_with_scene_settings to respect color_mode settings
        # This applies proper tone mapping (linear/reinhard) and colorizedIntensity
        renderer.draw_ray_with_scene_settings(seg, scene, base_color=(255, 0, 0),
                                              stroke_width=1.5, extend_to_edge=False)

    renderer.save(output_file)
    if verbose:
        print(f"\nSaved to: {output_file}")
    save_csv(segments, output_dir)

    return True


def coupled_demo(
        color_mode: str = 'default',
        simulation_mode: str = 'rays',
        show_ray_arrows: bool = False,
        verbose: bool = True,
        min_brightness_exp: int = None,
    ):
    """Coupled Prisms demonstration.

    Problem Statement
    Demonstrate the behavior of light rays passing through two coupled prisms
    placed in sequence, showing refraction at each interface.

    Physics Background
    Snell's Law: n₁ * sin(θ₁) = n₂ * sin(θ₂)
    Refraction occurs at each interface based on refractive indices

    Expected Behavior
    Ray enters first prism (n=1.5) from air (n=1.0) → refracts inward
    Ray transmits unddisturbed at the interface, because the two prisms are coupled
    Ray exits second prism back to air → refracts outward

    Args:
        color_mode: Color rendering mode. Options: 'default', 'linear', 'linearRGB',
                   'reinhard', 'colorizedIntensity'. Default: 'default'
        simulation_mode: Simulation mode. Options: 'rays', 'extended', 'images',
                        'observer'. Default: 'rays'
        show_ray_arrows: Whether to display direction arrows on rays. Default: False
        verbose: Whether to print progress messages. Default: True
        min_brightness_exp: [PYTHON-SPECIFIC] Exponent for minimum brightness threshold.
                           The threshold is 10^(-min_brightness_exp). For example:
                           - 2 means threshold = 0.01 (1%)
                           - 6 means threshold = 1e-6 (1ppm)
                           If None (default), threshold is auto-determined by color_mode.
  """

    output_dir = os.path.join(os.path.dirname(__file__), 'output_coupled')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_file = output_dir + '/prisms_coupled.svg'

    if verbose:
        print("Setting up Coupled Prisms...\n")

    # Create scene
    scene = Scene()
    scene.ray_density = 0.1
    scene.color_mode = color_mode
    scene.mode = simulation_mode
    scene.show_ray_arrows = show_ray_arrows
    # PYTHON-SPECIFIC: Set explicit brightness threshold if provided
    if min_brightness_exp is not None:
        scene.min_brightness_exp = min_brightness_exp

    # Create measuring prism
    meas_prism = Glass(scene)
    meas_prism.path = [
        {'x': 167, 'y': 61, 'arc': False},
        {'x': 274, 'y': 61, 'arc': False},
        {'x': 188, 'y': 104, 'arc': False}
    ]
    meas_prism.not_done = False
    meas_prism.refIndex = 1.5

    # Create illumination prism with same y of measuring prism, in this way the two prisms are coupled
    ill_prism = Glass(scene)
    ill_prism.path = [
        {'x': 167, 'y': 61, 'arc': False},
        {'x': 274, 'y': 61, 'arc': False},
        {'x': 253, 'y': 13, 'arc': False}
    ]
    ill_prism.not_done = False
    ill_prism.refIndex = 1.5

    scene.add_object(meas_prism)
    scene.add_object(ill_prism)
    dict_ray={
        'ray1A': {'p1':[272,4],'p2':[258,15]}
    }

    ray_list: List[SingleRay] = []
    for ray in dict_ray:
        new_ray_source = SingleRay(scene)
        new_ray_source.p1 = {'x': dict_ray[ray]['p1'][0], 'y': dict_ray[ray]['p1'][1]}
        new_ray_source.p2 = {'x': dict_ray[ray]['p2'][0], 'y': dict_ray[ray]['p2'][1]}  #point along the ray
        new_ray_source.brightness = 1.0
        ray_list.append(new_ray_source)

    # Add sources to scene
    for ray_source in ray_list:
        scene.add_object(ray_source)

    # Run simulation
    # verbose levels: 0=silent (default), 1=verbose (ray processing), 2=debug (detailed refraction)
    simulator = Simulator(scene, max_rays=1000, verbose=0)
    segments = simulator.run()

    print(f"Rays traced: {simulator.processed_ray_count}")
    print(f"Segments: {len(segments)}")

    # Render
    renderer = SVGRenderer(width=800, height=600, viewbox=(0, 0, 300, 200))
    renderer.draw_line_segment(meas_prism.path[0], meas_prism.path[1], color='blue', stroke_width=2, label='MeasPrism')
    renderer.draw_line_segment(meas_prism.path[1], meas_prism.path[2], color='blue', stroke_width=2)
    renderer.draw_line_segment(meas_prism.path[2], meas_prism.path[0], color='blue', stroke_width=2)

    renderer.draw_line_segment(ill_prism.path[0], ill_prism.path[1], color='blue', stroke_width=2, label='IllPrism')
    renderer.draw_line_segment(ill_prism.path[1], ill_prism.path[2], color='blue', stroke_width=2)
    renderer.draw_line_segment(ill_prism.path[2], ill_prism.path[0], color='blue', stroke_width=2)

    for seg in segments:
        # Use draw_ray_with_scene_settings to respect color_mode settings
        renderer.draw_ray_with_scene_settings(seg, scene, base_color=(255, 0, 0),
                                              stroke_width=1.5, extend_to_edge=False)

    renderer.save(output_file)
    print(f"\nSaved to: {output_file}")
    save_csv(segments, output_dir)

    return True


def coupled_through_3rd_element_demo(
        medium_ref_index=1.33,
        prisms_ref_index=1.7,
        dict_ray={
            'ray1A': {'p1':[272,4],'p2':[258,15]}
        },
        save_svg:bool = True,
        save_csv_flag:bool = False,
        verbose:bool = False,
        output_dir:str = None,
        color_mode: str = 'default',
        simulation_mode: str = 'rays',
        show_ray_arrows: bool = False,
        min_brightness_exp: int = None,
        use_renderer_draw_routine:bool = False
    ):
    """Coupled Prisms demonstration.

    Problem Statement
    Demonstrate the behavior of light rays passing through two coupled prisms
    placed on a third element with imilar index of refraction.

    Physics Background
    Snell's Law: n₁ * sin(θ₁) = n₂ * sin(θ₂)
    Refraction occurs at each interface based on refractive indices

    Expected Behavior
    Ray enters first prism (n=<prisms_ref_index>) from air (n=1.0) → refracts inward
    When medium_ref_index is equal to prisms_ref_index ray transmits unddisturbed at the interface, because the two prisms are perfectly coupled
    Ray exits second prism back to air → refracts outward

    Args:
        medium_ref_index: Refractive index of the medium between prisms. Default: 1.33
        prisms_ref_index: Refractive index of the prisms. Default: 1.7
        dict_ray: Dictionary defining the input rays. Default: single ray from (272,4) to (258,15)
        save_svg: Whether to save the SVG output. Default: True
        save_csv_flag: Whether to save the CSV output. Default: False
        verbose: Whether to print progress messages. Default: False
        output_dir: Output directory path. Default: None (uses default location)
        color_mode: Color rendering mode. Options: 'default', 'linear', 'linearRGB',
                   'reinhard', 'colorizedIntensity'. Default: 'default'
        simulation_mode: Simulation mode. Options: 'rays', 'extended', 'images',
                        'observer'. Default: 'rays'
        show_ray_arrows: Whether to display direction arrows on rays. Default: False
        min_brightness_exp: [PYTHON-SPECIFIC] Exponent for minimum brightness threshold.
                           The threshold is 10^(-min_brightness_exp). For example:
                           - 2 means threshold = 0.01 (1%)
                           - 6 means threshold = 1e-6 (1ppm)
                           If None (default), threshold is auto-determined by color_mode.
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), 'output_coupled_through_3rd_element')

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_file = output_dir + '/prisms_coupled_3rd_element.svg'

    if verbose:print("Setting up Coupled Prism sistem...\n")

    # Create scene
    scene = Scene()
    scene.ray_density = 0.1
    scene.color_mode = color_mode
    scene.mode = simulation_mode
    scene.show_ray_arrows = show_ray_arrows
    # PYTHON-SPECIFIC: Set explicit brightness threshold if provided
    if min_brightness_exp is not None:
        scene.min_brightness_exp = min_brightness_exp

    # Create measuring prism
    meas_prism = Glass(scene)
    meas_prism.path = [
        {'x': 167, 'y': 61, 'arc': False},
        {'x': 274, 'y': 61, 'arc': False},
        {'x': 188, 'y': 104, 'arc': False}
    ]
    meas_prism.not_done = False
    meas_prism.refIndex = prisms_ref_index
    # Create medium in between prisms
    medium = Glass(scene)
    medium.path = [
        {'x': 167, 'y': 61, 'arc': False},
        {'x': 274, 'y': 61, 'arc': False},
        {'x': 274, 'y': 55, 'arc': False},
        {'x': 167, 'y': 55, 'arc': False}
    ]
    medium.not_done = False
    medium.refIndex = medium_ref_index

    # Create illumination prism
    ill_prism = Glass(scene)
    ill_prism.path = [
        {'x': 167, 'y': 55, 'arc': False},#y 55
        {'x': 274, 'y': 55, 'arc': False},#y 55
        {'x': 253, 'y': 13, 'arc': False}
    ]
    ill_prism.not_done = False
    ill_prism.refIndex = prisms_ref_index

    scene.add_object(meas_prism)
    scene.add_object(medium)
    scene.add_object(ill_prism)

    scene.auto_label_all_glass_cardinal()

    # add the ray sources
    ray_list: List[SingleRay] = []
    for ray in dict_ray:
        new_ray_source = SingleRay(scene)
        new_ray_source.p1 = {'x': dict_ray[ray]['p1'][0], 'y': dict_ray[ray]['p1'][1]}
        new_ray_source.p2 = {'x': dict_ray[ray]['p2'][0], 'y': dict_ray[ray]['p2'][1]}  #point along the ray
        new_ray_source.brightness = 1.0
        ray_list.append(new_ray_source)

    # Add sources to scene
    for ray_source in ray_list:
        scene.add_object(ray_source)

    # Run simulation
    # verbose levels: 0=silent (default), 1=verbose (ray processing), 2=debug (detailed refraction)
    simulator = Simulator(scene, max_rays=1000, verbose=0)
    segments = simulator.run()

    if verbose:
        print(f"Rays traced: {simulator.processed_ray_count}")
        print(f"Segments: {len(segments)}")

    # Render
    renderer = SVGRenderer(width=800, height=600, viewbox=(0, 0, 300, 200))
    # test of the new draw_scene method that should automatically draw all scene objects with the correct colors and labels, if use_renderer_draw_routine is set to True. If False, we use the old way of drawing each object manually, which is more verbose but allows for more customization.
    if use_renderer_draw_routine:
        renderer.draw_scene(scene,segments)
    else:
        # draw measuring prism
        renderer.draw_line_segment(meas_prism.path[0], meas_prism.path[1], color='blue', stroke_width=2, label='Prism', scene_obj=meas_prism)
        renderer.draw_line_segment(meas_prism.path[1], meas_prism.path[2], color='blue', stroke_width=2, scene_obj=meas_prism)
        renderer.draw_line_segment(meas_prism.path[2], meas_prism.path[0], color='blue', stroke_width=2, scene_obj=meas_prism)

        # draw medium
        renderer.draw_line_segment(medium.path[0], medium.path[1], color='green', stroke_width=2, label='Medium', scene_obj=medium)
        renderer.draw_line_segment(medium.path[1], medium.path[2], color='green', stroke_width=2, scene_obj=medium)
        renderer.draw_line_segment(medium.path[2], medium.path[3], color='green', stroke_width=2, scene_obj=medium)
        renderer.draw_line_segment(medium.path[3], medium.path[0], color='green', stroke_width=2, scene_obj=medium)
        # draw illumination prism
        renderer.draw_line_segment(ill_prism.path[0], ill_prism.path[1], color='blue', stroke_width=2, label='Prism', scene_obj=ill_prism)
        renderer.draw_line_segment(ill_prism.path[1], ill_prism.path[2], color='blue', stroke_width=2, scene_obj=ill_prism)
        renderer.draw_line_segment(ill_prism.path[2], ill_prism.path[0], color='blue', stroke_width=2, scene_obj=ill_prism)

        renderer.draw_glass_edge_labels(meas_prism)

        for seg in segments:
            # Use draw_ray_with_scene_settings to respect color_mode settings
            renderer.draw_ray_with_scene_settings(seg, scene, base_color=(255, 0, 0),
                                                stroke_width=1.5, extend_to_edge=False)
    if save_svg:
        renderer.save(output_file)
        print(f"\nSaved to: {output_file}")
    if save_csv_flag:
        save_csv(segments, output_dir)
    return True

def book_img_il():
    # dry run
    prisms_ref_index = 1.7
    medium_ref_index = 1.5
    dict_in_ray={
                'ray1A': {'p1':[272,4],'p2':[258,15]},
                'ray1B':{'p1':[271.4,2.58],'p2':[258,14]},
                'ray2A': {'p1':[280,20],'p2':[266,31]},
                'ray2B':{'p1':[280,18],'p2':[266,30]}
            }
    # Create scene
    scene = Scene()
    scene.ray_density = 0.1
    scene.color_mode = 'linear'
    scene.mode = 'rays'
    scene.show_ray_arrows = True
    scene.min_brightness_exp = 1
    # Create measuring prism
    meas_prism = Glass(scene)
    meas_prism.path = [
        {'x': 167, 'y': 61, 'arc': False},
        {'x': 274, 'y': 61, 'arc': False},
        {'x': 188, 'y': 104, 'arc': False}
    ]
    meas_prism.not_done = False
    meas_prism.refIndex = prisms_ref_index
    # Create medium in between prisms
    medium = Glass(scene)
    medium.path = [
        {'x': 167, 'y': 61, 'arc': False},
        {'x': 274, 'y': 61, 'arc': False},
        {'x': 274, 'y': 55, 'arc': False},
        {'x': 167, 'y': 55, 'arc': False}
    ]
    medium.not_done = False
    medium.refIndex = medium_ref_index

    # Create illumination prism
    ill_prism = Glass(scene)
    ill_prism.path = [
        {'x': 167, 'y': 55, 'arc': False},#y 55
        {'x': 274, 'y': 55, 'arc': False},#y 55
        {'x': 253, 'y': 13, 'arc': False}
    ]
    ill_prism.not_done = False
    ill_prism.refIndex = prisms_ref_index

    # add a lens
    lens = IdealLens(scene)
    lens.p1 = {'x': 155, 'y': 135}
    lens.p2 = {'x': 116, 'y': 93}
    lens.focal_length = 100

    scene.add_object(meas_prism)
    scene.add_object(medium)
    scene.add_object(ill_prism)
    scene.add_object(lens)

    # add the ray sources
    ray_list: List[SingleRay] = []
    for in_ray in dict_in_ray:
        new_ray_source = SingleRay(scene)
        new_ray_source.p1 = {'x': dict_in_ray[in_ray]['p1'][0], 'y': dict_in_ray[in_ray]['p1'][1]}
        new_ray_source.p2 = {'x': dict_in_ray[in_ray]['p2'][0], 'y': dict_in_ray[in_ray]['p2'][1]}  #point along the ray
        new_ray_source.brightness = 1.0
        ray_list.append(new_ray_source)

    # Add sources to scene
    for ray_source in ray_list:
        scene.add_object(ray_source)

    # Run simulation
    # verbose levels: 0=silent (default), 1=verbose (ray processing), 2=debug (detailed refraction)
    simulator = Simulator(scene, max_rays=1000, verbose=0)

    segments:List[Ray] = simulator.run()

    print(f"Rays traced: {simulator.processed_ray_count}")
    print(f"Segments: {len(segments)}")

    # Render
    renderer = SVGRenderer(width=800, height=600, viewbox=(0, 0, 300, 200))
    # draw measuring prism
    renderer.draw_line_segment(meas_prism.path[0], meas_prism.path[1], color='blue', stroke_width=2, label='Prism')
    renderer.draw_line_segment(meas_prism.path[1], meas_prism.path[2], color='blue', stroke_width=2)
    renderer.draw_line_segment(meas_prism.path[2], meas_prism.path[0], color='blue', stroke_width=2)

    # draw medium
    renderer.draw_line_segment(medium.path[0], medium.path[1], color='green', stroke_width=2, label='Medium')
    renderer.draw_line_segment(medium.path[1], medium.path[2], color='green', stroke_width=2)
    renderer.draw_line_segment(medium.path[2], medium.path[3], color='green', stroke_width=2)
    renderer.draw_line_segment(medium.path[3], medium.path[0], color='green', stroke_width=2)
    # draw illumination prism
    renderer.draw_line_segment(ill_prism.path[0], ill_prism.path[1], color='blue', stroke_width=2, label='Prism')
    renderer.draw_line_segment(ill_prism.path[1], ill_prism.path[2], color='blue', stroke_width=2)
    renderer.draw_line_segment(ill_prism.path[2], ill_prism.path[0], color='blue', stroke_width=2)
    # dravw lens
    renderer.draw_lens(
        lens.p1,
        lens.p2,
        lens.focal_length,
        color='blue',
        label=f'Lens (f={lens.focal_length})'
    )

    for i,seg in enumerate(segments):
        if seg.gap is True:
            print('seg ',i, 'is a gap ray')
        
        # Use draw_ray_with_scene_settings to respect color_mode settings
        renderer.draw_ray_with_scene_settings(seg, scene, base_color=(255, 0, 0),
                                                stroke_width=1.5, extend_to_edge=False)

    # draw the first two rays , which are gap rayy in a different color
    renderer.draw_ray_segment(segments[0],color='green', opacity=0.8, stroke_width=1.5,show_arrow=True,draw_gap_rays=True)    
    renderer.draw_ray_segment(segments[1],color='blue', opacity=0.8, stroke_width=1.5,show_arrow=True,draw_gap_rays=True)    
    renderer.draw_ray_segment(segments[2],color='green', opacity=0.8, stroke_width=1.5,show_arrow=True,draw_gap_rays=True)    
    renderer.draw_ray_segment(segments[3],color='blue', opacity=0.8, stroke_width=1.5,show_arrow=True,draw_gap_rays=True)    

    #HTML(renderer.to_string())

if __name__ == '__main__':
    # uncoupled_demo()
    # coupled_demo()
    coupled_through_3rd_element_demo(
        medium_ref_index=1.6, 
        prisms_ref_index=1.75, 
        dict_ray={
            'ray1A': {'p1':[272,4],'p2':[258,15]}
        },
        save_svg=True,
        save_csv_flag=True,
        verbose=True,
        color_mode= 'default',
        simulation_mode = 'observer',
        show_ray_arrows= True,
        min_brightness_exp=2,
        use_renderer_draw_routine=True
    )

