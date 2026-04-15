#!/usr/bin/env python3
"""
Local STEP export from DeepCAD JSON data (v2).

Exports STEP geometry at EVERY intermediate step including 2D sketch wireframes.
Infers geometric constraints from curve geometry.

State numbering follows the DeepCAD sequence:
  state_0001.step  (sketch wireframe)
  state_0002.step  (extrude solid)
  state_0003.step  (next sketch wireframe on top of existing solid)
  state_0004.step  (next extrude)
  ...

Usage:
    python3 local_export.py --test
    python3 local_export.py --input path/to/model.json --output /tmp/out
    python3 local_export.py --input-dir path/to/jsons --output /tmp/batch --limit 200
"""

import os
import sys
import json
import time
import argparse
import numpy as np
from copy import copy

from OCP.gp import gp_Pnt, gp_Dir, gp_Circ, gp_Pln, gp_Vec, gp_Ax3, gp_Ax2
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire,
)
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
from OCP.GC import GC_MakeArcOfCircle
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopoDS import TopoDS_Compound, TopoDS
from OCP.BRep import BRep_Builder

sys.path.insert(0, os.path.dirname(__file__))
from cadlib.extrude import CADSequence, Extrude, CoordSystem, EXTRUDE_OPERATIONS, EXTENT_TYPE
from cadlib.sketch import Profile, Loop
from cadlib.curves import Line, Circle, Arc


# =============== geometry helpers ===============

def point_local2global(point, sketch_plane, to_gp_Pnt=True):
    g = point[0] * sketch_plane.x_axis + point[1] * sketch_plane.y_axis + sketch_plane.origin
    if to_gp_Pnt:
        return gp_Pnt(float(g[0]), float(g[1]), float(g[2]))
    return g


def create_edge_3d(curve, sketch_plane):
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
    mk = BRepBuilderAPI_MakeWire()
    for curve in loop.children:
        edge = create_edge_3d(curve, sketch_plane)
        if edge is not None:
            mk.Add(edge)
    return mk.Wire()


def create_profile_face(profile, sketch_plane):
    origin = gp_Pnt(*[float(x) for x in sketch_plane.origin])
    normal = gp_Dir(*[float(x) for x in sketch_plane.normal])
    x_axis = gp_Dir(*[float(x) for x in sketch_plane.x_axis])
    gp_face = gp_Pln(gp_Ax3(origin, normal, x_axis))

    wires = [create_loop_wire(lp, sketch_plane) for lp in profile.children]
    mk = BRepBuilderAPI_MakeFace(gp_face, wires[0])
    for w in wires[1:]:
        try:
            reversed_wire = TopoDS.Wire_s(w.Reversed())
            mk.Add(reversed_wire)
        except Exception:
            mk.Add(w)
    return mk.Face()


def create_by_extrude(extrude_op):
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
    """Build wireframe compound from a sketch profile."""
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)
    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    for loop in profile.children:
        for curve in loop.children:
            try:
                edge = create_edge_3d(curve, sketch_plane)
                if edge is not None:
                    builder.Add(compound, edge)
            except Exception:
                pass

    return compound, sketch_plane


def make_compound_with_body(body, sketch_compound):
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    if body is not None:
        builder.Add(compound, body)
    builder.Add(compound, sketch_compound)
    return compound


def write_step(shape, filepath):
    if shape is None:
        return False
    try:
        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        return writer.Write(filepath) == 1
    except Exception:
        return False


# =============== constraint inference ===============

def _pt(p):
    return (round(float(p[0]), 8), round(float(p[1]), 8))


def infer_sketch_constraints(profile):
    """Infer geometric constraints from curve geometry."""
    constraints = []
    all_curves = []
    for loop in profile.children:
        all_curves.extend(loop.children)

    lines_data = []
    circle_data = []
    EPS = 1e-6

    for idx, c in enumerate(all_curves):
        if isinstance(c, Line):
            sp, ep = _pt(c.start_point), _pt(c.end_point)
            dx = ep[0] - sp[0]
            dy = ep[1] - sp[1]
            length = np.sqrt(dx*dx + dy*dy)
            lines_data.append({'idx': idx, 'sp': sp, 'ep': ep, 'dx': dx, 'dy': dy, 'length': length})
        elif isinstance(c, Circle):
            circle_data.append({'idx': idx, 'type': 'circle', 'center': _pt(c.center), 'radius': round(float(c.radius), 8)})
        elif isinstance(c, Arc):
            circle_data.append({
                'idx': idx, 'type': 'arc', 'center': _pt(c.center),
                'radius': round(float(c.radius), 8),
                'sp': _pt(c.start_point), 'ep': _pt(c.end_point)
            })

    # Line constraints
    for i, L in enumerate(lines_data):
        if abs(L['dy']) < EPS and L['length'] > EPS:
            constraints.append({'type': 'horizontal', 'curves': [L['idx']]})
        if abs(L['dx']) < EPS and L['length'] > EPS:
            constraints.append({'type': 'vertical', 'curves': [L['idx']]})

    for i in range(len(lines_data)):
        for j in range(i + 1, len(lines_data)):
            Li, Lj = lines_data[i], lines_data[j]
            if abs(Li['length'] - Lj['length']) < EPS and Li['length'] > EPS:
                constraints.append({'type': 'equal_length', 'curves': [Li['idx'], Lj['idx']]})
            if Li['length'] > EPS and Lj['length'] > EPS:
                norm = Li['length'] * Lj['length']
                cross = abs(Li['dx'] * Lj['dy'] - Li['dy'] * Lj['dx'])
                dot = abs(Li['dx'] * Lj['dx'] + Li['dy'] * Lj['dy'])
                if cross / norm < EPS:
                    constraints.append({'type': 'parallel', 'curves': [Li['idx'], Lj['idx']]})
                if dot / norm < EPS:
                    constraints.append({'type': 'perpendicular', 'curves': [Li['idx'], Lj['idx']]})

    # Circle/arc constraints
    for i in range(len(circle_data)):
        for j in range(i + 1, len(circle_data)):
            Ci, Cj = circle_data[i], circle_data[j]
            cd = np.sqrt((Ci['center'][0]-Cj['center'][0])**2 + (Ci['center'][1]-Cj['center'][1])**2)
            if cd < EPS:
                constraints.append({'type': 'concentric', 'curves': [Ci['idx'], Cj['idx']]})
            if abs(Ci['radius'] - Cj['radius']) < EPS:
                constraints.append({'type': 'equal_radius', 'curves': [Ci['idx'], Cj['idx']]})

    # Coincident endpoints
    endpoints = []
    for L in lines_data:
        endpoints.append((L['sp'], L['idx'], 'start'))
        endpoints.append((L['ep'], L['idx'], 'end'))
    for C in circle_data:
        if C['type'] == 'arc':
            endpoints.append((C['sp'], C['idx'], 'start'))
            endpoints.append((C['ep'], C['idx'], 'end'))

    used = set()
    for i in range(len(endpoints)):
        if i in used:
            continue
        group = [i]
        for j in range(i + 1, len(endpoints)):
            if j in used:
                continue
            pi, pj = endpoints[i][0], endpoints[j][0]
            if abs(pi[0]-pj[0]) < EPS and abs(pi[1]-pj[1]) < EPS:
                if endpoints[i][1] != endpoints[j][1]:
                    group.append(j)
                    used.add(j)
        if len(group) >= 2:
            curve_ids = list(set(endpoints[k][1] for k in group))
            if len(curve_ids) >= 2:
                constraints.append({
                    'type': 'coincident', 'curves': curve_ids,
                    'point': list(endpoints[i][0])
                })

    return constraints


# =============== sketch metadata extraction ===============

def extract_sketch_metadata(extrude_op):
    """Extract sketch curves and inferred constraints as metadata."""
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)
    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    curves_meta = []
    for loop_idx, loop in enumerate(profile.children):
        for curve_idx, curve in enumerate(loop.children):
            cm = {'loop': loop_idx, 'index_in_loop': curve_idx}
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

    plane_meta = {
        'origin': [round(float(x), 8) for x in sketch_plane.origin],
        'normal': [round(float(x), 8) for x in sketch_plane.normal],
        'x_axis': [round(float(x), 8) for x in sketch_plane.x_axis],
        'y_axis': [round(float(x), 8) for x in sketch_plane.y_axis],
    }

    constraints = infer_sketch_constraints(profile)

    return {
        'plane': plane_meta,
        'curves': curves_meta,
        'num_loops': len(profile.children),
        'num_curves': len(curves_meta),
        'constraints': constraints,
    }


# =============== core export ===============

def export_all_states(raw_data, output_dir, data_id=None, validate=False):
    """
    Export STEP at every sequence step (Sketch + ExtrudeFeature).
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

    body = None
    exported = 0
    state_num = 0

    # Build index: sketch_entity_id -> extrude_entity_ids that reference it
    sketch_to_extrude = {}
    for item in sequence:
        if item['type'] == 'ExtrudeFeature':
            ext_entity = entities[item['entity']]
            for prof_ref in ext_entity.get('profiles', []):
                sid = prof_ref.get('sketch')
                if sid:
                    sketch_to_extrude.setdefault(sid, []).append(item['entity'])

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
                sketch_entity = entity

                builder = BRep_Builder()
                sketch_compound = TopoDS_Compound()
                builder.MakeCompound(sketch_compound)

                all_sketch_meta = {}
                has_edges = False

                for profile_id, profile_data in sketch_entity.get('profiles', {}).items():
                    extrude_ids = sketch_to_extrude.get(entity_id, [])
                    matched_ext_op = None

                    for eid in extrude_ids:
                        ext_ent = entities[eid]
                        for pref in ext_ent.get('profiles', []):
                            if pref.get('sketch') == entity_id and pref.get('profile') == profile_id:
                                try:
                                    ops = Extrude.from_dict(raw_data, eid)
                                    if ops:
                                        matched_ext_op = ops[0]
                                except Exception:
                                    pass
                                break
                        if matched_ext_op:
                            break

                    if matched_ext_op:
                        wireframe, _ = create_sketch_wireframe(matched_ext_op)
                        builder.Add(sketch_compound, wireframe)
                        has_edges = True
                        all_sketch_meta[profile_id] = extract_sketch_metadata(matched_ext_op)
                    else:
                        all_sketch_meta[profile_id] = {'note': 'orphan sketch (no matching extrude)'}

                # Combine with existing body
                if body is not None:
                    export_shape = make_compound_with_body(body, sketch_compound)
                else:
                    export_shape = sketch_compound

                step_path = os.path.join(output_dir, f"state_{state_num:04d}.step")
                if has_edges:
                    success = write_step(export_shape, step_path)
                else:
                    success = False

                if success and os.path.exists(step_path):
                    size_kb = os.path.getsize(step_path) / 1024
                    state['exported'] = True
                    state['step_file'] = f"state_{state_num:04d}.step"
                    state['size_kb'] = round(size_kb, 1)
                    exported += 1
                else:
                    state['exported'] = False
                    if not has_edges:
                        state['error'] = 'no edges in sketch (orphan)'
                    else:
                        state['error'] = 'write_step failed'

                state['sketch'] = all_sketch_meta
                plane_data = sketch_entity.get('transform', {})
                if plane_data:
                    state['sketch_plane'] = {
                        'origin': [plane_data['origin']['x'], plane_data['origin']['y'], plane_data['origin']['z']],
                        'x_axis': [plane_data['x_axis']['x'], plane_data['x_axis']['y'], plane_data['x_axis']['z']],
                        'y_axis': [plane_data['y_axis']['x'], plane_data['y_axis']['y'], plane_data['y_axis']['z']],
                        'z_axis': [plane_data['z_axis']['x'], plane_data['z_axis']['y'], plane_data['z_axis']['z']],
                    }

            elif step_type == 'ExtrudeFeature':
                ext_entity = entity

                try:
                    extrude_ops = Extrude.from_dict(raw_data, entity_id)
                except Exception as e:
                    extrude_ops = []
                    state['parse_error'] = str(e)[:200]

                if not extrude_ops:
                    state['exported'] = False
                    state['error'] = 'no profiles in extrude (empty profiles list)'
                    state['operation'] = ext_entity.get('operation', '')
                    metadata['states'].append(state)
                    continue

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

                step_path = os.path.join(output_dir, f"state_{state_num:04d}.step")
                success = write_step(body, step_path)

                if success and os.path.exists(step_path):
                    size_kb = os.path.getsize(step_path) / 1024
                    state['exported'] = True
                    state['step_file'] = f"state_{state_num:04d}.step"
                    state['size_kb'] = round(size_kb, 1)
                    exported += 1
                else:
                    state['exported'] = False
                    state['error'] = 'write_step failed (invalid shape)'

                state['operation'] = ext_entity.get('operation', '')
                state['extent_type'] = ext_entity.get('extent_type', '')
                state['extent_one'] = ext_entity.get('extent_one', {}).get('distance', {}).get('value', 0.0)
                if ext_entity.get('extent_type') == 'TwoSidesFeatureExtentType':
                    state['extent_two'] = ext_entity.get('extent_two', {}).get('distance', {}).get('value', 0.0)
                state['taper_angle'] = ext_entity.get('extent_one', {}).get('taper_angle', {}).get('value', 0.0)

            else:
                state['exported'] = False
                state['error'] = f'unknown step type: {step_type}'

        except Exception as e:
            state['exported'] = False
            state['error'] = str(e)[:300]

        metadata['states'].append(state)

    metadata['total_exported'] = exported
    metadata['total_states'] = state_num

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


# =============== batch processing ===============

def process_json_file(json_path, output_dir, validate=False, quiet=False):
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
            print(f"  {data_id}: {len(seq)} steps ({n_sketch}S + {n_ext}E)")

        model_dir = os.path.join(output_dir, data_id)
        metadata = export_all_states(raw_data, model_dir, data_id=data_id, validate=validate)

        result['status'] = 'success'
        result['num_steps'] = len(seq)
        result['num_sketches'] = n_sketch
        result['num_extrudes'] = n_ext
        result['states_exported'] = metadata['total_exported']
        result['total_states'] = metadata['total_states']

        if os.path.exists(model_dir):
            step_files = [f for f in os.listdir(model_dir) if f.endswith('.step')]
            total_size = sum(os.path.getsize(os.path.join(model_dir, f)) for f in step_files)
            result['total_size_kb'] = round(total_size / 1024, 1)
            result['step_files'] = len(step_files)

        # Count constraints
        total_c = 0
        for st in metadata['states']:
            if st['type'] == 'Sketch' and 'sketch' in st:
                for pid, sd in st['sketch'].items():
                    if isinstance(sd, dict) and 'constraints' in sd:
                        total_c += len(sd['constraints'])
        result['total_constraints'] = total_c

        if not quiet:
            print(f"    ✓ {metadata['total_exported']}/{metadata['total_states']} states "
                  f"({result.get('total_size_kb', 0):.1f} KB, {total_c} constraints)")

    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:300]
        if not quiet:
            print(f"    ✗ Error: {e}")

    result['time_seconds'] = round(time.time() - start_time, 3)
    return result


# =============== CLI ===============

def main():
    parser = argparse.ArgumentParser(description='CAD-Steps: local STEP export with sketch states + constraints')
    parser.add_argument('--input', type=str)
    parser.add_argument('--input-dir', type=str)
    parser.add_argument('--output', type=str, default='/tmp/cad_steps_v2')
    parser.add_argument('--test', action='store_true')
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
        print(f"Testing {len(json_files)} models\n")

        t0 = time.time()
        results = []
        for jf in json_files:
            r = process_json_file(os.path.join(data_dir, jf), args.output, validate=args.validate)
            results.append(r)

        elapsed = time.time() - t0
        ok = [r for r in results if r['status'] == 'success']
        err = [r for r in results if r['status'] != 'success']

        print(f"\n{'='*60}")
        print(f"Done: {len(ok)}/{len(results)} succeeded, {elapsed:.1f}s")
        if ok:
            total_files = sum(r.get('step_files', 0) for r in ok)
            total_kb = sum(r.get('total_size_kb', 0) for r in ok)
            total_states = sum(r.get('total_states', 0) for r in ok)
            total_exported = sum(r.get('states_exported', 0) for r in ok)
            total_constraints = sum(r.get('total_constraints', 0) for r in ok)
            avg_t = sum(r['time_seconds'] for r in ok) / len(ok)
            print(f"  States: {total_exported}/{total_states} exported")
            print(f"  STEP files: {total_files}")
            print(f"  Size: {total_kb:.1f} KB")
            print(f"  Avg time/model: {avg_t:.3f}s")
            print(f"  Inferred constraints: {total_constraints}")
        if err:
            for r in err:
                print(f"  ERR {r['data_id']}: {r.get('error', '?')[:120]}")

    elif args.input:
        r = process_json_file(args.input, args.output, validate=args.validate)
        print(json.dumps(r, indent=2))

    elif args.input_dir:
        json_files = sorted([f for f in os.listdir(args.input_dir) if f.endswith('.json')])
        if args.limit:
            json_files = json_files[:args.limit]
        print(f"Processing {len(json_files)} files\n")

        t0 = time.time()
        results = []
        for i, jf in enumerate(json_files):
            if (i + 1) % 50 == 0 or i == 0:
                print(f"--- [{i+1}/{len(json_files)}] ---")
            r = process_json_file(
                os.path.join(args.input_dir, jf), args.output,
                validate=args.validate, quiet=(len(json_files) > 20)
            )
            results.append(r)

        elapsed = time.time() - t0
        ok = [r for r in results if r['status'] == 'success']
        err = [r for r in results if r['status'] != 'success']

        print(f"\n{'='*60}")
        print(f"Batch: {len(ok)}/{len(results)} in {elapsed:.1f}s")
        if ok:
            total_files = sum(r.get('step_files', 0) for r in ok)
            total_kb = sum(r.get('total_size_kb', 0) for r in ok)
            total_states = sum(r.get('total_states', 0) for r in ok)
            total_exported = sum(r.get('states_exported', 0) for r in ok)
            total_constraints = sum(r.get('total_constraints', 0) for r in ok)
            print(f"  States: {total_exported}/{total_states} exported")
            print(f"  STEP files: {total_files}")
            print(f"  Size: {total_kb/1024:.1f} MB")
            print(f"  Constraints: {total_constraints}")
        if err:
            err_types = {}
            for r in err:
                msg = r.get('error', 'unknown')[:60]
                err_types[msg] = err_types.get(msg, 0) + 1
            print(f"  Errors ({len(err)}):")
            for msg, ct in sorted(err_types.items(), key=lambda x: -x[1]):
                print(f"    [{ct}x] {msg}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
