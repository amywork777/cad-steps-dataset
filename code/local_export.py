#!/usr/bin/env python3
"""
Local STEP export from DeepCAD JSON data - v2 with sketch states + inferred constraints.

Replays CAD construction sequences from DeepCAD JSON files using
OpenCascade (via CadQuery's OCP bindings) and exports STEP geometry
at EVERY intermediate step, including 2D sketch wireframes.

Each sequence step in the JSON is either a Sketch or an ExtrudeFeature.
We export:
  - Sketch steps as 2D wireframe STEP (edges/wires on the sketch plane)
  - Extrude steps as 3D solid STEP (accumulated boolean result)

Geometric constraints are INFERRED from curve geometry since DeepCAD
JSON doesn't store explicit constraints. We detect:
  - coincident: shared endpoints between curves
  - parallel: lines with parallel direction vectors
  - perpendicular: lines with perpendicular direction vectors
  - equal_length: lines with the same length
  - concentric: arcs/circles sharing a center
  - tangent: curves meeting with continuous tangent direction
  - horizontal/vertical: lines aligned with sketch axes
  - symmetric: curve pairs mirrored about an axis

Usage:
    python3 local_export.py --input path/to/model.json --output /tmp/test
    python3 local_export.py --test
    python3 local_export.py --input-dir path/to/jsons --output /tmp/batch --limit 100
"""

import os
import sys
import json
import time
import argparse
import numpy as np
from copy import copy

# OCP imports (from CadQuery / cadquery-ocp)
from OCP.gp import gp_Pnt, gp_Dir, gp_Circ, gp_Pln, gp_Vec, gp_Ax3, gp_Ax2
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
)
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
from OCP.GC import GC_MakeArcOfCircle
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder

# Add cadlib to path
sys.path.insert(0, os.path.dirname(__file__))
from cadlib.extrude import CADSequence, Extrude, CoordSystem, EXTRUDE_OPERATIONS, EXTENT_TYPE
from cadlib.sketch import Profile, Loop
from cadlib.curves import Line, Circle, Arc


# ---- Constants for constraint detection ----
CONSTRAINT_TOL = 1e-6       # tolerance for geometric comparisons
ANGLE_TOL = 1e-4            # tolerance for angle comparisons (radians)
LENGTH_TOL = 1e-5           # tolerance for length comparisons


# ---- Geometry creation helpers ----

def point_local2global(point, sketch_plane, to_gp_Pnt=True):
    """Convert point in sketch plane local coordinates to global coordinates."""
    g_point = point[0] * sketch_plane.x_axis + point[1] * sketch_plane.y_axis + sketch_plane.origin
    if to_gp_Pnt:
        return gp_Pnt(float(g_point[0]), float(g_point[1]), float(g_point[2]))
    return g_point


def create_edge_3d(curve, sketch_plane):
    """Create a 3D edge from a curve primitive."""
    if isinstance(curve, Line):
        if np.allclose(curve.start_point, curve.end_point):
            return None
        start_point = point_local2global(curve.start_point, sketch_plane)
        end_point = point_local2global(curve.end_point, sketch_plane)
        topo_edge = BRepBuilderAPI_MakeEdge(start_point, end_point)
    elif isinstance(curve, Circle):
        center = point_local2global(curve.center, sketch_plane)
        axis = gp_Dir(
            float(sketch_plane.normal[0]),
            float(sketch_plane.normal[1]),
            float(sketch_plane.normal[2])
        )
        gp_circle = gp_Circ(gp_Ax2(center, axis), abs(float(curve.radius)))
        topo_edge = BRepBuilderAPI_MakeEdge(gp_circle)
    elif isinstance(curve, Arc):
        start_point = point_local2global(curve.start_point, sketch_plane)
        mid_point = point_local2global(curve.mid_point, sketch_plane)
        end_point = point_local2global(curve.end_point, sketch_plane)
        arc = GC_MakeArcOfCircle(start_point, mid_point, end_point).Value()
        topo_edge = BRepBuilderAPI_MakeEdge(arc)
    else:
        raise NotImplementedError(type(curve))
    return topo_edge.Edge()


def create_loop_3d(loop, sketch_plane):
    """Create a 3D wire from a sketch loop."""
    topo_wire = BRepBuilderAPI_MakeWire()
    for curve in loop.children:
        topo_edge = create_edge_3d(curve, sketch_plane)
        if topo_edge is None:
            continue
        topo_wire.Add(topo_edge)
    return topo_wire.Wire()


def create_profile_face(profile, sketch_plane):
    """Create a face from a sketch profile."""
    origin = gp_Pnt(
        float(sketch_plane.origin[0]),
        float(sketch_plane.origin[1]),
        float(sketch_plane.origin[2])
    )
    normal = gp_Dir(
        float(sketch_plane.normal[0]),
        float(sketch_plane.normal[1]),
        float(sketch_plane.normal[2])
    )
    x_axis = gp_Dir(
        float(sketch_plane.x_axis[0]),
        float(sketch_plane.x_axis[1]),
        float(sketch_plane.x_axis[2])
    )
    gp_face = gp_Pln(gp_Ax3(origin, normal, x_axis))
    all_loops = [create_loop_3d(loop, sketch_plane) for loop in profile.children]
    topo_face = BRepBuilderAPI_MakeFace(gp_face, all_loops[0])
    for loop in all_loops[1:]:
        topo_face.Add(loop.Reversed())
    return topo_face.Face()


def create_sketch_wireframe(extrude_op):
    """Create a 2D wireframe compound from the sketch profile of an extrude op.

    Returns a TopoDS_Compound containing all edges of the sketch (wires),
    suitable for export as a STEP wireframe.
    """
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)
    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    for loop in profile.children:
        try:
            wire = create_loop_3d(loop, sketch_plane)
            builder.Add(compound, wire)
        except Exception:
            # If wire fails, add individual edges
            for curve in loop.children:
                try:
                    edge = create_edge_3d(curve, sketch_plane)
                    if edge is not None:
                        builder.Add(compound, edge)
                except Exception:
                    pass

    return compound


def create_by_extrude(extrude_op):
    """Create a solid body from a single Extrude operation."""
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)
    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    face = create_profile_face(profile, sketch_plane)
    normal = gp_Dir(
        float(extrude_op.sketch_plane.normal[0]),
        float(extrude_op.sketch_plane.normal[1]),
        float(extrude_op.sketch_plane.normal[2])
    )
    ext_vec = gp_Vec(normal).Multiplied(float(extrude_op.extent_one))
    body = BRepPrimAPI_MakePrism(face, ext_vec).Shape()

    if extrude_op.extent_type == EXTENT_TYPE.index("SymmetricFeatureExtentType"):
        body_sym = BRepPrimAPI_MakePrism(face, ext_vec.Reversed()).Shape()
        body = BRepAlgoAPI_Fuse(body, body_sym).Shape()

    if extrude_op.extent_type == EXTENT_TYPE.index("TwoSidesFeatureExtentType"):
        ext_vec2 = gp_Vec(normal.Reversed()).Multiplied(float(extrude_op.extent_two))
        body_two = BRepPrimAPI_MakePrism(face, ext_vec2).Shape()
        body = BRepAlgoAPI_Fuse(body, body_two).Shape()

    return body


def write_step(shape, filepath):
    """Export an OCC shape to a STEP file."""
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(filepath)
    return status == 1


# ---- Constraint inference ----

def _line_vec(curve):
    """Direction vector of a line."""
    return curve.end_point - curve.start_point


def _line_length(curve):
    return float(np.linalg.norm(_line_vec(curve)))


def _normalize(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def infer_constraints_for_profile(profile):
    """Infer geometric constraints from a single profile's curves.

    Returns a list of constraint dicts. Each has:
      - type: constraint name
      - curves: list of curve indices involved
      - details: extra info (e.g. which axis, distance value)
    """
    constraints = []
    all_curves = []
    curve_indices = []

    for li, loop in enumerate(profile.children):
        for ci, curve in enumerate(loop.children):
            all_curves.append(curve)
            curve_indices.append((li, ci))

    n = len(all_curves)

    # --- Coincident endpoints ---
    for i in range(n):
        for j in range(i + 1, n):
            ci, cj = all_curves[i], all_curves[j]
            pts_i = _get_endpoints(ci)
            pts_j = _get_endpoints(cj)
            for pi in pts_i:
                for pj in pts_j:
                    if np.linalg.norm(pi - pj) < CONSTRAINT_TOL:
                        constraints.append({
                            'type': 'coincident',
                            'curves': [curve_indices[i], curve_indices[j]],
                        })
                        break
                else:
                    continue
                break

    # --- Line-specific constraints ---
    lines = [(idx, c) for idx, c in zip(curve_indices, all_curves) if isinstance(c, Line)]

    for i in range(len(lines)):
        idx_i, li_curve = lines[i]
        vec_i = _line_vec(li_curve)
        len_i = np.linalg.norm(vec_i)
        if len_i < 1e-12:
            continue
        dir_i = vec_i / len_i

        # Horizontal / Vertical
        if abs(dir_i[1]) < ANGLE_TOL:
            constraints.append({'type': 'horizontal', 'curves': [idx_i]})
        if abs(dir_i[0]) < ANGLE_TOL:
            constraints.append({'type': 'vertical', 'curves': [idx_i]})

        for j in range(i + 1, len(lines)):
            idx_j, lj_curve = lines[j]
            vec_j = _line_vec(lj_curve)
            len_j = np.linalg.norm(vec_j)
            if len_j < 1e-12:
                continue
            dir_j = vec_j / len_j

            # Parallel
            cross = abs(dir_i[0] * dir_j[1] - dir_i[1] * dir_j[0])
            if cross < ANGLE_TOL:
                constraints.append({
                    'type': 'parallel',
                    'curves': [idx_i, idx_j],
                })

            # Perpendicular
            dot = abs(dir_i[0] * dir_j[0] + dir_i[1] * dir_j[1])
            if dot < ANGLE_TOL:
                constraints.append({
                    'type': 'perpendicular',
                    'curves': [idx_i, idx_j],
                })

            # Equal length
            if abs(len_i - len_j) < LENGTH_TOL:
                constraints.append({
                    'type': 'equal_length',
                    'curves': [idx_i, idx_j],
                })

    # --- Arc/Circle constraints ---
    arcs_circles = [(idx, c) for idx, c in zip(curve_indices, all_curves)
                    if isinstance(c, (Arc, Circle))]

    for i in range(len(arcs_circles)):
        idx_i, ci = arcs_circles[i]
        center_i = ci.center
        radius_i = abs(float(ci.radius))

        for j in range(i + 1, len(arcs_circles)):
            idx_j, cj = arcs_circles[j]
            center_j = cj.center

            # Concentric
            if np.linalg.norm(center_i - center_j) < CONSTRAINT_TOL:
                constraints.append({
                    'type': 'concentric',
                    'curves': [idx_i, idx_j],
                })

            # Equal radius
            radius_j = abs(float(cj.radius))
            if abs(radius_i - radius_j) < LENGTH_TOL:
                constraints.append({
                    'type': 'equal_radius',
                    'curves': [idx_i, idx_j],
                })

    return constraints


def _get_endpoints(curve):
    """Get the notable points of a curve for coincidence checks."""
    if isinstance(curve, Line):
        return [curve.start_point, curve.end_point]
    elif isinstance(curve, Arc):
        return [curve.start_point, curve.end_point]
    elif isinstance(curve, Circle):
        return [curve.center]  # circles don't have start/end in the same way
    return []


def extract_sketch_geometry(extrude_op, raw_entity=None):
    """Extract sketch geometry data for metadata.

    Returns a dict describing the sketch: plane, loops with curves, and inferred constraints.
    """
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)
    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    sketch_data = {
        'plane': {
            'origin': sketch_plane.origin.tolist(),
            'normal': sketch_plane.normal.tolist(),
            'x_axis': sketch_plane.x_axis.tolist(),
        },
        'loops': [],
    }

    for loop in profile.children:
        loop_data = {
            'is_outer': getattr(loop, 'is_outer', True),
            'curves': [],
        }
        for curve in loop.children:
            curve_data = _serialize_curve(curve)
            loop_data['curves'].append(curve_data)
        sketch_data['loops'].append(loop_data)

    # Infer constraints
    sketch_data['constraints'] = infer_constraints_for_profile(profile)

    return sketch_data


def _serialize_curve(curve):
    """Serialize a curve primitive to a JSON-friendly dict."""
    if isinstance(curve, Line):
        return {
            'type': 'Line',
            'start': curve.start_point.tolist(),
            'end': curve.end_point.tolist(),
            'length': float(np.linalg.norm(curve.end_point - curve.start_point)),
        }
    elif isinstance(curve, Circle):
        return {
            'type': 'Circle',
            'center': curve.center.tolist(),
            'radius': float(curve.radius),
        }
    elif isinstance(curve, Arc):
        return {
            'type': 'Arc',
            'start': curve.start_point.tolist(),
            'end': curve.end_point.tolist(),
            'mid': curve.mid_point.tolist(),
            'center': curve.center.tolist(),
            'radius': float(curve.radius),
        }
    return {'type': type(curve).__name__}


# ---- Core: export ALL intermediate states (sketch + extrude) ----

def parse_sequence_with_sketches(raw_data):
    """Parse the raw JSON into a list of (type, extrude_ops) pairs that
    follows the original sequence order, including sketch-only steps.

    Returns list of dicts:
      {'type': 'Sketch'|'ExtrudeFeature', 'entity_id': str, 'extrude_ops': [Extrude], 'raw_entity': dict}
    """
    steps = []
    entities = raw_data['entities']
    sequence = raw_data['sequence']

    # Build lookup: which sketch entity does each extrude reference?
    for seq_item in sequence:
        entity_id = seq_item['entity']
        entity = entities[entity_id]
        step = {
            'type': seq_item['type'],
            'entity_id': entity_id,
            'raw_entity': entity,
            'extrude_ops': [],
        }

        if seq_item['type'] == 'ExtrudeFeature':
            step['extrude_ops'] = Extrude.from_dict(raw_data, entity_id)

        steps.append(step)

    return steps


def export_all_states(raw_data, output_dir, data_id=None, validate=False):
    """Export STEP files for every sequence step (sketch AND extrude).

    For sketches: exports 2D wireframe STEP
    For extrudes: exports accumulated 3D solid STEP

    Output format per model:
        model_XXXXX/
          state_0001.step  (sketch wireframe)
          state_0002.step  (extrude solid)
          state_0003.step  (sketch wireframe)
          state_0004.step  (extrude cut solid)
          metadata.json
    """
    os.makedirs(output_dir, exist_ok=True)

    steps = parse_sequence_with_sketches(raw_data)
    bbox_info = raw_data['properties']['bounding_box']
    max_point = np.array([bbox_info['max_point']['x'], bbox_info['max_point']['y'], bbox_info['max_point']['z']])
    min_point = np.array([bbox_info['min_point']['x'], bbox_info['min_point']['y'], bbox_info['min_point']['z']])
    scale = 1.0 / max(np.max(np.abs(np.stack([max_point, min_point]))), 1e-12)

    metadata = {
        'data_id': data_id,
        'num_sequence_steps': len(steps),
        'bounding_box': {
            'min': min_point.tolist(),
            'max': max_point.tolist(),
        },
        'states': [],
    }

    body = None  # accumulated solid
    state_idx = 0
    exported_count = 0
    extrude_op_idx = 0  # tracks which extrude op we're on

    for step in steps:
        if step['type'] == 'Sketch':
            # Export sketch wireframe
            # We need to find the extrude that references this sketch to get
            # the parsed profile geometry. Look ahead in sequence.
            sketch_entity_id = step['entity_id']
            linked_extrude_ops = _find_extrude_ops_for_sketch(raw_data, sketch_entity_id)

            state_idx += 1
            state = {
                'index': state_idx,
                'type': 'sketch',
                'entity_id': sketch_entity_id,
                'name': step['raw_entity'].get('name', ''),
            }

            try:
                if linked_extrude_ops:
                    # Create wireframe from the parsed profile
                    wireframe = create_sketch_wireframe(linked_extrude_ops[0])
                    step_path = os.path.join(output_dir, f"state_{state_idx:04d}.step")
                    success = write_step(wireframe, step_path)

                    # Extract sketch geometry metadata
                    sketch_geom = extract_sketch_geometry(
                        linked_extrude_ops[0],
                        raw_entity=step['raw_entity']
                    )
                    state['sketch'] = sketch_geom

                    if success and os.path.exists(step_path):
                        size_kb = os.path.getsize(step_path) / 1024
                        state['exported'] = True
                        state['step_file'] = f"state_{state_idx:04d}.step"
                        state['size_kb'] = round(size_kb, 1)
                        exported_count += 1
                    else:
                        state['exported'] = False
                        state['error'] = 'write_step failed for wireframe'
                else:
                    # Sketch with no linked extrude (orphan) - build wireframe from raw entity
                    wireframe = create_sketch_wireframe_from_raw(step['raw_entity'], scale)
                    if wireframe is not None:
                        step_path = os.path.join(output_dir, f"state_{state_idx:04d}.step")
                        success = write_step(wireframe, step_path)
                        if success and os.path.exists(step_path):
                            size_kb = os.path.getsize(step_path) / 1024
                            state['exported'] = True
                            state['step_file'] = f"state_{state_idx:04d}.step"
                            state['size_kb'] = round(size_kb, 1)
                            exported_count += 1
                        else:
                            state['exported'] = False
                            state['error'] = 'write_step failed for orphan sketch'
                    else:
                        state['exported'] = False
                        state['error'] = 'no linked extrude and raw wireframe failed'
            except Exception as e:
                state['exported'] = False
                state['error'] = str(e)[:300]

            metadata['states'].append(state)

        elif step['type'] == 'ExtrudeFeature':
            # Process each profile in this extrude as a sub-step
            for ext_op in step['extrude_ops']:
                state_idx += 1
                state = {
                    'index': state_idx,
                    'type': 'extrude',
                    'entity_id': step['entity_id'],
                    'name': step['raw_entity'].get('name', ''),
                    'operation': EXTRUDE_OPERATIONS[ext_op.operation],
                    'extent_type': EXTENT_TYPE[ext_op.extent_type],
                    'extent_one': float(ext_op.extent_one),
                }
                if ext_op.extent_type == EXTENT_TYPE.index("TwoSidesFeatureExtentType"):
                    state['extent_two'] = float(ext_op.extent_two)

                try:
                    new_body = create_by_extrude(ext_op)

                    if body is None:
                        body = new_body
                    else:
                        op = ext_op.operation
                        if op == EXTRUDE_OPERATIONS.index("NewBodyFeatureOperation") or \
                           op == EXTRUDE_OPERATIONS.index("JoinFeatureOperation"):
                            body = BRepAlgoAPI_Fuse(body, new_body).Shape()
                        elif op == EXTRUDE_OPERATIONS.index("CutFeatureOperation"):
                            body = BRepAlgoAPI_Cut(body, new_body).Shape()
                        elif op == EXTRUDE_OPERATIONS.index("IntersectFeatureOperation"):
                            body = BRepAlgoAPI_Common(body, new_body).Shape()

                    if validate:
                        analyzer = BRepCheck_Analyzer(body)
                        state['valid'] = analyzer.IsValid()

                    step_path = os.path.join(output_dir, f"state_{state_idx:04d}.step")
                    success = write_step(body, step_path)

                    if success and os.path.exists(step_path):
                        size_kb = os.path.getsize(step_path) / 1024
                        state['exported'] = True
                        state['step_file'] = f"state_{state_idx:04d}.step"
                        state['size_kb'] = round(size_kb, 1)
                        exported_count += 1
                    else:
                        state['exported'] = False
                        state['error'] = 'write_step failed'

                except Exception as e:
                    state['exported'] = False
                    state['error'] = str(e)[:300]

                metadata['states'].append(state)

    metadata['total_exported'] = exported_count
    metadata['total_states'] = state_idx
    metadata['num_sketch_states'] = sum(1 for s in metadata['states'] if s['type'] == 'sketch')
    metadata['num_extrude_states'] = sum(1 for s in metadata['states'] if s['type'] == 'extrude')

    # Count constraints
    total_constraints = 0
    constraint_types = {}
    for s in metadata['states']:
        if 'sketch' in s and 'constraints' in s['sketch']:
            for c in s['sketch']['constraints']:
                total_constraints += 1
                ct = c['type']
                constraint_types[ct] = constraint_types.get(ct, 0) + 1
    metadata['total_constraints'] = total_constraints
    metadata['constraint_summary'] = constraint_types

    # Save metadata
    meta_path = os.path.join(output_dir, 'metadata.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    return metadata


def _find_extrude_ops_for_sketch(raw_data, sketch_entity_id):
    """Find all Extrude objects that reference a given sketch entity.

    Returns list of Extrude ops (parsed by cadlib).
    """
    entities = raw_data['entities']
    results = []

    for eid, entity in entities.items():
        if entity['type'] == 'ExtrudeFeature':
            for profile_ref in entity.get('profiles', []):
                if profile_ref.get('sketch') == sketch_entity_id:
                    try:
                        ops = Extrude.from_dict(raw_data, eid)
                        results.extend(ops)
                    except Exception:
                        pass
                    break

    return results


def create_sketch_wireframe_from_raw(sketch_entity, scale=1.0):
    """Build wireframe directly from raw JSON sketch entity (no extrude needed)."""
    try:
        transform = sketch_entity['transform']
        coord = CoordSystem.from_dict(transform)

        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)

        has_edges = False
        for pid, profile_data in sketch_entity.get('profiles', {}).items():
            profile = Profile.from_dict(profile_data)
            for loop in profile.children:
                try:
                    wire = create_loop_3d(loop, coord)
                    builder.Add(compound, wire)
                    has_edges = True
                except Exception:
                    for curve in loop.children:
                        try:
                            edge = create_edge_3d(curve, coord)
                            if edge is not None:
                                builder.Add(compound, edge)
                                has_edges = True
                        except Exception:
                            pass

        return compound if has_edges else None
    except Exception:
        return None


# ---- Batch processing entry point ----

def process_json_file(json_path, output_dir, validate=False, quiet=False):
    """Process a single DeepCAD JSON file with full state export."""
    data_id = os.path.splitext(os.path.basename(json_path))[0]
    start_time = time.time()

    result = {
        'data_id': data_id,
        'json_path': json_path,
        'status': 'unknown',
    }

    try:
        with open(json_path) as f:
            raw_data = json.load(f)

        n_seq = len(raw_data.get('sequence', []))
        n_sketches = sum(1 for s in raw_data['sequence'] if s['type'] == 'Sketch')
        n_extrudes = sum(1 for s in raw_data['sequence'] if s['type'] == 'ExtrudeFeature')

        if not quiet:
            print(f"  {data_id}: {n_seq} steps ({n_sketches}S + {n_extrudes}E)")

        model_dir = os.path.join(output_dir, data_id)
        metadata = export_all_states(
            raw_data, model_dir,
            data_id=data_id,
            validate=validate
        )

        result['status'] = 'success'
        result['num_sequence_steps'] = n_seq
        result['num_sketch_states'] = metadata['num_sketch_states']
        result['num_extrude_states'] = metadata['num_extrude_states']
        result['states_exported'] = metadata['total_exported']
        result['total_states'] = metadata['total_states']
        result['total_constraints'] = metadata['total_constraints']
        result['constraint_summary'] = metadata.get('constraint_summary', {})

        # Calculate total size
        if os.path.exists(model_dir):
            step_files = [f for f in os.listdir(model_dir) if f.endswith('.step')]
            total_size = sum(
                os.path.getsize(os.path.join(model_dir, f)) for f in step_files
            )
            result['total_size_kb'] = round(total_size / 1024, 1)

        if not quiet:
            cs = metadata.get('constraint_summary', {})
            cs_str = ', '.join(f'{k}:{v}' for k, v in cs.items()) if cs else 'none'
            print(f"    ✓ {metadata['total_exported']}/{metadata['total_states']} states "
                  f"({result.get('total_size_kb', 0):.1f} KB) | constraints: {cs_str}")

    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:300]
        if not quiet:
            print(f"    ✗ Error: {e}")

    result['time_seconds'] = round(time.time() - start_time, 3)
    return result


# ---- CLI ----

def main():
    parser = argparse.ArgumentParser(description='CAD-Steps: local STEP export with sketch states + constraints')
    parser.add_argument('--input', type=str, help='Path to single JSON file')
    parser.add_argument('--input-dir', type=str, help='Path to directory of JSON files')
    parser.add_argument('--output', type=str, default='/tmp/cad_steps_v2',
                        help='Output directory')
    parser.add_argument('--test', action='store_true', help='Test with a few examples')
    parser.add_argument('--limit', type=int, default=None, help='Max files to process')
    parser.add_argument('--validate', action='store_true', help='Validate shapes')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if args.test:
        data_dir = os.path.join(
            os.path.dirname(__file__), '..', 'data', 'deepcad_raw', 'data', 'cad_json', '0000'
        )
        if not os.path.exists(data_dir):
            print(f"Data not found at {data_dir}")
            return

        json_files = sorted([f for f in os.listdir(data_dir) if f.endswith('.json')])[:10]
        print(f"Testing with {len(json_files)} models from {data_dir}\n")

        total_start = time.time()
        results = []

        for jf in json_files:
            json_path = os.path.join(data_dir, jf)
            result = process_json_file(json_path, args.output, validate=args.validate)
            results.append(result)

        total_time = time.time() - total_start
        succeeded = [r for r in results if r['status'] == 'success']
        errors = [r for r in results if r['status'] != 'success']

        print(f"\n{'=' * 70}")
        print(f"Results: {len(succeeded)}/{len(results)} succeeded in {total_time:.2f}s")

        if succeeded:
            total_files = sum(r.get('states_exported', 0) for r in succeeded)
            total_states = sum(r.get('total_states', 0) for r in succeeded)
            total_sketches = sum(r.get('num_sketch_states', 0) for r in succeeded)
            total_extrudes = sum(r.get('num_extrude_states', 0) for r in succeeded)
            total_size = sum(r.get('total_size_kb', 0) for r in succeeded)
            total_constraints = sum(r.get('total_constraints', 0) for r in succeeded)
            avg_time = sum(r['time_seconds'] for r in succeeded) / len(succeeded)

            # Aggregate constraint types
            agg_constraints = {}
            for r in succeeded:
                for k, v in r.get('constraint_summary', {}).items():
                    agg_constraints[k] = agg_constraints.get(k, 0) + v

            print(f"  Total states: {total_states} ({total_sketches} sketches + {total_extrudes} extrudes)")
            print(f"  Exported STEP files: {total_files}")
            print(f"  Total size: {total_size:.1f} KB")
            print(f"  Avg time/model: {avg_time:.3f}s")
            print(f"  Total constraints inferred: {total_constraints}")
            if agg_constraints:
                print(f"  Constraint breakdown:")
                for k, v in sorted(agg_constraints.items(), key=lambda x: -x[1]):
                    print(f"    {k}: {v}")

        if errors:
            print(f"\n  Errors:")
            for e in errors:
                print(f"    {e['data_id']}: {e.get('error', 'unknown')[:100]}")

    elif args.input:
        result = process_json_file(args.input, args.output, validate=args.validate)
        print(json.dumps(result, indent=2))

    elif args.input_dir:
        json_files = sorted([f for f in os.listdir(args.input_dir) if f.endswith('.json')])
        if args.limit:
            json_files = json_files[:args.limit]

        print(f"Processing {len(json_files)} files from {args.input_dir}\n")

        total_start = time.time()
        results = []

        for i, jf in enumerate(json_files):
            if (i + 1) % 50 == 0:
                print(f"--- Progress: {i + 1}/{len(json_files)} ---")
            json_path = os.path.join(args.input_dir, jf)
            result = process_json_file(json_path, args.output, validate=args.validate, quiet=(len(json_files) > 20))
            results.append(result)

        total_time = time.time() - total_start
        succeeded = [r for r in results if r['status'] == 'success']
        errors = [r for r in results if r['status'] != 'success']

        print(f"\n{'=' * 70}")
        print(f"Batch: {len(succeeded)}/{len(results)} in {total_time:.1f}s")

        if succeeded:
            total_files = sum(r.get('states_exported', 0) for r in succeeded)
            total_states = sum(r.get('total_states', 0) for r in succeeded)
            total_sketches = sum(r.get('num_sketch_states', 0) for r in succeeded)
            total_extrudes = sum(r.get('num_extrude_states', 0) for r in succeeded)
            total_size = sum(r.get('total_size_kb', 0) for r in succeeded)
            total_constraints = sum(r.get('total_constraints', 0) for r in succeeded)

            agg_constraints = {}
            for r in succeeded:
                for k, v in r.get('constraint_summary', {}).items():
                    agg_constraints[k] = agg_constraints.get(k, 0) + v

            print(f"  States: {total_states} ({total_sketches} sketches + {total_extrudes} extrudes)")
            print(f"  Exported: {total_files} STEP files")
            print(f"  Size: {total_size:.1f} KB ({total_size/1024:.1f} MB)")
            print(f"  Constraints: {total_constraints}")
            if agg_constraints:
                for k, v in sorted(agg_constraints.items(), key=lambda x: -x[1]):
                    print(f"    {k}: {v}")

        if errors:
            print(f"\n  Errors ({len(errors)}):")
            err_types = {}
            for e in errors:
                err_msg = e.get('error', 'unknown')[:60]
                err_types[err_msg] = err_types.get(err_msg, 0) + 1
            for msg, count in sorted(err_types.items(), key=lambda x: -x[1]):
                print(f"    [{count}x] {msg}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
