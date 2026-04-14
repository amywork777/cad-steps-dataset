#!/usr/bin/env python3
"""
Local STEP export from DeepCAD JSON data.

Replays CAD construction sequences from DeepCAD JSON files using
OpenCascade (via CadQuery's OCP bindings) and exports STEP geometry
at each intermediate step.

NO Onshape API required - everything runs locally.

Based on DeepCAD's cadlib/visualize.py, adapted for OCP (CadQuery)
instead of pythonocc (OCC.Core).

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
from OCP.gp import gp_Pnt, gp_Dir, gp_Circ, gp_Pln, gp_Vec, gp_Ax3, gp_Ax2, gp_Lin
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
from OCP.GC import GC_MakeArcOfCircle
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.BRepCheck import BRepCheck_Analyzer

# Add cadlib to path
sys.path.insert(0, os.path.dirname(__file__))
from cadlib.extrude import CADSequence, Extrude, CoordSystem, EXTRUDE_OPERATIONS, EXTENT_TYPE
from cadlib.sketch import Profile, Loop
from cadlib.curves import Line, Circle, Arc, CurveBase


# ---- Geometry creation (adapted from DeepCAD cadlib/visualize.py) ----

def point_local2global(point, sketch_plane, to_gp_Pnt=True):
    """Convert point in sketch plane local coordinates to global coordinates."""
    g_point = point[0] * sketch_plane.x_axis + point[1] * sketch_plane.y_axis + sketch_plane.origin
    if to_gp_Pnt:
        return gp_Pnt(float(g_point[0]), float(g_point[1]), float(g_point[2]))
    return g_point


def create_edge_3d(curve, sketch_plane):
    """Create a 3D edge from a curve."""
    if isinstance(curve, Line):
        if np.allclose(curve.start_point, curve.end_point):
            return None
        start_point = point_local2global(curve.start_point, sketch_plane)
        end_point = point_local2global(curve.end_point, sketch_plane)
        topo_edge = BRepBuilderAPI_MakeEdge(start_point, end_point)
    elif isinstance(curve, Circle):
        center = point_local2global(curve.center, sketch_plane)
        axis = gp_Dir(float(sketch_plane.normal[0]), float(sketch_plane.normal[1]), float(sketch_plane.normal[2]))
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
    """Create a 3D sketch loop (wire)."""
    topo_wire = BRepBuilderAPI_MakeWire()
    for curve in loop.children:
        topo_edge = create_edge_3d(curve, sketch_plane)
        if topo_edge is None:
            continue
        topo_wire.Add(topo_edge)
    return topo_wire.Wire()


def create_profile_face(profile, sketch_plane):
    """Create a face from a sketch profile and the sketch plane."""
    origin = gp_Pnt(float(sketch_plane.origin[0]), float(sketch_plane.origin[1]), float(sketch_plane.origin[2]))
    normal = gp_Dir(float(sketch_plane.normal[0]), float(sketch_plane.normal[1]), float(sketch_plane.normal[2]))
    x_axis = gp_Dir(float(sketch_plane.x_axis[0]), float(sketch_plane.x_axis[1]), float(sketch_plane.x_axis[2]))
    gp_face = gp_Pln(gp_Ax3(origin, normal, x_axis))

    all_loops = [create_loop_3d(loop, sketch_plane) for loop in profile.children]
    topo_face = BRepBuilderAPI_MakeFace(gp_face, all_loops[0])
    for loop in all_loops[1:]:
        topo_face.Add(loop.Reversed())
    return topo_face.Face()


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
    return status == 1  # 1 = success in OCC


# ---- Core: export intermediate states ----

def export_intermediate_steps(cad_seq, output_dir, data_id=None, validate=False):
    """
    Replay a CAD construction sequence and export STEP at each step.
    
    This is the key function for the CAD-Steps dataset.
    Instead of building the full model and only exporting the final result,
    we export geometry after each extrude operation.
    
    Args:
        cad_seq: CADSequence object from DeepCAD
        output_dir: Directory to save STEP files and metadata
        data_id: Optional model identifier for logging
        validate: If True, check shapes with BRepCheck_Analyzer
        
    Returns:
        dict with export results and metadata
    """
    os.makedirs(output_dir, exist_ok=True)
    
    prefix = data_id or "model"
    n_ops = len(cad_seq.seq)
    
    metadata = {
        'data_id': data_id,
        'num_operations': n_ops,
        'states': [],
    }
    
    body = None
    exported = 0
    
    for i, extrude_op in enumerate(cad_seq.seq):
        state = {
            'index': i,
            'operation': EXTRUDE_OPERATIONS[extrude_op.operation],
            'extent_type': EXTENT_TYPE[extrude_op.extent_type],
            'extent_one': float(extrude_op.extent_one),
        }
        
        try:
            new_body = create_by_extrude(extrude_op)
            
            if body is None:
                body = new_body
            else:
                op = extrude_op.operation
                if op == EXTRUDE_OPERATIONS.index("NewBodyFeatureOperation") or \
                   op == EXTRUDE_OPERATIONS.index("JoinFeatureOperation"):
                    body = BRepAlgoAPI_Fuse(body, new_body).Shape()
                elif op == EXTRUDE_OPERATIONS.index("CutFeatureOperation"):
                    body = BRepAlgoAPI_Cut(body, new_body).Shape()
                elif op == EXTRUDE_OPERATIONS.index("IntersectFeatureOperation"):
                    body = BRepAlgoAPI_Common(body, new_body).Shape()
            
            # Validate if requested
            if validate:
                analyzer = BRepCheck_Analyzer(body)
                state['valid'] = analyzer.IsValid()
            
            # Export STEP
            step_path = os.path.join(output_dir, f"state_{i:04d}.step")
            success = write_step(body, step_path)
            
            if success and os.path.exists(step_path):
                size_kb = os.path.getsize(step_path) / 1024
                state['exported'] = True
                state['step_file'] = f"state_{i:04d}.step"
                state['size_kb'] = round(size_kb, 1)
                exported += 1
            else:
                state['exported'] = False
                state['error'] = 'write_step failed'
                
        except Exception as e:
            state['exported'] = False
            state['error'] = str(e)[:200]
    
        metadata['states'].append(state)
    
    metadata['total_exported'] = exported
    metadata['total_operations'] = n_ops
    
    # Save metadata
    meta_path = os.path.join(output_dir, 'metadata.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return metadata


# ---- Batch processing ----

def process_json_file(json_path, output_dir, validate=False, quiet=False):
    """
    Process a single DeepCAD JSON file and export intermediate STEP states.
    
    Args:
        json_path: Path to DeepCAD JSON file
        output_dir: Directory to save output
        validate: Validate shapes with BRepCheck_Analyzer
        quiet: Suppress output
        
    Returns:
        dict with processing results
    """
    data_id = os.path.splitext(os.path.basename(json_path))[0]
    start_time = time.time()
    
    result = {
        'data_id': data_id,
        'json_path': json_path,
        'status': 'unknown',
    }
    
    try:
        with open(json_path) as f:
            data = json.load(f)
        
        cad_seq = CADSequence.from_dict(data)
        cad_seq.normalize()
        
        if not quiet:
            print(f"  Model {data_id}: {len(cad_seq.seq)} extrude operations")
        
        model_dir = os.path.join(output_dir, data_id)
        metadata = export_intermediate_steps(
            cad_seq, model_dir, 
            data_id=data_id, 
            validate=validate
        )
        
        result['status'] = 'success'
        result['num_operations'] = len(cad_seq.seq)
        result['states_exported'] = metadata['total_exported']
        result['step_files'] = metadata['total_exported']
        
        # Calculate total size
        if os.path.exists(model_dir):
            step_files = [f for f in os.listdir(model_dir) if f.endswith('.step')]
            total_size = sum(os.path.getsize(os.path.join(model_dir, f)) for f in step_files)
            result['total_size_kb'] = round(total_size / 1024, 1)
        
        if not quiet:
            print(f"    ✓ Exported {metadata['total_exported']}/{len(cad_seq.seq)} states "
                  f"({result.get('total_size_kb', 0):.1f} KB)")
        
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:200]
        if not quiet:
            print(f"    ✗ Error: {e}")
    
    result['time_seconds'] = round(time.time() - start_time, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description='Local STEP export from DeepCAD JSON')
    parser.add_argument('--input', type=str, help='Path to single JSON file')
    parser.add_argument('--input-dir', type=str, help='Path to directory of JSON files')
    parser.add_argument('--output', type=str, default='/tmp/cad_steps_local',
                       help='Output directory')
    parser.add_argument('--test', action='store_true', help='Test with a few examples')
    parser.add_argument('--limit', type=int, default=None, help='Max files to process')
    parser.add_argument('--validate', action='store_true', help='Validate shapes')
    args = parser.parse_args()
    
    os.makedirs(args.output, exist_ok=True)
    
    if args.test:
        # Test with a few models from the dataset
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'deepcad_raw', 'data', 'cad_json', '0000')
        if not os.path.exists(data_dir):
            print(f"Data not found at {data_dir}")
            print("Download: curl -L http://www.cs.columbia.edu/cg/deepcad/data.tar | tar x")
            return
        
        json_files = sorted([f for f in os.listdir(data_dir) if f.endswith('.json')])[:5]
        print(f"Testing with {len(json_files)} models from {data_dir}")
        
        total_start = time.time()
        results = []
        
        for jf in json_files:
            json_path = os.path.join(data_dir, jf)
            result = process_json_file(json_path, args.output, validate=args.validate)
            results.append(result)
        
        total_time = time.time() - total_start
        succeeded = [r for r in results if r['status'] == 'success']
        
        print(f"\n{'='*60}")
        print(f"Test complete: {len(succeeded)}/{len(results)} succeeded in {total_time:.1f}s")
        if succeeded:
            total_files = sum(r.get('step_files', 0) for r in succeeded)
            total_size = sum(r.get('total_size_kb', 0) for r in succeeded)
            avg_time = sum(r['time_seconds'] for r in succeeded) / len(succeeded)
            print(f"  Total STEP files: {total_files}")
            print(f"  Total size: {total_size:.1f} KB")
            print(f"  Avg time/model: {avg_time:.2f}s")
            
            # Full dataset projection
            total_models = 178238
            est_time_h = (avg_time * total_models) / 3600
            est_size_gb = (total_size / len(succeeded)) * total_models / 1024 / 1024
            print(f"\n  --- Full Dataset Projection (178k models) ---")
            print(f"  Sequential: ~{est_time_h:.0f}h ({est_time_h/24:.0f} days)")
            print(f"  10 workers: ~{est_time_h/10:.0f}h ({est_time_h/10/24:.1f} days)")
            print(f"  Est. size: ~{est_size_gb:.1f} GB")
    
    elif args.input:
        result = process_json_file(args.input, args.output, validate=args.validate)
        print(json.dumps(result, indent=2))
    
    elif args.input_dir:
        json_files = sorted([f for f in os.listdir(args.input_dir) if f.endswith('.json')])
        if args.limit:
            json_files = json_files[:args.limit]
        
        print(f"Processing {len(json_files)} files from {args.input_dir}")
        
        total_start = time.time()
        results = []
        
        for i, jf in enumerate(json_files):
            print(f"[{i+1}/{len(json_files)}]", end=" ")
            json_path = os.path.join(args.input_dir, jf)
            result = process_json_file(json_path, args.output, validate=args.validate)
            results.append(result)
        
        total_time = time.time() - total_start
        succeeded = [r for r in results if r['status'] == 'success']
        errors = [r for r in results if r['status'] != 'success']
        
        print(f"\n{'='*60}")
        print(f"Batch complete: {len(succeeded)}/{len(results)} in {total_time:.1f}s")
        print(f"  Errors: {len(errors)}")
        if succeeded:
            total_files = sum(r.get('step_files', 0) for r in succeeded)
            total_size = sum(r.get('total_size_kb', 0) for r in succeeded)
            print(f"  STEP files: {total_files}")
            print(f"  Total size: {total_size:.1f} KB")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
