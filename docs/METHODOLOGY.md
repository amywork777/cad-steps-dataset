# Methodology

## Problem Statement

Parametric CAD construction is sequential: a model is built through a series of operations (sketch, extrude, boolean) that progressively transform geometry. We formalize this as:

```
S_0 → a_0 → S_1 → a_1 → S_2 → ... → a_{n-1} → S_n
```

Where S_i is the geometry state (B-Rep, represented as a STEP file) and a_i is a parametric operation. Existing datasets provide either {S_n} (final geometry) or {a_0, ..., a_{n-1}} (operation sequences), but never {S_0, S_1, ..., S_n} (intermediate geometry states).

CAD-Steps fills this gap by providing STEP geometry at every construction step.

## Approach 1: Onshape API Extraction (Failed)

### Method
1. Port onshape-cad-parser (github.com/ChrisWu1997/onshape-cad-parser) from Python 2 to Python 3
2. For each model in DeepCAD:
   - Copy the Onshape document (to avoid modifying original)
   - Get the feature list (construction history)
   - For each feature position i:
     - Set the rollback bar to position i
     - Check if geometry exists (some positions are sketch-only with no solid)
     - Create a STEP translation request
     - Poll until translation completes
     - Download the STEP file
   - Reset rollback bar, delete the copy
3. Save metadata (feature types, export status, file sizes)

### API Call Budget Per Model
- 7 fixed overhead calls (get features, copy doc, get elements, etc.)
- ~5 calls per feature state (rollback, get parts, create translation, poll status, download)
- Average model has ~3 exportable feature states
- **Total: ~22 API calls per model**

### Results
- 15-model test batch: 86.7% success rate on pre-filtered DeepCAD models
- Average 23 seconds per successful model
- Average 2.5 exportable states per model

### Why It Failed: Rate Limits
After processing ~15 models (~300 API calls), the Onshape API returned HTTP 429 with:
- `Retry-After: 73808` (20 hours)
- `X-Rate-Limit-Remaining: 0`

Official annual API call limits:

| Plan | Calls/Year | Models/Year | Years for 178K Models |
|------|-----------|-------------|----------------------|
| Free | ~300/day | ~15/day | ~32 years |
| Standard | 2,500 | 113 | 1,576 |
| Professional | 5,000 | 227 | 785 |
| Enterprise | 10,000 | 454 | **392** |

Additionally, Onshape's Terms of Service prohibit data mining public documents.

**Conclusion**: API-based extraction does not scale beyond ~15 models/day on free tier, and is contractually prohibited at any tier.

## Approach 2: Local OpenCascade Reconstruction (Successful)

### Key Insight
DeepCAD already provides pre-parsed construction sequences as JSON files. Each file contains:
- Sketch entities with curve data (Line3D, Circle3D, Arc3D coordinates)
- Extrude parameters (distance, direction, boolean operation type)
- Sketch plane coordinate systems (origin, normal, x_axis, y_axis)
- Construction sequence ordering

We can replay these sequences locally using any CAD kernel that supports B-Rep operations and STEP export.

### Pipeline

```
DeepCAD JSON → Parse → For each step: Build OCC geometry → Export STEP → Save metadata
```

For each model:

1. **Parse**: Load JSON, construct CADSequence object (from DeepCAD's cadlib)
2. **Normalize**: Scale coordinates to standard range
3. **For each operation in sequence**:
   - **If Sketch**: 
     - Build 2D wireframe from curve data (Line, Circle, Arc edges)
     - Transform from local sketch coordinates to global 3D coordinates
     - Export wireframe edges as STEP (2D geometry on sketch plane)
   - **If Extrude**:
     - Build sketch profile face (wires → face)
     - Create solid via BRepPrimAPI_MakePrism (prism extrusion along normal)
     - Handle extent types: OneSide, Symmetric (both directions), TwoSides
     - Apply boolean with accumulated body:
       - NewBody/Join: BRepAlgoAPI_Fuse
       - Cut: BRepAlgoAPI_Cut
       - Intersect: BRepAlgoAPI_Common
     - Export resulting solid as STEP
4. **Save metadata.json** with all operation details and sketch geometry

### Implementation Details

**CAD kernel**: OpenCascade Technology (OCCT) via CadQuery/OCP Python bindings. Specifically, we use OCP (the raw Python wrapper) rather than CadQuery's higher-level API, for maximum control over geometry creation.

**Key OCC classes used**:
- `gp_Pnt, gp_Dir, gp_Vec, gp_Pln, gp_Ax2, gp_Ax3` — geometric primitives
- `BRepBuilderAPI_MakeEdge, MakeWire, MakeFace` — build topology from geometry
- `BRepPrimAPI_MakePrism` — extrude face to solid
- `BRepAlgoAPI_Fuse, Cut, Common` — boolean operations
- `GC_MakeArcOfCircle` — create arc edges
- `STEPControl_Writer` — export to STEP (AP203/AP214)

**Parallelization**: ProcessPoolExecutor (not ThreadPoolExecutor, to avoid GIL contention in OCC). Each worker is fully independent; no shared state.

**Checkpointing**: Before processing a model, check if metadata.json already exists in the output directory. If so, skip. This enables safe resume after crashes.

### Results

200-model validation batch (8 workers):

| Metric | Value |
|--------|-------|
| Models processed | 200 |
| Success rate | 100% |
| STEP files generated | 395 |
| Total output size | 32.8 MB |
| Total processing time | 1.5 seconds |
| Effective time per model | 7.7 ms |

Comparison:

| Metric | Onshape API | Local OCC | Speedup |
|--------|-------------|-----------|---------|
| Time/model | 23,000 ms | 7.7 ms | **885x** |
| API calls/model | 22 | 0 | ∞ |
| Success rate | 86.7% | 100% | +13.3pp |
| Rate limited | Yes (20h lockout) | No | - |
| Internet required | Yes | No | - |
| 178K models | 392 years | ~3 minutes | - |

## Data Format

### Source Data

DeepCAD's JSON format (per model):

```json
{
  "entities": {
    "<sketch_id>": {
      "type": "Sketch",
      "name": "Sketch 1",
      "transform": {"origin": {}, "x_axis": {}, "y_axis": {}, "z_axis": {}},
      "profiles": {
        "<profile_id>": {
          "loops": [
            {
              "is_outer": true,
              "profile_curves": [
                {"type": "Line3D", "start_point": {}, "end_point": {}},
                {"type": "Circle3D", "center_point": {}, "radius": 0.091, "normal": {}},
                {"type": "Arc3D", "start_point": {}, "end_point": {}, "center_point": {}, "radius": 0.025}
              ]
            }
          ]
        }
      }
    },
    "<extrude_id>": {
      "type": "ExtrudeFeature",
      "name": "Extrude 1",
      "operation": "NewBodyFeatureOperation|JoinFeatureOperation|CutFeatureOperation|IntersectFeatureOperation",
      "extent_type": "OneSideFeatureExtentType|SymmetricFeatureExtentType|TwoSidesFeatureExtentType",
      "extent_one": {"distance": {"value": 0.0254}},
      "profiles": [{"profile": "<profile_id>", "sketch": "<sketch_id>"}]
    }
  },
  "sequence": [
    {"index": 0, "type": "Sketch", "entity": "<sketch_id>"},
    {"index": 1, "type": "ExtrudeFeature", "entity": "<extrude_id>"}
  ]
}
```

**Curve types in source data**: Line3D (start + end points), Circle3D (center + radius + normal), Arc3D (start + end + center + radius + angles + reference vector).

### Output Data

Per-model directory with STEP files and metadata:

```
<model_id>/
├── state_0000.step     # First operation state (sketch or extrude)
├── state_0001.step     # Second operation state
├── ...
└── metadata.json       # Operation details and sketch geometry
```

### What DeepCAD Does NOT Provide (Constraints)

DeepCAD's JSON stores **resolved geometry only**, not the original design-intent constraints from Onshape's parametric solver. Missing data:

**Geometric constraints** (not available):
- Concentric (circles share center)
- Parallel, perpendicular, tangent
- Equal-length, symmetric
- Horizontal, vertical
- Coincident, midpoint

**Dimensional constraints** (not available):
- Named distances and angles
- Parametric relationships (e.g., "radius = 2 * other_radius")

**Feature references** (not available):
- Which sketch plane references which face of an existing body
- Feature dependencies in the construction tree

The geometry in the JSON is fully evaluated/resolved: all coordinates are absolute numbers, not expressions of constraints. This means our dataset captures the **geometric trajectory** but not the full **reasoning trajectory** that includes design intent.

We can infer some constraints post-hoc from geometry (e.g., two circles with identical centers are likely concentric), but this is approximate and does not recover the constraint solver's internal state. This is documented as a limitation and future work direction in the paper.
