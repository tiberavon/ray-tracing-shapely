"""
Python-specific module: simulation result
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

===============================================================================
PYTHON-SPECIFIC MODULE: Simulation Result Container
===============================================================================
This module provides a container for simulation results that captures:
- The ray segments produced by the simulation
- The scene configuration at simulation time
- Metadata for correlating results across multiple runs

This enables LLM-friendly conversations about multiple simulations and their
relationships to scene configurations.
===============================================================================
"""

import uuid as uuid_module
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.ray import Ray
    from ..core.ray_lineage import RayLineage
    from ..core.scene import Scene


@dataclass
class SceneSnapshot:
    """
    Captures the state of a scene at a specific point in time.

    This is a lightweight snapshot that records identifying information
    and key settings, not a full serialization of the scene.

    Attributes:
        uuid: The scene's UUID at snapshot time
        name: The scene's display name
        object_count: Total number of objects in the scene
        optical_object_count: Number of optical objects
        object_uuids: List of UUIDs for all objects in the scene
        object_summary: Brief description of objects (e.g., "2 Glass, 1 PointSource")
        settings: Dictionary of key scene settings
    """
    uuid: str
    name: str
    object_count: int
    optical_object_count: int
    object_uuids: List[str]
    object_summary: str
    settings: Dict[str, Any]

    @classmethod
    def from_scene(cls, scene: 'Scene') -> 'SceneSnapshot':
        """
        Create a snapshot from a Scene object.

        Args:
            scene: The Scene to snapshot

        Returns:
            A SceneSnapshot capturing the scene's current state
        """
        # Collect object UUIDs
        object_uuids = []
        type_counts: Dict[str, int] = {}

        for obj in scene.objs:
            if hasattr(obj, 'uuid'):
                object_uuids.append(obj.uuid)

            # Count by type
            type_name = getattr(obj, 'type', obj.__class__.__name__)
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        # Build object summary
        summary_parts = [f"{count} {name}" for name, count in sorted(type_counts.items())]
        object_summary = ", ".join(summary_parts) if summary_parts else "empty"

        # Capture key settings
        settings = {
            'mode': scene.mode,
            'color_mode': scene.color_mode,
            'simulate_colors': scene.simulate_colors,
            'ray_density': scene.ray_density,
            'length_scale': scene.length_scale,
            'min_brightness_exp': scene.min_brightness_exp,
            'grazing_angle_threshold': scene.grazing_angle_threshold,
            'grazing_polarization_ratio_threshold': scene.grazing_polarization_ratio_threshold,
            'grazing_transmission_threshold': scene.grazing_transmission_threshold,
        }

        return cls(
            uuid=scene.uuid,
            name=scene.get_display_name(),
            object_count=len(scene.objs),
            optical_object_count=len(scene.optical_objs),
            object_uuids=object_uuids,
            object_summary=object_summary,
            settings=settings,
        )


@dataclass
class SimulationResult:
    """
    Container for simulation results with full context.

    This class wraps the ray segments returned by a simulation run along with
    metadata that allows correlating results with scene configurations. It
    enables conversations like:
    - "In simulation sim_abc123, which rays hit the prism?"
    - "Compare results between sim_001 and sim_002"
    - "What scene settings were used for sim_abc123?"

    Attributes:
        uuid: Unique identifier for this simulation run
        name: Optional human-readable name for this run
        timestamp: ISO format timestamp when simulation completed
        scene_snapshot: Snapshot of scene state at simulation time
        segments: The ray segments produced by the simulation
        max_rays: Maximum rays limit used for the simulation
        processed_ray_count: Number of rays actually processed
        total_truncation: Sum of truncated ray brightness
        undefined_behavior_count: Count of undefined behavior incidents
        warnings: List of warning messages from the simulation
        error: Error message if simulation failed, None otherwise
    """
    # Identification
    uuid: str
    name: Optional[str]
    timestamp: str

    # Scene context
    scene_snapshot: SceneSnapshot

    # Results
    segments: List['Ray']

    # Simulation parameters
    max_rays: int

    # Statistics
    processed_ray_count: int
    total_truncation: float = 0.0
    undefined_behavior_count: int = 0
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    # Lineage tracking (Python-specific)
    lineage: Optional['RayLineage'] = None

    @classmethod
    def create(
        cls,
        scene: 'Scene',
        segments: List['Ray'],
        max_rays: int,
        processed_ray_count: int,
        total_truncation: float = 0.0,
        undefined_behavior_count: int = 0,
        name: Optional[str] = None,
        lineage: Optional['RayLineage'] = None
    ) -> 'SimulationResult':
        """
        Create a SimulationResult from simulation outputs.

        This is the primary factory method for creating SimulationResult objects.

        Args:
            scene: The Scene that was simulated
            segments: The ray segments produced
            max_rays: Maximum rays limit used
            processed_ray_count: Number of rays processed
            total_truncation: Sum of truncated brightness (default: 0.0)
            undefined_behavior_count: Count of undefined behaviors (default: 0)
            name: Optional name for this simulation run
            lineage: Optional RayLineage tracker with parent-child relationships

        Returns:
            A new SimulationResult instance
        """
        # Collect warnings
        warnings = []
        if scene.warning:
            warnings.append(scene.warning)

        return cls(
            uuid=str(uuid_module.uuid4()),
            name=name,
            timestamp=datetime.now().isoformat(),
            scene_snapshot=SceneSnapshot.from_scene(scene),
            segments=segments,
            max_rays=max_rays,
            processed_ray_count=processed_ray_count,
            total_truncation=total_truncation,
            undefined_behavior_count=undefined_behavior_count,
            warnings=warnings,
            error=scene.error,
            lineage=lineage,
        )

    def get_display_name(self) -> str:
        """
        Get a display name for this simulation result.

        Returns the user-defined name if set, otherwise returns a combination
        of "Simulation" and a short UUID suffix.

        Returns:
            A string suitable for display (e.g., "TIR Test Run 1" or "Simulation_a1b2c3d4").
        """
        if self.name:
            return self.name
        short_uuid = self.uuid[:8]
        return f"Simulation_{short_uuid}"

    @property
    def segment_count(self) -> int:
        """Get the number of ray segments in the result."""
        return len(self.segments)

    @property
    def success(self) -> bool:
        """Check if the simulation completed successfully (no error)."""
        return self.error is None

    @property
    def hit_ray_limit(self) -> bool:
        """Check if the simulation hit the maximum ray limit."""
        return self.processed_ray_count >= self.max_rays

    # =========================================================================
    # PYTHON-SPECIFIC FEATURE: Wavelength and Source Analysis
    # =========================================================================
    # These methods enable analysis of ray results grouped by wavelength or
    # source, useful for prism dispersion studies and multi-wavelength sims.
    # =========================================================================

    @property
    def unique_wavelengths(self) -> Set[Optional[float]]:
        """
        Get the set of unique wavelengths in the simulation results.

        Returns:
            Set of wavelength values (includes None if white light rays present)
        """
        return {seg.wavelength for seg in self.segments}

    @property
    def unique_source_uuids(self) -> Set[Optional[str]]:
        """
        Get the set of unique source UUIDs in the simulation results.

        Returns:
            Set of source UUID strings (includes None if source not tracked)
        """
        return {getattr(seg, 'source_uuid', None) for seg in self.segments}

    @property
    def unique_labels(self) -> Set[Optional[str]]:
        """
        Get the set of unique source labels in the simulation results.

        Returns:
            Set of label strings (includes None if label not set)
        """
        return {getattr(seg, 'source_label', None) for seg in self.segments}

    def get_wavelength_groups(self) -> Dict[Optional[float], List['Ray']]:
        """
        Group ray segments by wavelength.

        Returns:
            Dictionary mapping wavelength (or None for white light) to list of rays

        Example:
            >>> groups = result.get_wavelength_groups()
            >>> red_rays = groups.get(650, [])
            >>> print(f"Red rays: {len(red_rays)}")
        """
        groups: Dict[Optional[float], List['Ray']] = defaultdict(list)
        for seg in self.segments:
            groups[seg.wavelength].append(seg)
        return dict(groups)

    def get_source_groups(self) -> Dict[Optional[str], List['Ray']]:
        """
        Group ray segments by source UUID.

        Returns:
            Dictionary mapping source UUID (or None) to list of rays

        Example:
            >>> groups = result.get_source_groups()
            >>> for source_uuid, rays in groups.items():
            ...     print(f"Source {source_uuid[:8]}: {len(rays)} rays")
        """
        groups: Dict[Optional[str], List['Ray']] = defaultdict(list)
        for seg in self.segments:
            source_uuid = getattr(seg, 'source_uuid', None)
            groups[source_uuid].append(seg)
        return dict(groups)

    def get_label_groups(self) -> Dict[Optional[str], List['Ray']]:
        """
        Group ray segments by source label.

        Returns:
            Dictionary mapping label (or None) to list of rays

        Example:
            >>> groups = result.get_label_groups()
            >>> red_rays = groups.get('Red Ray', [])
            >>> chief_rays = groups.get('Chief Ray', [])
        """
        groups: Dict[Optional[str], List['Ray']] = defaultdict(list)
        for seg in self.segments:
            label = getattr(seg, 'source_label', None)
            groups[label].append(seg)
        return dict(groups)

    def get_rays_by_wavelength(
        self,
        wavelength: float,
        tolerance: float = 1.0
    ) -> List['Ray']:
        """
        Get all rays near a specific wavelength.

        Args:
            wavelength: Target wavelength in nm
            tolerance: Tolerance in nm (default: 1.0)

        Returns:
            List of rays within tolerance of the target wavelength

        Example:
            >>> red_rays = result.get_rays_by_wavelength(650, tolerance=5)
        """
        return [
            seg for seg in self.segments
            if seg.wavelength is not None
            and abs(seg.wavelength - wavelength) <= tolerance
        ]

    def get_rays_by_label(self, label: str) -> List['Ray']:
        """
        Get all rays with a specific source label.

        Args:
            label: The source label to match (exact match)

        Returns:
            List of rays with the specified label

        Example:
            >>> red_rays = result.get_rays_by_label('Red Ray')
            >>> chief_rays = result.get_rays_by_label('Chief Ray')
        """
        return [
            seg for seg in self.segments
            if getattr(seg, 'source_label', None) == label
        ]

    def get_rays_by_source(self, source_uuid: str) -> List['Ray']:
        """
        Get all rays from a specific source.

        Args:
            source_uuid: The UUID of the source (can be partial, matches prefix)

        Returns:
            List of rays from the specified source

        Example:
            >>> rays = result.get_rays_by_source(red_source.uuid)
            >>> # Or with partial UUID:
            >>> rays = result.get_rays_by_source('abc123')
        """
        return [
            seg for seg in self.segments
            if getattr(seg, 'source_uuid', None) is not None
            and getattr(seg, 'source_uuid', '').startswith(source_uuid)
        ]

    def get_wavelength_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about wavelengths in the simulation.

        Returns:
            Dictionary with wavelength statistics:
            - wavelength_count: Number of unique wavelengths
            - wavelengths: Dict mapping wavelength to ray count
            - has_white_light: True if any rays have None wavelength
            - min_wavelength: Minimum wavelength (excluding None)
            - max_wavelength: Maximum wavelength (excluding None)

        Example:
            >>> stats = result.get_wavelength_statistics()
            >>> print(f"Wavelengths: {stats['wavelength_count']}")
            >>> for wl, count in stats['wavelengths'].items():
            ...     print(f"  {wl}nm: {count} rays")
        """
        groups = self.get_wavelength_groups()

        # Count rays per wavelength
        wavelength_counts = {wl: len(rays) for wl, rays in groups.items()}

        # Get numeric wavelengths only
        numeric_wavelengths = [wl for wl in groups.keys() if wl is not None]

        return {
            'wavelength_count': len(groups),
            'wavelengths': wavelength_counts,
            'has_white_light': None in groups,
            'min_wavelength': min(numeric_wavelengths) if numeric_wavelengths else None,
            'max_wavelength': max(numeric_wavelengths) if numeric_wavelengths else None,
        }

    def get_source_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about ray sources in the simulation.

        Returns:
            Dictionary with source statistics:
            - source_count: Number of unique sources
            - sources: Dict mapping source_uuid to {label, ray_count}
            - has_unlabeled: True if any rays have no source tracking

        Example:
            >>> stats = result.get_source_statistics()
            >>> for uuid, info in stats['sources'].items():
            ...     print(f"  {info['label']}: {info['ray_count']} rays")
        """
        source_groups = self.get_source_groups()
        label_by_uuid: Dict[Optional[str], Optional[str]] = {}

        # Build label mapping
        for seg in self.segments:
            source_uuid = getattr(seg, 'source_uuid', None)
            if source_uuid and source_uuid not in label_by_uuid:
                label_by_uuid[source_uuid] = getattr(seg, 'source_label', None)

        # Build source info
        sources = {}
        for source_uuid, rays in source_groups.items():
            if source_uuid is not None:
                sources[source_uuid] = {
                    'label': label_by_uuid.get(source_uuid),
                    'ray_count': len(rays),
                }

        return {
            'source_count': len([k for k in source_groups.keys() if k is not None]),
            'sources': sources,
            'has_unlabeled': None in source_groups,
        }

    def get_grazing_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about grazing incidence in the simulation.

        [PYTHON-SPECIFIC FEATURE]

        Grazing incidence occurs at angles near the critical angle, where
        polarization effects become extreme. Three independent criteria are tracked.

        Returns:
            Dictionary with grazing statistics:
            - grazing_angle_count: Rays flagged by angle criterion
            - grazing_polar_count: Rays flagged by polarization criterion
            - grazing_transm_count: Rays flagged by transmission criterion
            - grazing_any_count: Rays flagged by any criterion
            - has_grazing: True if any grazing events detected

        Example:
            >>> stats = result.get_grazing_statistics()
            >>> print(f"Grazing events: {stats['grazing_any_count']}")
            >>> if stats['has_grazing']:
            ...     print(f"  By angle: {stats['grazing_angle_count']}")
        """
        angle_count = sum(1 for seg in self.segments
                         if getattr(seg, 'is_grazing_result__angle', False))
        polar_count = sum(1 for seg in self.segments
                         if getattr(seg, 'is_grazing_result__polar', False))
        transm_count = sum(1 for seg in self.segments
                          if getattr(seg, 'is_grazing_result__transm', False))
        any_count = sum(1 for seg in self.segments
                       if (getattr(seg, 'is_grazing_result__angle', False) or
                           getattr(seg, 'is_grazing_result__polar', False) or
                           getattr(seg, 'is_grazing_result__transm', False)))

        return {
            'grazing_angle_count': angle_count,
            'grazing_polar_count': polar_count,
            'grazing_transm_count': transm_count,
            'grazing_any_count': any_count,
            'has_grazing': any_count > 0,
        }

    def get_tir_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about TIR (Total Internal Reflection) in the simulation.

        [PYTHON-SPECIFIC FEATURE]

        Returns:
            Dictionary with TIR statistics:
            - tir_count: Number of rays that experienced TIR
            - max_tir_count: Maximum TIR count in any ray lineage
            - has_tir: True if any TIR events detected

        Example:
            >>> stats = result.get_tir_statistics()
            >>> print(f"TIR events: {stats['tir_count']}")
        """
        tir_count = sum(1 for seg in self.segments
                       if getattr(seg, 'is_tir_result', False))
        max_tir = max((getattr(seg, 'tir_count', 0) for seg in self.segments), default=0)

        return {
            'tir_count': tir_count,
            'max_tir_count': max_tir,
            'has_tir': tir_count > 0,
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        status = "OK" if self.success else "ERROR"
        return (f"SimulationResult('{self.get_display_name()}', "
                f"segments={self.segment_count}, "
                f"rays={self.processed_ray_count}/{self.max_rays}, "
                f"status={status})")


def _escape_xml(text: str) -> str:
    """Escape special characters for XML."""
    if text is None:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def describe_simulation_result(
    result: SimulationResult,
    format: str = 'xml',
    include_segments: bool = False,
    max_segments: int = 100
) -> str:
    """
    Generate a formatted description of a simulation result.

    Args:
        result: The SimulationResult to describe
        format: Output format - 'xml' for XML, 'text' for human-readable
        include_segments: If True, include individual segment data
        max_segments: Maximum number of segments to include (default: 100)

    Returns:
        Formatted string describing the simulation result

    Example (XML format):
        >>> print(describe_simulation_result(result))
        <?xml version="1.0" encoding="UTF-8"?>
        <simulation_result>
          <identification>
            <uuid>abc123...</uuid>
            <name>TIR Test</name>
            <timestamp>YYYY-MM-DDThh:mm:ss</timestamp>
          </identification>
          <scene_snapshot>
            <uuid>def456...</uuid>
            <name>Scene_def456</name>
            <object_count>3</object_count>
            <object_summary>1 Glass, 1 PointSource, 1 Blocker</object_summary>
            <settings>
              <mode>rays</mode>
              <ray_density>0.1</ray_density>
              ...
            </settings>
          </scene_snapshot>
          <results>
            <segment_count>150</segment_count>
            <processed_ray_count>150</processed_ray_count>
            <max_rays>10000</max_rays>
            <hit_ray_limit>false</hit_ray_limit>
          </results>
          <status>
            <success>true</success>
            <warnings/>
          </status>
        </simulation_result>
    """
    if format == 'xml':
        return _describe_result_xml(result, include_segments, max_segments)
    else:
        return _describe_result_text(result, include_segments, max_segments)


def _describe_result_xml(
    result: SimulationResult,
    include_segments: bool,
    max_segments: int
) -> str:
    """Generate XML format for simulation result description."""
    lines = []

    # XML header
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<simulation_result>')

    # Identification section
    lines.append('  <identification>')
    lines.append(f'    <uuid>{_escape_xml(result.uuid)}</uuid>')
    if result.name:
        lines.append(f'    <name>{_escape_xml(result.name)}</name>')
    lines.append(f'    <display_name>{_escape_xml(result.get_display_name())}</display_name>')
    lines.append(f'    <timestamp>{_escape_xml(result.timestamp)}</timestamp>')
    lines.append('  </identification>')

    # Scene snapshot section
    snap = result.scene_snapshot
    lines.append('  <scene_snapshot>')
    lines.append(f'    <uuid>{_escape_xml(snap.uuid)}</uuid>')
    lines.append(f'    <name>{_escape_xml(snap.name)}</name>')
    lines.append(f'    <object_count>{snap.object_count}</object_count>')
    lines.append(f'    <optical_object_count>{snap.optical_object_count}</optical_object_count>')
    lines.append(f'    <object_summary>{_escape_xml(snap.object_summary)}</object_summary>')

    # Scene settings
    lines.append('    <settings>')
    for key, value in snap.settings.items():
        lines.append(f'      <{key}>{_escape_xml(str(value))}</{key}>')
    lines.append('    </settings>')

    # Object UUIDs (abbreviated if many)
    if snap.object_uuids:
        lines.append('    <object_uuids>')
        for obj_uuid in snap.object_uuids[:20]:  # Limit to first 20
            lines.append(f'      <object_uuid>{_escape_xml(obj_uuid)}</object_uuid>')
        if len(snap.object_uuids) > 20:
            lines.append(f'      <!-- ... and {len(snap.object_uuids) - 20} more -->')
        lines.append('    </object_uuids>')

    lines.append('  </scene_snapshot>')

    # Results section
    lines.append('  <results>')
    lines.append(f'    <segment_count>{result.segment_count}</segment_count>')
    lines.append(f'    <processed_ray_count>{result.processed_ray_count}</processed_ray_count>')
    lines.append(f'    <max_rays>{result.max_rays}</max_rays>')
    lines.append(f'    <hit_ray_limit>{str(result.hit_ray_limit).lower()}</hit_ray_limit>')
    lines.append(f'    <total_truncation>{result.total_truncation:.6f}</total_truncation>')
    lines.append(f'    <undefined_behavior_count>{result.undefined_behavior_count}</undefined_behavior_count>')
    lines.append('  </results>')

    # Status section
    lines.append('  <status>')
    lines.append(f'    <success>{str(result.success).lower()}</success>')
    if result.error:
        lines.append(f'    <error>{_escape_xml(result.error)}</error>')
    if result.warnings:
        lines.append('    <warnings>')
        for warning in result.warnings:
            lines.append(f'      <warning>{_escape_xml(warning)}</warning>')
        lines.append('    </warnings>')
    else:
        lines.append('    <warnings/>')
    lines.append('  </status>')

    # Wavelength analysis section (Python-specific)
    wl_stats = result.get_wavelength_statistics()
    if wl_stats['wavelength_count'] > 0:
        lines.append('  <wavelength_analysis>')
        lines.append(f'    <wavelength_count>{wl_stats["wavelength_count"]}</wavelength_count>')
        lines.append(f'    <has_white_light>{str(wl_stats["has_white_light"]).lower()}</has_white_light>')
        if wl_stats['min_wavelength'] is not None:
            lines.append(f'    <min_wavelength>{wl_stats["min_wavelength"]}</min_wavelength>')
            lines.append(f'    <max_wavelength>{wl_stats["max_wavelength"]}</max_wavelength>')
        lines.append('    <wavelengths>')
        for wl, count in sorted(wl_stats['wavelengths'].items(), key=lambda x: (x[0] is None, x[0])):
            wl_str = 'white' if wl is None else str(wl)
            lines.append(f'      <wavelength nm="{wl_str}" ray_count="{count}"/>')
        lines.append('    </wavelengths>')
        lines.append('  </wavelength_analysis>')

    # Source analysis section (Python-specific)
    src_stats = result.get_source_statistics()
    if src_stats['source_count'] > 0:
        lines.append('  <source_analysis>')
        lines.append(f'    <source_count>{src_stats["source_count"]}</source_count>')
        lines.append(f'    <has_unlabeled>{str(src_stats["has_unlabeled"]).lower()}</has_unlabeled>')
        lines.append('    <sources>')
        for uuid, info in src_stats['sources'].items():
            label_attr = f' label="{_escape_xml(info["label"])}"' if info['label'] else ''
            lines.append(f'      <source uuid="{_escape_xml(uuid)}"{label_attr} ray_count="{info["ray_count"]}"/>')
        lines.append('    </sources>')
        lines.append('  </source_analysis>')

    # TIR analysis section (Python-specific)
    tir_stats = result.get_tir_statistics()
    if tir_stats['has_tir']:
        lines.append('  <tir_analysis>')
        lines.append(f'    <tir_count>{tir_stats["tir_count"]}</tir_count>')
        lines.append(f'    <max_tir_count>{tir_stats["max_tir_count"]}</max_tir_count>')
        lines.append('  </tir_analysis>')

    # Grazing incidence analysis section (Python-specific)
    grazing_stats = result.get_grazing_statistics()
    if grazing_stats['has_grazing']:
        lines.append('  <grazing_analysis>')
        lines.append(f'    <grazing_any_count>{grazing_stats["grazing_any_count"]}</grazing_any_count>')
        lines.append(f'    <grazing_angle_count>{grazing_stats["grazing_angle_count"]}</grazing_angle_count>')
        lines.append(f'    <grazing_polar_count>{grazing_stats["grazing_polar_count"]}</grazing_polar_count>')
        lines.append(f'    <grazing_transm_count>{grazing_stats["grazing_transm_count"]}</grazing_transm_count>')
        lines.append('  </grazing_analysis>')

    # Optional segments section
    if include_segments and result.segments:
        lines.append('  <segments>')
        for i, seg in enumerate(result.segments[:max_segments]):
            brightness = seg.brightness_s + seg.brightness_p
            tir_attrs = ""
            if getattr(seg, 'is_tir_result', False):
                tir_attrs += ' is_tir_result="true"'
            if getattr(seg, 'caused_tir', False):
                tir_attrs += ' caused_tir="true"'

            # Add grazing incidence attributes
            grazing_attrs = ""
            if getattr(seg, 'is_grazing_result__angle', False):
                grazing_attrs += ' grazing_angle="true"'
            if getattr(seg, 'is_grazing_result__polar', False):
                grazing_attrs += ' grazing_polar="true"'
            if getattr(seg, 'is_grazing_result__transm', False):
                grazing_attrs += ' grazing_transm="true"'

            # Add source label attribute if present
            source_label = getattr(seg, 'source_label', None)
            label_attr = f' label="{_escape_xml(source_label)}"' if source_label else ''

            # Handle both dict and Point objects for p1/p2
            p1_x = seg.p1['x'] if isinstance(seg.p1, dict) else seg.p1.x
            p1_y = seg.p1['y'] if isinstance(seg.p1, dict) else seg.p1.y
            p2_x = seg.p2['x'] if isinstance(seg.p2, dict) else seg.p2.x
            p2_y = seg.p2['y'] if isinstance(seg.p2, dict) else seg.p2.y

            # Add polarization attributes
            polar_ratio = getattr(seg, 'polarization_ratio', None)
            dop = getattr(seg, 'degree_of_polarization', None)
            polar_attrs = ""
            if polar_ratio is not None:
                pr_str = "inf" if polar_ratio == float('inf') else f"{polar_ratio:.4f}"
                polar_attrs += f' polar_ratio="{pr_str}"'
            if dop is not None:
                polar_attrs += f' dop="{dop:.4f}"'

            lines.append(f'    <segment index="{i}" brightness="{brightness:.4f}"{tir_attrs}{grazing_attrs}{polar_attrs}{label_attr}>')
            lines.append(f'      <p1 x="{p1_x:.4f}" y="{p1_y:.4f}"/>')
            lines.append(f'      <p2 x="{p2_x:.4f}" y="{p2_y:.4f}"/>')
            if seg.wavelength is not None:
                lines.append(f'      <wavelength>{seg.wavelength}</wavelength>')
            # Add source UUID if present
            source_uuid = getattr(seg, 'source_uuid', None)
            if source_uuid:
                lines.append(f'      <source_uuid>{_escape_xml(source_uuid)}</source_uuid>')
            lines.append('    </segment>')

        if len(result.segments) > max_segments:
            lines.append(f'    <!-- ... and {len(result.segments) - max_segments} more segments -->')
        lines.append('  </segments>')

    lines.append('</simulation_result>')

    return "\n".join(lines)


def _describe_result_text(
    result: SimulationResult,
    include_segments: bool,
    max_segments: int
) -> str:
    """Generate human-readable text format for simulation result description."""
    lines = []

    # Header
    lines.append("")
    lines.append("=" * 70)
    lines.append(f"Simulation Result: {result.get_display_name()}")
    lines.append("=" * 70)

    # Identification
    lines.append(f"\nUUID: {result.uuid}")
    lines.append(f"Timestamp: {result.timestamp}")

    # Scene info
    snap = result.scene_snapshot
    lines.append(f"\nScene: {snap.name} (uuid: {snap.uuid[:8]}...)")
    lines.append(f"Objects: {snap.object_summary}")
    lines.append(f"Total objects: {snap.object_count} ({snap.optical_object_count} optical)")

    # Settings
    lines.append("\nScene Settings:")
    for key, value in snap.settings.items():
        lines.append(f"  {key}: {value}")

    # Results
    lines.append("\nResults:")
    lines.append(f"  Segments: {result.segment_count}")
    lines.append(f"  Processed rays: {result.processed_ray_count} / {result.max_rays}")
    if result.hit_ray_limit:
        lines.append("  *** HIT RAY LIMIT ***")
    lines.append(f"  Total truncation: {result.total_truncation:.6f}")
    lines.append(f"  Undefined behaviors: {result.undefined_behavior_count}")

    # Status
    lines.append("\nStatus:")
    lines.append(f"  Success: {result.success}")
    if result.error:
        lines.append(f"  Error: {result.error}")
    if result.warnings:
        lines.append("  Warnings:")
        for warning in result.warnings:
            lines.append(f"    - {warning}")

    # Wavelength analysis (Python-specific)
    wl_stats = result.get_wavelength_statistics()
    if wl_stats['wavelength_count'] > 0:
        lines.append("\nWavelength Analysis:")
        lines.append(f"  Unique wavelengths: {wl_stats['wavelength_count']}")
        if wl_stats['min_wavelength'] is not None:
            lines.append(f"  Range: {wl_stats['min_wavelength']}nm - {wl_stats['max_wavelength']}nm")
        if wl_stats['has_white_light']:
            lines.append("  White light (None): present")
        lines.append("  By wavelength:")
        for wl, count in sorted(wl_stats['wavelengths'].items(), key=lambda x: (x[0] is None, x[0])):
            wl_str = 'white' if wl is None else f'{wl}nm'
            lines.append(f"    {wl_str}: {count} rays")

    # Source analysis (Python-specific)
    src_stats = result.get_source_statistics()
    if src_stats['source_count'] > 0:
        lines.append("\nSource Analysis:")
        lines.append(f"  Unique sources: {src_stats['source_count']}")
        lines.append("  By source:")
        for uuid, info in src_stats['sources'].items():
            label = info['label'] or f"(uuid: {uuid[:8]}...)"
            lines.append(f"    {label}: {info['ray_count']} rays")

    # TIR analysis (Python-specific)
    tir_stats = result.get_tir_statistics()
    if tir_stats['has_tir']:
        lines.append("\nTIR (Total Internal Reflection) Analysis:")
        lines.append(f"  TIR events: {tir_stats['tir_count']}")
        lines.append(f"  Max TIR count in lineage: {tir_stats['max_tir_count']}")

    # Grazing incidence analysis (Python-specific)
    grazing_stats = result.get_grazing_statistics()
    if grazing_stats['has_grazing']:
        lines.append("\nGrazing Incidence Analysis:")
        lines.append(f"  Total grazing events: {grazing_stats['grazing_any_count']}")
        lines.append(f"  By angle criterion: {grazing_stats['grazing_angle_count']}")
        lines.append(f"  By polarization criterion: {grazing_stats['grazing_polar_count']}")
        lines.append(f"  By transmission criterion: {grazing_stats['grazing_transm_count']}")

    # Optional segments
    if include_segments and result.segments:
        lines.append(f"\nSegments (first {min(max_segments, len(result.segments))} of {len(result.segments)}):")
        lines.append("-" * 90)
        lines.append(f"{'Index':>6} | {'Label':>12} | {'WL(nm)':>7} | {'Brightness':>10} | {'P1':>16} | {'P2':>16} | TIR")
        lines.append("-" * 90)

        for i, seg in enumerate(result.segments[:max_segments]):
            brightness = seg.brightness_s + seg.brightness_p
            # Handle both dict and Point objects for p1/p2
            p1_x = seg.p1['x'] if isinstance(seg.p1, dict) else seg.p1.x
            p1_y = seg.p1['y'] if isinstance(seg.p1, dict) else seg.p1.y
            p2_x = seg.p2['x'] if isinstance(seg.p2, dict) else seg.p2.x
            p2_y = seg.p2['y'] if isinstance(seg.p2, dict) else seg.p2.y
            p1_str = f"({p1_x:.1f}, {p1_y:.1f})"
            p2_str = f"({p2_x:.1f}, {p2_y:.1f})"
            tir_str = ""
            if getattr(seg, 'is_tir_result', False):
                tir_str = "TIR"
            if getattr(seg, 'caused_tir', False):
                tir_str += "->TIR"
            # Add label and wavelength
            label = getattr(seg, 'source_label', None) or ''
            label_str = label[:12] if len(label) > 12 else label
            wl_str = str(int(seg.wavelength)) if seg.wavelength else '-'
            lines.append(f"{i:>6} | {label_str:>12} | {wl_str:>7} | {brightness:>10.4f} | {p1_str:>16} | {p2_str:>16} | {tir_str}")

        if len(result.segments) > max_segments:
            lines.append(f"  ... and {len(result.segments) - max_segments} more segments")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


# Example usage and testing
if __name__ == "__main__":
    print("Testing SimulationResult class...\n")

    # Create mock objects for testing
    class MockScene:
        def __init__(self):
            self._uuid = str(uuid_module.uuid4())
            self.name = "Test Scene"
            self.objs = []
            self.optical_objs = []
            self.mode = 'rays'
            self.color_mode = 'default'
            self.simulate_colors = False
            self.ray_density = 0.1
            self.length_scale = 1.0
            self.min_brightness_exp = None
            self.warning = None
            self.error = None

        @property
        def uuid(self):
            return self._uuid

        def get_display_name(self):
            return self.name if self.name else f"Scene_{self._uuid[:8]}"

    class MockObject:
        def __init__(self, obj_type):
            self._uuid = str(uuid_module.uuid4())
            self.type = obj_type

        @property
        def uuid(self):
            return self._uuid

    class MockRay:
        def __init__(self, p1, p2, brightness=1.0):
            self.p1 = p1
            self.p2 = p2
            self.brightness_s = brightness / 2
            self.brightness_p = brightness / 2
            self.wavelength = None
            self.is_tir_result = False
            self.caused_tir = False

    # Test 1: Create SceneSnapshot
    print("Test 1: SceneSnapshot from Scene")
    scene = MockScene()
    scene.objs = [MockObject('Glass'), MockObject('Glass'), MockObject('PointSource')]
    scene.optical_objs = scene.objs.copy()

    snapshot = SceneSnapshot.from_scene(scene)
    print(f"  Scene UUID: {snapshot.uuid[:8]}...")
    print(f"  Scene name: {snapshot.name}")
    print(f"  Object count: {snapshot.object_count}")
    print(f"  Object summary: {snapshot.object_summary}")
    print(f"  Settings: {snapshot.settings}")

    # Test 2: Create SimulationResult
    print("\nTest 2: SimulationResult.create()")
    rays = [
        MockRay({'x': 0, 'y': 0}, {'x': 100, 'y': 0}, 1.0),
        MockRay({'x': 100, 'y': 0}, {'x': 150, 'y': 50}, 0.8),
        MockRay({'x': 150, 'y': 50}, {'x': 200, 'y': 50}, 0.6),
    ]
    rays[1].is_tir_result = True  # Mark as TIR result

    result = SimulationResult.create(
        scene=scene,
        segments=rays,
        max_rays=10000,
        processed_ray_count=3,
        total_truncation=0.001,
        name="Test Run 1"
    )

    print(f"  {result}")
    print(f"  Display name: {result.get_display_name()}")
    print(f"  Success: {result.success}")
    print(f"  Hit ray limit: {result.hit_ray_limit}")

    # Test 3: XML output
    print("\nTest 3: describe_simulation_result() - XML format")
    xml_output = describe_simulation_result(result, format='xml')
    print(xml_output[:1500] + "...\n")

    # Test 4: Text output
    print("\nTest 4: describe_simulation_result() - Text format")
    text_output = describe_simulation_result(result, format='text')
    print(text_output)

    # Test 5: With segments
    print("\nTest 5: describe_simulation_result() with segments")
    xml_with_segments = describe_simulation_result(result, format='xml', include_segments=True)
    print(xml_with_segments)

    # Test 6: Error case
    print("\nTest 6: Simulation with error")
    scene_error = MockScene()
    scene_error.error = "Ray limit exceeded"
    scene_error.warning = "Some rays were truncated"

    result_error = SimulationResult.create(
        scene=scene_error,
        segments=[],
        max_rays=100,
        processed_ray_count=100,
        name="Error Test"
    )

    print(f"  {result_error}")
    print(f"  Success: {result_error.success}")
    print(f"  Error: {result_error.error}")
    print(f"  Warnings: {result_error.warnings}")

    print("\nSimulationResult test completed successfully!")
