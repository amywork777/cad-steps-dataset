#!/usr/bin/env python3
"""
Local STEP export from DeepCAD JSON data.

Replays CAD construction sequences from DeepCAD JSON files using
OpenCascade (via CadQuery's OCP bindings) and exports STEP geometry
at EVERY intermediate step -- including 2D sketch wireframes.

State numbering follows the original DeepCAD sequence order:
  state_0001.step  (sketch wireframe)
  state_0002.step  (extrude solid)
  state_0003.step  (next sketch wireframe, overlaid on existing solid)
  state_0004.step  (next extrude)
  ...

metadata.json includes per-step type info, sketch geometry, extrude
params, and inferred geometric constraints.

NO Onshape API required - everything runs locally.

Usage:
    python3 local_export.py --input ../data/deepcad_raw/data/cad_json/0000/00000007.json --output /tmp/test_export
    python3 local_export.py --test
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
    BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
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


# --------------- geometry helpers ---------------

def point_local2global(point, sketch_plane, to_gp_Pnt=True):
    """Convert 2D sketch-plane point to 3D global coordinates."""
    g = point[0] * sketch_plane.x_axis + point[1] * sketch_plane.y_axis + sketch_plane.origin
    if to_gp_Pnt:
        return gp_Pnt(float(g[0]), float(g[1]), float(g[2]))
    return g


def create_edge_3d(curve, sketch_plane):
    """Create a 3D OCC Edge from a DeepCAD curve object."""
    if isinstance(curve, Line):
        if np.allclose(curve.start_point, curve.end_point):
            return None
        sp = point_local2global(curve.start_point, sketch_plane)
        ep = point_local2global(curve.end_point, sketch_plane)
        return BRepBuilderAPI_MakeEdge(sp, ep).Edge()
    elif isinstance(curve, Circle):
        center = point_local2global(curve.center, sketch_plane)
        axis = gp_Dir(float(sketch_plane.normal[0]), float(sketch_plane.normal[1]), float(sketch_plane.normal[2]))
        gc = gp_Circ(gp_Ax2(center, axis), abs(float(curve.radius)))
        return BRepBuilderAPI_MakeEdge(gc).Edge()
    elif isinstance(curve, Arc):
        sp = point_local2global(curve.start_point, sketch_plane)
        mp = point_local2global(curve.mid_point, sketch_plane)
        ep = point_local2global(curve.end_point, sketch_plane)
        arc = GC_MakeArcOfCircle(sp, mp, ep).Value()
        return BRepBuilderAPI_MakeEdge(arc).Edge()
    else:
        raise NotImplementedError(type(curve))


def create_loop_wire(loop, sketch_plane):
    """Create a 3D wire from a sketch loop."""
    mk = BRepBuilderAPI_MakeWire()
    for curve in loop.children:
        edge = create_edge_3d(curve, sketch_plane)
        if edge is not None:
            mk.Add(edge)
    return mk.Wire()


def create_profile_face(profile, sketch_plane):
    """Create a planar face from a profile (outer loop + optional inner loops)."""
    origin = gp_Pnt(*[float(x) for x in sketch_plane.origin])
    normal = gp_Dir(*[float(x) for x in sketch_plane.normal])
    x_axis = gp_Dir(*[float(x) for x in sketch_plane.x_axis])
    gp_face = gp_Pln(gp_Ax3(origin, normal, x_axis))

    wires = [create_loop_wire(lp, sketch_plane) for lp in profile.children]
    mk = BRepBuilderAPI_MakeFace(gp_face, wires[0])
    for w in wires[1:]:
        from OCP.TopoDS import TopoDS
        try:
            reversed_wire = TopoDS.Wire_s(w.Reversed())
            mk.Add(reversed_wire)
        except Exception:
            mk.Add(w)
    return mk.Face()


def create_by_extrude(extrude_op):
    """Create a solid body from a single Extrude op."""
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)

    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    face = create_profile_face(profile, sketch_plane)
    normal = gp_Dir(*[float(x) for x in extrude_op.sketch_plane.normal])
    ext_vec = gp_Vec(normal).Multiplied(float(extrude_op.extent_one))
    body = BRepPrimAPI_MakePrism(face, ext_vec).Shape()

    if extrude_op.extent_type == EXTENT_TYPE.index("SymmetricFeatureExtentType"):
        body_sym = BRepPrimAPI_MakePrism(face, ext_vec.Reversed()).Shape()
        body = BRepAlgoAPI_Fuse(body, body_sym).Shape()

    if extrude_op.extent_type == EXTENT_TYPE.index("TwoSidesFeatureExtentType"):
        ext_vec2 = gp_Vec(normal.Reversed()).Multiplied(float(extrude_op.extent_two))
        body_two = BRepPrimAPI_MakePrism(face, ext_vec2).Shape()
        body = BRepAlgoAPI_Fuse(body, body_two).Shape()

    return body, sketch_plane


def create_sketch_wireframe(extrude_op):
    """
    Build a wireframe compound from a sketch profile (2D curves in 3D space).
    Returns an OCC TopoDS_Compound of edges/wires.
    """
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)

    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    for loop in profile.children:
        for curve in loop.children:
            edge = create_edge_3d(curve, sketch_plane)
            if edge is not None:
                builder.Add(compound, edge)

    return compound, sketch_plane


def make_compound_with_body(body, sketch_compound):
    """Combine existing solid body with new sketch wireframe into a compound."""
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    if body is not None:
        builder.Add(compound, body)
    builder.Add(compound, sketch_compound)
    return compound


def write_step(shape, filepath, compress=False):
    """Export an OCC shape to a STEP file (optionally gzipped)."""
    import gzip as _gzip
    import tempfile as _tempfile
    if compress:
        fd, tmp_path = _tempfile.mkstemp(suffix='.step')
        os.close(fd)
        try:
            writer = STEPControl_Writer()
            writer.Transfer(shape, STEPControl_AsIs)
            status = writer.Write(tmp_path)
            if status != 1:
                os.unlink(tmp_path)
                return False
            gz_path = filepath if filepath.endswith('.gz') else filepath + '.gz'
            with open(tmp_path, 'rb') as f_in:
                with _gzip.open(gz_path, 'wb', compresslevel=6) as f_out:
                    f_out.write(f_in.read())
            os.unlink(tmp_path)
            return True
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    else:
        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        return writer.Write(filepath) == 1


# --------------- constraint inference ---------------

def _pt(p):
    """Normalize point representation to tuple."""
    return (round(float(p[0]), 8), round(float(p[1]), 8))


def infer_sketch_constraints(profile):
    """
    Infer geometric constraints from sketch curve geometry.
    Returns a list of constraint dicts.

    DeepCAD JSON does NOT store explicit constraints, but the curve
    geometry encodes them implicitly. We detect:
      - coincident: endpoints that overlap
      - horizontal / vertical: lines aligned to axes
      - parallel / perpendicular: line-line angle relationships
      - equal_length: lines with identical length
      - concentric: circles/arcs sharing a center
      - equal_radius: circles/arcs with same radius
      - tangent: arc smoothly meeting a line (endpoint + direction match)
    """
    constraints = []
    all_curves = []
    for loop in profile.children:
        all_curves.extend(loop.children)

    # Collect lines and circles/arcs separately
    lines_data = []
    circle_data = []

    for idx, c in enumerate(all_curves):
        if isinstance(c, Line):
            sp, ep = _pt(c.start_point), _pt(c.end_point)
            dx = ep[0] - sp[0]
            dy = ep[1] - sp[1]
            length = np.sqrt(dx*dx + dy*dy)
            lines_data.append({
                'idx': idx, 'sp': sp, 'ep': ep,
                'dx': dx, 'dy': dy, 'length': length
            })
        elif isinstance(c, Circle):
            circle_data.append({
                'idx': idx, 'type': 'circle',
                'center': _pt(c.center), 'radius': round(float(c.radius), 8)
            })
        elif isinstance(c, Arc):
            circle_data.append({
                'idx': idx, 'type': 'arc',
                'center': _pt(c.center), 'radius': round(float(c.radius), 8),
                'sp': _pt(c.start_point), 'ep': _pt(c.end_point)
            })

    EPS = 1e-6

    # --- Line constraints ---
    for i, L in enumerate(lines_data):
        # Horizontal / vertical
        if abs(L['dy']) < EPS and L['length'] > EPS:
            constraints.append({'type': 'horizontal', 'curves': [L['idx']]})
        if abs(L['dx']) < EPS and L['length'] > EPS:
            constraints.append({'type': 'vertical', 'curves': [L['idx']]})

    # Pairwise line constraints
    for i in range(len(lines_data)):
        for j in range(i + 1, len(lines_data)):
            Li, Lj = lines_data[i], lines_data[j]

            # equal_length
            if abs(Li['length'] - Lj['length']) < EPS and Li['length'] > EPS:
                constraints.append({'type': 'equal_length', 'curves': [Li['idx'], Lj['idx']]})

            # parallel / perpendicular (via cross/dot product of direction)
            if Li['length'] > EPS and Lj['length'] > EPS:
                cross = abs(Li['dx'] * Lj['dy'] - Li['dy'] * Lj['dx'])
                dot = abs(Li['dx'] * Lj['dx'] + Li['dy'] * Lj['dy'])
                norm = Li['length'] * Lj['length']
                if cross / norm < EPS:
                    constraints.append({'type': 'parallel', 'curves': [Li['idx'], Lj['idx']]})
                if dot / norm < EPS:
                    constraints.append({'type': 'perpendicular', 'curves': [Li['idx'], Lj['idx']]})

    # --- Circle/arc constraints ---
    for i in range(len(circle_data)):
        for j in range(i + 1, len(circle_data)):
            Ci, Cj = circle_data[i], circle_data[j]
            # concentric
            cd = np.sqrt((Ci['center'][0] - Cj['center'][0])**2 +
                         (Ci['center'][1] - Cj['center'][1])**2)
            if cd < EPS:
                constraints.append({'type': 'concentric', 'curves': [Ci['idx'], Cj['idx']]})
            # equal_radius
            if abs(Ci['radius'] - Cj['radius']) < EPS:
                constraints.append({'type': 'equal_radius', 'curves': [Ci['idx'], Cj['idx']]})

    # --- Coincident endpoints ---
    endpoints = []
    for L in lines_data:
        endpoints.append((L['sp'], L['idx'], 'start'))
        endpoints.append((L['ep'], L['idx'], 'end'))
    for C in circle_data:
        if C['type'] == 'arc':
            endpoints.append((C['sp'], C['idx'], 'start'))
            endpoints.append((C['ep'], C['idx'], 'end'))

    # Group coincident points
    used = set()
    for i in range(len(endpoints)):
        if i in used:
            continue
        group = [i]
        for j in range(i + 1, len(endpoints)):
            if j in used:
                continue
            pi, pj = endpoints[i][0], endpoints[j][0]
            if abs(pi[0] - pj[0]) < EPS and abs(pi[1] - pj[1]) < EPS:
                # Only report coincident between DIFFERENT curves
                if endpoints[i][1] != endpoints[j][1]:
                    group.append(j)
                    used.add(j)
        if len(group) >= 2:
            curve_ids = list(set(endpoints[k][1] for k in group))
            if len(curve_ids) >= 2:
                constraints.append({
                    'type': 'coincident',
                    'curves': curve_ids,
                    'point': list(endpoints[i][0])
                })

    return constraints


# --------------- sketch metadata extraction ---------------

def extract_sketch_metadata(extrude_op, raw_entity):
    """
    Extract rich sketch metadata from a DeepCAD extrude op.
    Includes curve geometry in original coordinates and inferred constraints.
    """
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)

    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    # Build curve list
    curves_meta = []
    for loop_idx, loop in enumerate(profile.children):
        for curve_idx, curve in enumerate(loop.children):
            cm = {
                'loop': loop_idx,
                'index_in_loop': curve_idx,
            }
            if isinstance(curve, Line):
                cm['type'] = 'Line'
                cm['start'] = [round(float(x), 8) for x in curve.start_point]
                cm['end'] = [round(float(x), 8) for x in curve.end_point]
            elif isinstance(curve, Circle):
                cm['type'] = 'Circle'
                cm['center'] = [round(float(x), 8) for x in curve.center]
                cm['radius'] = round(float(curve.radius), 8)
            elif isinstance(curve, Arc):
                cm['type'] = 'Arc'
                cm['start'] = [round(float(x), 8) for x in curve.start_point]
                cm['end'] = [round(float(x), 8) for x in curve.end_point]
                cm['mid'] = [round(float(x), 8) for x in curve.mid_point]
                cm['center'] = [round(float(x), 8) for x in curve.center]
                cm['radius'] = round(float(curve.radius), 8)
            curves_meta.append(cm)

    # Plane info
    plane_meta = {
        'origin': [round(float(x), 8) for x in sketch_plane.origin],
        'normal': [round(float(x), 8) for x in sketch_plane.normal],
        'x_axis': [round(float(x), 8) for x in sketch_plane.x_axis],
        'y_axis': [round(float(x), 8) for x in sketch_plane.y_axis],
    }

    # Infer constraints
    constraints = infer_sketch_constraints(profile)

    return {
        'plane': plane_meta,
        'curves': curves_meta,
        'num_loops': len(profile.children),
        'num_curves': len(curves_meta),
        'constraints': constraints,
    }


# --------------- core export ---------------

def export_all_states(raw_data, output_dir, data_id=None, validate=False, compress=True):
    """
    Replay a DeepCAD JSON construction sequence, exporting STEP at EVERY step.

    For each entry in the "sequence" array:
      - Sketch: export wireframe compound (2D curves in 3D space).
        If a solid body already exists, the sketch is combined with it.
      - ExtrudeFeature: perform the boolean, export the resulting solid.

    Returns metadata dict.
    """
    os.makedirs(output_dir, exist_ok=True)

    sequence = raw_data['sequence']
    entities = raw_data['entities']

    metadata = {
        'data_id': data_id,
        'num_sequence_steps': len(sequence),
        'states': [],
    }

    body = None          # running solid
    exported = 0
    state_num = 0        # 1-based state counter

    # We need to track which sketches belong to which extrudes.
    # Build an index: sketch_entity_id -> list of Extrude objects
    # (an extrude can reference profiles from earlier sketches)
    sketch_to_extrude = {}
    for item in sequence:
        if item['type'] == 'ExtrudeFeature':
            ext_entity = entities[item['entity']]
            for prof_ref in ext_entity['profiles']:
                sid = prof_ref['sketch']
                if sid not in sketch_to_extrude:
                    sketch_to_extrude[sid] = []
                sketch_to_extrude[sid].append(item['entity'])

    for seq_item in sequence:
        step_type = seq_item['type']
        entity_id = seq_item['entity']
        entity = entities[entity_id]
        state_num += 1

        state = {
            'state_num': state_num,
            'sequence_index': seq_item['index'],
            'type': step_type,
            'entity_id': entity_id,
            'name': entity.get('name', ''),
        }

        try:
            if step_type == 'Sketch':
                # Build wireframe from ALL profiles in this sketch
                sketch_entity = entity
                sketch_plane_cs = CoordSystem.from_dict(sketch_entity['transform'])

                builder = BRep_Builder()
                sketch_compound = TopoDS_Compound()
                builder.MakeCompound(sketch_compound)

                all_sketch_meta = {}
                for profile_id, profile_data in sketch_entity['profiles'].items():
                    # Parse profile through cadlib
                    prof = Profile.from_dict(profile_data)
                    # We need the extrude that uses this profile for normalization params
                    # Find matching extrude
                    extrude_ids = sketch_to_extrude.get(entity_id, [])
                    matched_ext = None
                    for eid in extrude_ids:
                        ext_ent = entities[eid]
                        for pref in ext_ent['profiles']:
                            if pref['sketch'] == entity_id and pref['profile'] == profile_id:
                                matched_ext = Extrude.from_dict(raw_data, eid)
                                break
                        if matched_ext:
                            break

                    if matched_ext:
                        # Use the first Extrude instance for this profile
                        ext_op = matched_ext[0] if isinstance(matched_ext, list) else matched_ext
                        wireframe, _ = create_sketch_wireframe(ext_op)
                        builder.Add(sketch_compound, wireframe)

                        # Extract metadata
                        ext_op_copy = copy(ext_op)
                        all_sketch_meta[profile_id] = extract_sketch_metadata(ext_op_copy, sketch_entity)
                    else:
                        # Sketch not used by any extrude (orphan) - still try to export raw
                        all_sketch_meta[profile_id] = {'note': 'orphan sketch, no matching extrude'}

                # Combine with existing body if any
                if body is not None:
                    export_shape = make_compound_with_body(body, sketch_compound)
                else:
                    export_shape = sketch_compound

                ext = ".step.gz" if compress else ".step"


                step_path = os.path.join(output_dir, f"state_{state_num:04d}{ext}")
                success = write_step(export_shape, step_path, compress=compress)

                if success and os.path.exists(step_path):
                    size_kb = os.path.getsize(step_path) / 1024
                    state['exported'] = True
                    state['step_file'] = f"state_{state_num:04d}{ext}"
                    state['size_kb'] = round(size_kb, 1)
                    exported += 1
                else:
                    state['exported'] = False
                    state['error'] = 'write_step failed'

                state['sketch'] = all_sketch_meta
                plane_data = sketch_entity['transform']
                state['sketch_plane'] = {
                    'origin': [plane_data['origin']['x'], plane_data['origin']['y'], plane_data['origin']['z']],
                    'x_axis': [plane_data['x_axis']['x'], plane_data['x_axis']['y'], plane_data['x_axis']['z']],
                    'y_axis': [plane_data['y_axis']['x'], plane_data['y_axis']['y'], plane_data['y_axis']['z']],
                    'z_axis': [plane_data['z_axis']['x'], plane_data['z_axis']['y'], plane_data['z_axis']['z']],
                }

            elif step_type == 'ExtrudeFeature':
                ext_entity = entity
                extrude_ops = Extrude.from_dict(raw_data, entity_id)

                for ext_op in extrude_ops:
                    new_body, _ = create_by_extrude(ext_op)

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

                if validate and body is not None:
                    analyzer = BRepCheck_Analyzer(body)
                    state['valid'] = analyzer.IsValid()

                ext = ".step.gz" if compress else ".step"


                step_path = os.path.join(output_dir, f"state_{state_num:04d}{ext}")
                success = write_step(body, step_path, compress=compress)

                if success and os.path.exists(step_path):
                    size_kb = os.path.getsize(step_path) / 1024
                    state['exported'] = True
                    state['step_file'] = f"state_{state_num:04d}{ext}"
                    state['size_kb'] = round(size_kb, 1)
                    exported += 1
                else:
                    state['exported'] = False
                    state['error'] = 'write_step failed'

                state['operation'] = ext_entity['operation']
                state['extent_type'] = ext_entity['extent_type']
                state['extent_one'] = ext_entity['extent_one']['distance']['value']
                if ext_entity['extent_type'] == 'TwoSidesFeatureExtentType':
                    state['extent_two'] = ext_entity['extent_two']['distance']['value']
                state['taper_angle'] = ext_entity['extent_one'].get('taper_angle', {}).get('value', 0.0)

            else:
                state['exported'] = False
                state['error'] = f'unknown step type: {step_type}'

        except Exception as e:
            state['exported'] = False
            state['error'] = str(e)[:300]

        metadata['states'].append(state)

    metadata['total_exported'] = exported
    metadata['total_states'] = state_num

    # Bounding box from raw data
    if 'properties' in raw_data and 'bounding_box' in raw_data['properties']:
        bb = raw_data['properties']['bounding_box']
        metadata['bounding_box'] = {
            'min': [bb['min_point']['x'], bb['min_point']['y'], bb['min_point']['z']],
            'max': [bb['max_point']['x'], bb['max_point']['y'], bb['max_point']['z']],
        }

    meta_path = os.path.join(output_dir, 'metadata.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    return metadata


# --------------- batch processing ---------------

def process_json_file(json_path, output_dir, validate=False, quiet=False, compress=True):
    """Process a single DeepCAD JSON file. Returns result dict."""
    data_id = os.path.splitext(os.path.basename(json_path))[0]
    start_time = time.time()

    result = {'data_id': data_id, 'json_path': json_path, 'status': 'unknown'}

    try:
        with open(json_path) as f:
            raw_data = json.load(f)

        seq = raw_data.get('sequence', [])
        n_sketch = sum(1 for s in seq if s['type'] == 'Sketch')
        n_ext = sum(1 for s in seq if s['type'] == 'ExtrudeFeature')

        if not quiet:
            print(f"  Model {data_id}: {len(seq)} steps ({n_sketch}S + {n_ext}E)")

        model_dir = os.path.join(output_dir, data_id)
        metadata = export_all_states(
            raw_data, model_dir,
            data_id=data_id,
            validate=validate,
            compress=compress,
        )

        result['status'] = 'success'
        result['num_steps'] = len(seq)
        result['num_sketches'] = n_sketch
        result['num_extrudes'] = n_ext
        result['states_exported'] = metadata['total_exported']

        if os.path.exists(model_dir):
            step_files = [f for f in os.listdir(model_dir) if f.endswith('.step') or f.endswith('.step.gz')]
            total_size = sum(os.path.getsize(os.path.join(model_dir, f)) for f in step_files)
            result['total_size_kb'] = round(total_size / 1024, 1)
            result['step_files'] = len(step_files)

        if not quiet:
            print(f"    ✓ {metadata['total_exported']}/{metadata['total_states']} states "
                  f"({result.get('total_size_kb', 0):.1f} KB)")

    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:300]
        if not quiet:
            print(f"    ✗ Error: {e}")

    result['time_seconds'] = round(time.time() - start_time, 3)
    return result


# --------------- CLI ---------------

def main():
    parser = argparse.ArgumentParser(description='Local STEP export from DeepCAD JSON (v2 - all states)')
    parser.add_argument('--input', type=str, help='Single JSON file')
    parser.add_argument('--input-dir', type=str, help='Directory of JSON files')
    parser.add_argument('--output', type=str, default='/tmp/cad_steps_v2')
    parser.add_argument('--test', action='store_true', help='Quick test with 10 examples')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if args.test:
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'deepcad_raw', 'data', 'cad_json', '0000')
        if not os.path.exists(data_dir):
            print(f"Data not found at {data_dir}")
            return

        json_files = sorted([f for f in os.listdir(data_dir) if f.endswith('.json')])[:10]
        print(f"Testing {len(json_files)} models from {data_dir}\n")

        t0 = time.time()
        results = []
        for jf in json_files:
            r = process_json_file(os.path.join(data_dir, jf), args.output, validate=args.validate)
            results.append(r)

        elapsed = time.time() - t0
        ok = [r for r in results if r['status'] == 'success']
        err = [r for r in results if r['status'] != 'success']

        print(f"\n{'='*60}")
        print(f"Done: {len(ok)}/{len(results)} succeeded, {len(err)} errors, {elapsed:.1f}s")
        if ok:
            total_files = sum(r.get('step_files', 0) for r in ok)
            total_kb = sum(r.get('total_size_kb', 0) for r in ok)
            avg_t = sum(r['time_seconds'] for r in ok) / len(ok)
            print(f"  STEP files: {total_files}")
            print(f"  Total size: {total_kb:.1f} KB")
            print(f"  Avg time/model: {avg_t:.3f}s")

            # Constraint stats
            total_constraints = 0
            for r in ok:
                mpath = os.path.join(args.output, r['data_id'], 'metadata.json')
                if os.path.exists(mpath):
                    with open(mpath) as f:
                        meta = json.load(f)
                    for st in meta['states']:
                        if st['type'] == 'Sketch' and 'sketch' in st:
                            for pid, sdata in st['sketch'].items():
                                if isinstance(sdata, dict) and 'constraints' in sdata:
                                    total_constraints += len(sdata['constraints'])
            print(f"  Total inferred constraints: {total_constraints}")
        if err:
            print(f"\n  Errors:")
            for r in err:
                print(f"    {r['data_id']}: {r.get('error', '?')[:120]}")

    elif args.input:
        r = process_json_file(args.input, args.output, validate=args.validate)
        print(json.dumps(r, indent=2))

    elif args.input_dir:
        json_files = sorted([f for f in os.listdir(args.input_dir) if f.endswith('.json')])
        if args.limit:
            json_files = json_files[:args.limit]
        print(f"Processing {len(json_files)} files from {args.input_dir}")

        t0 = time.time()
        results = []
        for i, jf in enumerate(json_files):
            print(f"[{i+1}/{len(json_files)}]", end=" ")
            r = process_json_file(os.path.join(args.input_dir, jf), args.output, validate=args.validate)
            results.append(r)

        elapsed = time.time() - t0
        ok = [r for r in results if r['status'] == 'success']
        err = [r for r in results if r['status'] != 'success']
        print(f"\n{'='*60}")
        print(f"Batch: {len(ok)}/{len(results)} in {elapsed:.1f}s")
        if ok:
            total_files = sum(r.get('step_files', 0) for r in ok)
            total_kb = sum(r.get('total_size_kb', 0) for r in ok)
            print(f"  STEP files: {total_files}, Size: {total_kb:.1f} KB")
        if err:
            for r in err[:5]:
                print(f"  ERR {r['data_id']}: {r.get('error', '?')[:120]}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
