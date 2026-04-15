#!/usr/bin/env python3
"""
CAD-Steps v2: Local STEP export with sketch states and geometric constraints.

Changes from v1:
- Exports sketch-only states as 2D wireframe STEP files (not just solid extrusions)
- Infers geometric constraints from curve geometry (concentric, equal-length, parallel, etc.)
- Rich metadata with sketch entities, constraints, and feature tree

Output per model:
    model_XXXXXXXX/
      state_0001.step  (sketch wireframe)
      state_0002.step  (solid after extrude)
      state_0003.step  (sketch on existing solid)
      state_0004.step  (solid after cut)
      metadata.json    (full feature tree with constraints)

Usage:
    python3 local_export_v2.py --input ../data/deepcad_raw/data/cad_json/0000/00000007.json --output /tmp/test
    python3 local_export_v2.py --test
"""

import os
import sys
import json
import time
import argparse
import numpy as np
from copy import copy
from itertools import combinations

# OCP imports
from OCP.gp import gp_Pnt, gp_Dir, gp_Circ, gp_Pln, gp_Vec, gp_Ax3, gp_Ax2
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
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


# ---- Tolerances for constraint detection ----
CONSTRAINT_TOL = 1e-4      # tolerance for equality checks
ANGLE_TOL = 1e-3           # tolerance for angle checks (radians)
PARALLEL_TOL = 1e-3        # tolerance for parallelism


# ---- Geometry helpers ----

def point_local2global(point, sketch_plane, to_gp_Pnt=True):
    """Convert point in sketch plane local coordinates to global coordinates."""
    g_point = point[0] * sketch_plane.x_axis + point[1] * sketch_plane.y_axis + sketch_plane.origin
    if to_gp_Pnt:
        return gp_Pnt(float(g_point[0]), float(g_point[1]), float(g_point[2]))
    return g_point


def point_local2global_array(point, sketch_plane):
    """Convert point to global coords, returning numpy array."""
    return point[0] * sketch_plane.x_axis + point[1] * sketch_plane.y_axis + sketch_plane.origin


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


def create_sketch_wireframe(extrude_op, existing_body=None):
    """
    Create a compound shape containing sketch wireframe geometry.
    If existing_body is provided, combine them (sketch drawn on existing solid).
    """
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)
    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)

    # Add existing solid if present
    if existing_body is not None:
        builder.Add(compound, existing_body)

    # Add sketch wireframe
    for loop in profile.children:
        try:
            wire = create_loop_3d(loop, sketch_plane)
            builder.Add(compound, wire)
        except Exception:
            # If full wire fails, add edges individually
            for curve in loop.children:
                try:
                    edge = create_edge_3d(curve, sketch_plane)
                    if edge is not None:
                        builder.Add(compound, edge)
                except Exception:
                    continue

    return compound


def write_step(shape, filepath):
    """Export an OCC shape to a STEP file."""
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(filepath)
    return str(status).endswith("Done") or status == 1


# ---- Sketch entity extraction ----

def extract_curve_entity(curve, curve_idx, sketch_plane):
    """Extract a curve entity description from a cadlib curve object."""
    entity = {"id": f"curve_{curve_idx}"}

    if isinstance(curve, Line):
        sp_global = point_local2global_array(curve.start_point, sketch_plane)
        ep_global = point_local2global_array(curve.end_point, sketch_plane)
        length = float(np.linalg.norm(ep_global - sp_global))
        direction = (ep_global - sp_global)
        if length > 0:
            direction = direction / length
        entity.update({
            "type": "line",
            "start": curve.start_point.tolist(),
            "end": curve.end_point.tolist(),
            "start_global": sp_global.tolist(),
            "end_global": ep_global.tolist(),
            "length": round(length, 8),
            "direction": direction.tolist(),
        })
    elif isinstance(curve, Circle):
        center_global = point_local2global_array(curve.center, sketch_plane)
        entity.update({
            "type": "circle",
            "center": curve.center.tolist(),
            "center_global": center_global.tolist(),
            "radius": round(float(curve.radius), 8),
        })
    elif isinstance(curve, Arc):
        sp_global = point_local2global_array(curve.start_point, sketch_plane)
        mp_global = point_local2global_array(curve.mid_point, sketch_plane)
        ep_global = point_local2global_array(curve.end_point, sketch_plane)
        center_global = point_local2global_array(curve.center, sketch_plane)
        entity.update({
            "type": "arc",
            "start": curve.start_point.tolist(),
            "mid": curve.mid_point.tolist(),
            "end": curve.end_point.tolist(),
            "center": curve.center.tolist(),
            "start_global": sp_global.tolist(),
            "mid_global": mp_global.tolist(),
            "end_global": ep_global.tolist(),
            "center_global": center_global.tolist(),
            "radius": round(float(curve.radius), 8),
        })

    return entity


def extract_sketch_entities(extrude_op):
    """Extract all sketch entities from an extrude operation."""
    profile = copy(extrude_op.profile)
    profile.denormalize(extrude_op.sketch_size)
    sketch_plane = copy(extrude_op.sketch_plane)
    sketch_plane.origin = extrude_op.sketch_pos

    entities = []
    loops_info = []
    curve_idx = 0

    for loop_idx, loop in enumerate(profile.children):
        loop_entity_ids = []
        for curve in loop.children:
            entity = extract_curve_entity(curve, curve_idx, sketch_plane)
            entities.append(entity)
            loop_entity_ids.append(entity["id"])
            curve_idx += 1
        loops_info.append({
            "loop_index": loop_idx,
            "is_outer": loop_idx == 0,  # first loop is outer in DeepCAD convention
            "curve_ids": loop_entity_ids,
        })

    return entities, loops_info, sketch_plane


# ---- Geometric constraint inference ----

def infer_constraints(entities):
    """
    Infer geometric constraints from sketch entities.
    Since DeepCAD doesn't store explicit constraints, we detect them
    from the geometry itself.
    """
    constraints = []
    constraint_id = 0

    lines = [(i, e) for i, e in enumerate(entities) if e["type"] == "line"]
    circles = [(i, e) for i, e in enumerate(entities) if e["type"] == "circle"]
    arcs = [(i, e) for i, e in enumerate(entities) if e["type"] == "arc"]
    all_circular = circles + arcs  # both have center+radius

    # 1. Coincident: endpoints that touch
    for (i, e1), (j, e2) in combinations(enumerate(entities), 2):
        pts1 = _get_endpoints(e1)
        pts2 = _get_endpoints(e2)
        for p1_name, p1 in pts1:
            for p2_name, p2 in pts2:
                if np.linalg.norm(np.array(p1) - np.array(p2)) < CONSTRAINT_TOL:
                    constraints.append({
                        "id": f"c_{constraint_id}",
                        "type": "coincident",
                        "entities": [e1["id"], e2["id"]],
                        "points": [p1_name, p2_name],
                    })
                    constraint_id += 1

    # 2. Concentric: circles/arcs sharing the same center
    for (i, e1), (j, e2) in combinations(all_circular, 2):
        c1 = np.array(e1["center"])
        c2 = np.array(e2["center"])
        if np.linalg.norm(c1 - c2) < CONSTRAINT_TOL:
            constraints.append({
                "id": f"c_{constraint_id}",
                "type": "concentric",
                "entities": [e1["id"], e2["id"]],
            })
            constraint_id += 1

    # 3. Equal radius: circles/arcs with the same radius
    for (i, e1), (j, e2) in combinations(all_circular, 2):
        if abs(e1["radius"] - e2["radius"]) < CONSTRAINT_TOL:
            constraints.append({
                "id": f"c_{constraint_id}",
                "type": "equal_radius",
                "entities": [e1["id"], e2["id"]],
                "value": round(e1["radius"], 8),
            })
            constraint_id += 1

    # 4. Equal length: lines with the same length
    for (i, e1), (j, e2) in combinations(lines, 2):
        if abs(e1["length"] - e2["length"]) < CONSTRAINT_TOL:
            constraints.append({
                "id": f"c_{constraint_id}",
                "type": "equal_length",
                "entities": [e1["id"], e2["id"]],
                "value": round(e1["length"], 8),
            })
            constraint_id += 1

    # 5. Parallel lines
    for (i, e1), (j, e2) in combinations(lines, 2):
        if e1["length"] < CONSTRAINT_TOL or e2["length"] < CONSTRAINT_TOL:
            continue
        d1 = np.array(e1["direction"])
        d2 = np.array(e2["direction"])
        cross = np.abs(np.cross(d1, d2)) if len(d1) == 2 else np.linalg.norm(np.cross(d1, d2))
        if cross < PARALLEL_TOL:
            constraints.append({
                "id": f"c_{constraint_id}",
                "type": "parallel",
                "entities": [e1["id"], e2["id"]],
            })
            constraint_id += 1

    # 6. Perpendicular lines
    for (i, e1), (j, e2) in combinations(lines, 2):
        if e1["length"] < CONSTRAINT_TOL or e2["length"] < CONSTRAINT_TOL:
            continue
        d1 = np.array(e1["direction"])
        d2 = np.array(e2["direction"])
        dot = abs(np.dot(d1, d2))
        if dot < ANGLE_TOL:
            constraints.append({
                "id": f"c_{constraint_id}",
                "type": "perpendicular",
                "entities": [e1["id"], e2["id"]],
            })
            constraint_id += 1

    # 7. Horizontal/Vertical lines (in sketch-local 2D coords)
    for (i, e) in lines:
        if e["length"] < CONSTRAINT_TOL:
            continue
        dx = abs(e["end"][0] - e["start"][0])
        dy = abs(e["end"][1] - e["start"][1])
        if dy < CONSTRAINT_TOL and dx > CONSTRAINT_TOL:
            constraints.append({
                "id": f"c_{constraint_id}",
                "type": "horizontal",
                "entities": [e["id"]],
            })
            constraint_id += 1
        elif dx < CONSTRAINT_TOL and dy > CONSTRAINT_TOL:
            constraints.append({
                "id": f"c_{constraint_id}",
                "type": "vertical",
                "entities": [e["id"]],
            })
            constraint_id += 1

    # 8. Tangent: line endpoint touches circle/arc and is perpendicular to radius at that point
    for (li, le) in lines:
        for (ci, ce) in all_circular:
            center = np.array(ce["center"])
            radius = ce["radius"]
            for pt_name in ["start", "end"]:
                pt = np.array(le[pt_name])
                dist_to_center = np.linalg.norm(pt - center)
                if abs(dist_to_center - radius) < CONSTRAINT_TOL:
                    # point is on circle; check if line is tangent
                    radial = pt - center
                    line_dir = np.array(le["end"]) - np.array(le["start"])
                    if np.linalg.norm(line_dir) > 0 and np.linalg.norm(radial) > 0:
                        dot = abs(np.dot(radial / np.linalg.norm(radial),
                                        line_dir / np.linalg.norm(line_dir)))
                        if dot < ANGLE_TOL:
                            constraints.append({
                                "id": f"c_{constraint_id}",
                                "type": "tangent",
                                "entities": [le["id"], ce["id"]],
                            })
                            constraint_id += 1

    # 9. Symmetric pairs of lines (about an axis, detected by midpoint alignment)
    for (i, e1), (j, e2) in combinations(lines, 2):
        if abs(e1["length"] - e2["length"]) < CONSTRAINT_TOL and e1["length"] > CONSTRAINT_TOL:
            mid1 = (np.array(e1["start"]) + np.array(e1["end"])) / 2
            mid2 = (np.array(e2["start"]) + np.array(e2["end"])) / 2
            # Check if midpoints are symmetric about x or y axis
            if abs(mid1[0] + mid2[0]) < CONSTRAINT_TOL and abs(mid1[1] - mid2[1]) < CONSTRAINT_TOL:
                constraints.append({
                    "id": f"c_{constraint_id}",
                    "type": "symmetric_y",
                    "entities": [e1["id"], e2["id"]],
                })
                constraint_id += 1
            elif abs(mid1[1] + mid2[1]) < CONSTRAINT_TOL and abs(mid1[0] - mid2[0]) < CONSTRAINT_TOL:
                constraints.append({
                    "id": f"c_{constraint_id}",
                    "type": "symmetric_x",
                    "entities": [e1["id"], e2["id"]],
                })
                constraint_id += 1

    return constraints


def _get_endpoints(entity):
    """Get named endpoints from an entity."""
    pts = []
    if entity["type"] == "line":
        pts.append(("start", entity["start"]))
        pts.append(("end", entity["end"]))
    elif entity["type"] == "arc":
        pts.append(("start", entity["start"]))
        pts.append(("end", entity["end"]))
    elif entity["type"] == "circle":
        # circles don't have explicit endpoints
        pass
    return pts


# ---- Core: export all intermediate states ----

def export_all_states(raw_data, output_dir, data_id=None):
    """
    Parse raw DeepCAD JSON and export ALL intermediate states:
    - Sketch states (2D wireframe STEP)
    - Extrude states (3D solid STEP)

    Returns metadata dict.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Parse the full sequence from raw JSON
    sequence = raw_data.get("sequence", [])
    entities_map = raw_data.get("entities", {})

    # Build CADSequence for geometry
    cad_seq = CADSequence.from_dict(raw_data)
    cad_seq.normalize()

    metadata = {
        "model_id": data_id,
        "num_sequence_items": len(sequence),
        "num_extrude_ops": len(cad_seq.seq),
        "states": [],
    }

    body = None
    state_idx = 0
    extrude_idx = 0  # index into cad_seq.seq
    exported_count = 0
    sketch_count = 0
    extrude_count = 0

    for seq_item in sequence:
        item_type = seq_item["type"]
        entity_id = seq_item["entity"]
        entity_data = entities_map.get(entity_id, {})

        if item_type == "Sketch":
            # This is a sketch state - export 2D wireframe
            state_idx += 1
            sketch_count += 1

            # Find the extrude op that uses this sketch to get the parsed profile
            # The extrude always follows its sketch in the sequence
            if extrude_idx < len(cad_seq.seq):
                ext_op = cad_seq.seq[extrude_idx]

                # Extract entities and constraints
                sketch_entities, loops_info, sketch_plane = extract_sketch_entities(ext_op)
                constraints = infer_constraints(sketch_entities)

                state = {
                    "index": state_idx,
                    "type": "sketch",
                    "sketch_name": entity_data.get("name", f"Sketch {sketch_count}"),
                    "sketch_plane": {
                        "origin": ext_op.sketch_pos.tolist() if hasattr(ext_op.sketch_pos, 'tolist') else list(ext_op.sketch_pos),
                        "normal": ext_op.sketch_plane.normal.tolist(),
                        "x_axis": ext_op.sketch_plane.x_axis.tolist(),
                    },
                    "entities": sketch_entities,
                    "loops": loops_info,
                    "constraints": constraints,
                    "num_entities": len(sketch_entities),
                    "num_constraints": len(constraints),
                }

                # Export sketch wireframe STEP
                try:
                    sketch_shape = create_sketch_wireframe(ext_op, existing_body=body)
                    step_path = os.path.join(output_dir, f"state_{state_idx:04d}.step")
                    success = write_step(sketch_shape, step_path)
                    if success and os.path.exists(step_path):
                        state["geometry_file"] = f"state_{state_idx:04d}.step"
                        state["size_kb"] = round(os.path.getsize(step_path) / 1024, 1)
                        state["exported"] = True
                        exported_count += 1
                    else:
                        state["exported"] = False
                        state["error"] = "write_step failed"
                except Exception as e:
                    state["exported"] = False
                    state["error"] = str(e)[:200]

            else:
                # Orphan sketch with no extrude - rare edge case
                state = {
                    "index": state_idx,
                    "type": "sketch",
                    "sketch_name": entity_data.get("name", f"Sketch {sketch_count}"),
                    "exported": False,
                    "error": "no_matching_extrude",
                }

            metadata["states"].append(state)

        elif item_type == "ExtrudeFeature":
            # This is an extrude state - export 3D solid
            if extrude_idx >= len(cad_seq.seq):
                continue

            # May need to process multiple extrude ops for multi-profile extrusions
            # DeepCAD decomposes multi-profile extrudes into separate Extrude objects
            ext_entity = entities_map.get(entity_id, {})
            n_profiles = len(ext_entity.get("profiles", []))

            for profile_i in range(n_profiles):
                if extrude_idx >= len(cad_seq.seq):
                    break

                ext_op = cad_seq.seq[extrude_idx]
                state_idx += 1
                extrude_count += 1

                op_name = EXTRUDE_OPERATIONS[ext_op.operation]
                ext_type_name = EXTENT_TYPE[ext_op.extent_type]

                state = {
                    "index": state_idx,
                    "type": "extrude",
                    "extrude_name": ext_entity.get("name", f"Extrude {extrude_count}"),
                    "operation": {
                        "type": op_name,
                        "extent_type": ext_type_name,
                        "extent_one": round(float(ext_op.extent_one), 8),
                        "extent_two": round(float(ext_op.extent_two), 8) if hasattr(ext_op, 'extent_two') else 0.0,
                        "sketch_ref": state_idx - 1,  # previous state was the sketch
                        "direction": ext_op.sketch_plane.normal.tolist(),
                    },
                }

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

                    step_path = os.path.join(output_dir, f"state_{state_idx:04d}.step")
                    success = write_step(body, step_path)
                    if success and os.path.exists(step_path):
                        state["geometry_file"] = f"state_{state_idx:04d}.step"
                        state["size_kb"] = round(os.path.getsize(step_path) / 1024, 1)
                        state["exported"] = True
                        exported_count += 1
                    else:
                        state["exported"] = False
                        state["error"] = "write_step failed"

                except Exception as e:
                    state["exported"] = False
                    state["error"] = str(e)[:200]

                metadata["states"].append(state)
                extrude_idx += 1

    metadata["total_states"] = state_idx
    metadata["total_exported"] = exported_count
    metadata["sketch_states"] = sketch_count
    metadata["extrude_states"] = extrude_count

    # Constraint summary
    all_constraints = []
    for s in metadata["states"]:
        if s.get("type") == "sketch" and "constraints" in s:
            all_constraints.extend(s["constraints"])
    
    constraint_types = {}
    for c in all_constraints:
        ct = c["type"]
        constraint_types[ct] = constraint_types.get(ct, 0) + 1
    metadata["constraint_summary"] = constraint_types
    metadata["total_constraints"] = len(all_constraints)

    # Save metadata
    meta_path = os.path.join(output_dir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


# ---- Single file processing ----

def process_json_file(json_path, output_dir, quiet=False):
    """Process a single DeepCAD JSON file."""
    data_id = os.path.splitext(os.path.basename(json_path))[0]
    start_time = time.time()

    result = {
        "data_id": data_id,
        "json_path": json_path,
        "status": "unknown",
    }

    try:
        with open(json_path) as f:
            raw_data = json.load(f)

        model_dir = os.path.join(output_dir, data_id)
        metadata = export_all_states(raw_data, model_dir, data_id=data_id)

        result["status"] = "success"
        result["total_states"] = metadata["total_states"]
        result["total_exported"] = metadata["total_exported"]
        result["sketch_states"] = metadata["sketch_states"]
        result["extrude_states"] = metadata["extrude_states"]
        result["total_constraints"] = metadata["total_constraints"]

        # Total size
        if os.path.exists(model_dir):
            step_files = [f for f in os.listdir(model_dir) if f.endswith(".step")]
            total_size = sum(os.path.getsize(os.path.join(model_dir, f)) for f in step_files)
            result["step_files"] = len(step_files)
            result["total_size_kb"] = round(total_size / 1024, 1)

        if not quiet:
            print(f"  {data_id}: {metadata['total_states']} states "
                  f"({metadata['sketch_states']} sketch, {metadata['extrude_states']} extrude), "
                  f"{metadata['total_exported']} exported, "
                  f"{metadata['total_constraints']} constraints, "
                  f"{result.get('total_size_kb', 0):.1f} KB")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        if not quiet:
            print(f"  {data_id}: ERROR - {e}")

    result["time_seconds"] = round(time.time() - start_time, 3)
    return result


# ---- Test / CLI ----

def main():
    parser = argparse.ArgumentParser(description="CAD-Steps v2: STEP export with sketches & constraints")
    parser.add_argument("--input", type=str, help="Path to single JSON file")
    parser.add_argument("--input-dir", type=str, help="Path to directory of JSON files")
    parser.add_argument("--output", type=str, default="/tmp/cad_steps_v2", help="Output directory")
    parser.add_argument("--test", action="store_true", help="Test with a few examples")
    parser.add_argument("--limit", type=int, default=None, help="Max files to process")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if args.test:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "deepcad_raw", "data", "cad_json", "0000")
        if not os.path.exists(data_dir):
            print(f"Data not found at {data_dir}")
            return

        json_files = sorted([f for f in os.listdir(data_dir) if f.endswith(".json")])[:10]
        print(f"Testing with {len(json_files)} models from {data_dir}\n")

        total_start = time.time()
        results = []

        for jf in json_files:
            json_path = os.path.join(data_dir, jf)
            result = process_json_file(json_path, args.output)
            results.append(result)

        total_time = time.time() - total_start
        succeeded = [r for r in results if r["status"] == "success"]
        failed = [r for r in results if r["status"] != "success"]

        print(f"\n{'='*70}")
        print(f"Test complete: {len(succeeded)}/{len(results)} succeeded in {total_time:.2f}s")
        if succeeded:
            total_files = sum(r.get("step_files", 0) for r in succeeded)
            total_size = sum(r.get("total_size_kb", 0) for r in succeeded)
            total_states = sum(r.get("total_states", 0) for r in succeeded)
            total_sketches = sum(r.get("sketch_states", 0) for r in succeeded)
            total_extrudes = sum(r.get("extrude_states", 0) for r in succeeded)
            total_constraints = sum(r.get("total_constraints", 0) for r in succeeded)

            print(f"  Total states: {total_states} ({total_sketches} sketch + {total_extrudes} extrude)")
            print(f"  Total STEP files: {total_files}")
            print(f"  Total constraints: {total_constraints}")
            print(f"  Total size: {total_size:.1f} KB")
            print(f"  Avg time/model: {total_time/len(succeeded)*1000:.0f}ms")

        if failed:
            print(f"\n  Failures:")
            for r in failed:
                print(f"    {r['data_id']}: {r.get('error', 'unknown')}")

    elif args.input:
        result = process_json_file(args.input, args.output)
        print(json.dumps(result, indent=2))

    elif args.input_dir:
        json_files = sorted([f for f in os.listdir(args.input_dir) if f.endswith(".json")])
        if args.limit:
            json_files = json_files[:args.limit]

        print(f"Processing {len(json_files)} files from {args.input_dir}")
        total_start = time.time()
        results = []

        for i, jf in enumerate(json_files):
            json_path = os.path.join(args.input_dir, jf)
            result = process_json_file(json_path, args.output, quiet=(i % 50 != 0))
            results.append(result)

        total_time = time.time() - total_start
        succeeded = [r for r in results if r["status"] == "success"]
        print(f"\n{'='*70}")
        print(f"Batch: {len(succeeded)}/{len(results)} in {total_time:.1f}s")
        if succeeded:
            total_files = sum(r.get("step_files", 0) for r in succeeded)
            total_constraints = sum(r.get("total_constraints", 0) for r in succeeded)
            print(f"  STEP files: {total_files}, Constraints: {total_constraints}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
