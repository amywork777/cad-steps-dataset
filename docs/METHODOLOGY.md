# Methodology

## 1. Problem Statement

Given a CAD construction sequence `S = [op₁, op₂, ..., opₙ]` and a geometric kernel, produce intermediate geometry files `[G₁, G₂, ..., Gₙ]` where `Gᵢ` is the cumulative solid geometry after applying operations `op₁` through `opᵢ`.

The dataset consists of tuples `(Gᵢ, opᵢ₊₁, Gᵢ₊₁)` for all valid transitions, enabling supervised learning on geometric state transitions.

---

## 2. Data Source: DeepCAD

### 2.1 Overview

We build on the DeepCAD dataset (Wu et al., ICCV 2021), which contains **178,238 parametric CAD models** with full construction sequences. The models were originally collected from public Onshape documents and pre-filtered to include only sketch-and-extrude operations.

### 2.2 Data Format

Each model is stored as a JSON file with the following structure:

```json
{
  "sequence": [
    {
      "type": "ExtrudeFeature",
      "operation": 0,           // 0=NewBody, 1=Join, 2=Cut, 3=Intersect
      "extent_type": 0,         // 0=OneSide, 1=Symmetric, 2=TwoSides
      "extent_one": 0.209,      // Extrusion distance (normalized)
      "extent_two": 0.0,        // Second distance (for TwoSides)
      "sketch": {
        "profiles": [{
          "loops": [{
            "curves": [
              {"type": "Line", "start": [0.1, 0.2], "end": [0.5, 0.2]},
              {"type": "Arc", "start": [0.5, 0.2], "mid": [0.6, 0.5], "end": [0.5, 0.8]},
              {"type": "Line", "start": [0.5, 0.8], "end": [0.1, 0.8]},
              {"type": "Line", "start": [0.1, 0.8], "end": [0.1, 0.2]}
            ]
          }]
        }],
        "plane": {
          "origin": [0, 0, 0],
          "normal": [0, 0, 1],
          "x_axis": [1, 0, 0]
        }
      }
    }
    // ... more operations
  ]
}
```

### 2.3 DeepCAD's Library (`cadlib`)

We use DeepCAD's own `cadlib` Python package to parse JSON into structured objects:
- `CADSequence`: ordered list of `Extrude` operations
- `Extrude`: sketch profile + extrusion parameters + boolean operation type
- `Profile` → `Loop` → `Curve` (Line, Arc, Circle): 2D sketch geometry
- `CoordSystem`: sketch plane definition (origin, normal, x-axis)
- Normalization: sketch coordinates are normalized to [0, 1]; `denormalize()` restores physical dimensions

### 2.4 Data Organization

DeepCAD distributes its 178K models across 100 bucket directories:
```
data/cad_json/
├── 0000/     # ~1,800 JSON files
├── 0001/     # ~1,800 JSON files
├── ...
└── 0099/     # ~1,800 JSON files
```

Total compressed size: ~185 MB (`cad_json.tar.gz`).

---

## 3. Extraction Pipeline

### 3.1 Approach 1: Onshape API (Proof of Concept)

#### Method

Our initial approach used Onshape's REST API to extract geometry directly from the original CAD documents:

1. **Authenticate** via HMAC-signed API requests
2. **Copy document** to a writable workspace (original docs are read-only)
3. **Get feature list** (construction history)
4. For each feature index `i`:
   - **Set rollback bar** to position `i` (hides all features after `i`)
   - **Check parts** (verify geometry exists at this state)
   - **Create STEP translation** (async export request)
   - **Poll translation status** until complete
   - **Download STEP file**
5. **Reset rollback bar** and **delete copied document**

#### Results

| Metric | Value |
|--------|-------|
| Models tested | 15 (DeepCAD subset) |
| Success rate | 86.7% (13/15) |
| Average time/model | 23 seconds |
| Average states/model | 2.5 |
| API calls/model | ~22 |
| Total STEP files | 21 |
| Total output size | 998 KB |

#### Why It Failed at Scale

After processing just 15 models (~300 API calls), the Onshape free tier returned HTTP 429:
```
HTTP/1.1 429 Too Many Requests
Retry-After: 73808
X-Rate-Limit-Remaining: 0
```

The 73,808-second lockout (~20 hours) made large-scale extraction impossible.

Even the most expensive Enterprise plan (10,000 calls/year) would process only ~454 models/year. At that rate, 178K models would require **392 years**.

Additionally, Onshape's Terms of Service explicitly prohibit data mining of public documents.

**Full rate limit analysis**: see [`ONSHAPE_ANALYSIS.md`](ONSHAPE_ANALYSIS.md).

---

### 3.2 Approach 2: Local OpenCascade Reconstruction

#### Key Insight

DeepCAD already provides the complete parametric data needed to reconstruct every model. Rather than querying Onshape for the geometry, we can replay the construction sequence locally using any B-rep kernel that supports sketch → extrude → boolean operations.

We use **OpenCascade** (via CadQuery's `OCP` Python bindings) — the same open-source B-rep kernel used by FreeCAD, CadQuery, and many commercial CAD systems.

#### Pipeline Architecture

```
DeepCAD JSON → cadlib parser → CADSequence → OCC reconstruction → STEP export
                                    │
                                    ├── For each Extrude operation:
                                    │   1. Build 2D sketch on 3D plane
                                    │   2. Create extruded solid
                                    │   3. Boolean with running body
                                    │   4. Export cumulative geometry
                                    │
                                    └── Save metadata.json
```

#### Step-by-Step Reconstruction

**Step 1: Coordinate Transform (2D → 3D)**

DeepCAD stores sketch curves in a local 2D coordinate system. We transform each point to 3D using the sketch plane:

```python
g_point = point[0] * sketch_plane.x_axis + point[1] * sketch_plane.y_axis + sketch_plane.origin
```

**Step 2: Edge Construction**

Each curve type maps to an OCC edge builder:
- `Line` → `BRepBuilderAPI_MakeEdge(start_pnt, end_pnt)`
- `Circle` → `BRepBuilderAPI_MakeEdge(gp_Circ(center, axis, radius))`
- `Arc` → `GC_MakeArcOfCircle(start, mid, end)` → `BRepBuilderAPI_MakeEdge`

Degenerate edges (zero-length lines) are filtered out.

**Step 3: Wire and Face Construction**

```python
# Build wire from edges
wire = BRepBuilderAPI_MakeWire()
for edge in loop_edges:
    wire.Add(edge)

# Build face from outer wire + inner wires (holes)
face = BRepBuilderAPI_MakeFace(sketch_plane, outer_wire)
for inner_wire in inner_wires:
    face.Add(inner_wire.Reversed())  # Reversed = hole
```

**Step 4: Extrusion**

```python
ext_vec = gp_Vec(normal).Multiplied(extrude_distance)
body = BRepPrimAPI_MakePrism(face, ext_vec).Shape()

# Handle symmetric extrusion
if extent_type == "Symmetric":
    body_sym = BRepPrimAPI_MakePrism(face, ext_vec.Reversed()).Shape()
    body = BRepAlgoAPI_Fuse(body, body_sym).Shape()

# Handle two-sided extrusion
if extent_type == "TwoSides":
    ext_vec2 = gp_Vec(normal.Reversed()).Multiplied(distance_two)
    body_two = BRepPrimAPI_MakePrism(face, ext_vec2).Shape()
    body = BRepAlgoAPI_Fuse(body, body_two).Shape()
```

**Step 5: Boolean Operation**

```python
if operation == "NewBody" or operation == "Join":
    cumulative = BRepAlgoAPI_Fuse(cumulative, new_body).Shape()
elif operation == "Cut":
    cumulative = BRepAlgoAPI_Cut(cumulative, new_body).Shape()
elif operation == "Intersect":
    cumulative = BRepAlgoAPI_Common(cumulative, new_body).Shape()
```

**Step 6: STEP Export**

```python
writer = STEPControl_Writer()
writer.Transfer(cumulative_shape, STEPControl_AsIs)
writer.Write("state_NNNN.step")
```

This export happens after every operation, producing the intermediate state file.

#### Parallelization

We use Python's `ProcessPoolExecutor` for parallel processing:
- Each worker is a separate process (avoids GIL issues with OCC)
- Models are independent; no shared state between workers
- Checkpoint support: existing `metadata.json` files are skipped on restart
- Progress reporting every 50 models with ETA estimation

#### Validation Results (200-Model Batch)

| Metric | Value |
|--------|-------|
| Models processed | 200 |
| Success rate | 100% (200/200) |
| STEP files generated | 395 |
| Total output size | 32.8 MB |
| Wall clock time | 1.5 seconds |
| Workers | 8 |
| Effective time/model | 7.7 ms |

#### Full Dataset Projections

| Workers | Time | Throughput |
|---------|------|------------|
| 1 (sequential) | ~23 min | 129/s |
| 4 | ~6 min | 516/s |
| 8 | **~3 min** | 1,032/s |
| 16 | ~1.5 min | 2,064/s |

Estimated output: **~352,000 STEP files**, **~29 GB** total.

---

## 4. Quality Considerations

### 4.1 Reconstructed vs Original Geometry

The local pipeline reconstructs geometry from DeepCAD's parsed parameters rather than exporting from the original Onshape documents. Key differences:

| Aspect | Onshape (original) | Local (reconstructed) |
|--------|--------------------|-----------------------|
| Kernel | Parasolid | OpenCascade (OCCT) |
| Precision | Onshape's internal | OCC defaults (~1e-6) |
| STEP schema | AP214 | AP214 (OCCT default) |
| Tessellation | Onshape rendering | Not applicable (B-rep only) |
| Parameters | Original | Parsed + normalized |

For the sketch-and-extrude operations in DeepCAD, the geometric results are expected to be nearly identical, as both kernels implement the same fundamental operations (planar face extrusion, boolean operations). Minor differences may arise from:
- Floating-point precision in coordinate transforms
- Edge case handling in boolean operations (e.g., touching faces)
- STEP file formatting and metadata

### 4.2 Known Failure Modes

Some models fail during reconstruction. Common causes:
- **Degenerate sketches**: Profiles with zero-area loops or self-intersecting edges
- **Boolean failures**: Self-intersecting geometry after boolean operations
- **Wire construction errors**: Non-contiguous edges that don't form a closed wire
- **Negative extrusion**: Some models have negative extrusion distances that produce invalid geometry

All failures are logged in `metadata.json` with error messages. Models with partial failures still produce valid STEP files for the successful steps.

### 4.3 Validation Strategy

To validate the local pipeline's output quality:
1. **Cross-reference with Onshape exports**: Compare local STEP files with the 13 models successfully exported via the Onshape API (available when rate limits reset)
2. **Shape validity checking**: Use `BRepCheck_Analyzer` to verify each exported shape
3. **Visual inspection**: Render a random sample of intermediate states to verify geometric correctness
4. **Statistics**: Compare file sizes, face counts, and bounding boxes between approaches

---

## 5. Output Format

### 5.1 Per-Model Directory

Each model produces a directory containing:
- `state_NNNN.step`: STEP geometry file for each successfully exported intermediate state
- `metadata.json`: Full construction trajectory metadata

### 5.2 Metadata Schema

```json
{
  "data_id": "string",            // Model identifier (matches DeepCAD ID)
  "num_operations": "int",        // Total operations in the sequence
  "states": [
    {
      "index": "int",             // Operation index (0-based)
      "operation": "string",      // "NewBodyFeatureOperation" | "JoinFeatureOperation" |
                                  // "CutFeatureOperation" | "IntersectFeatureOperation"
      "extent_type": "string",    // "OneSideFeatureExtentType" | "SymmetricFeatureExtentType" |
                                  // "TwoSidesFeatureExtentType"
      "extent_one": "float",      // Primary extrusion distance
      "exported": "bool",         // Whether STEP file was successfully generated
      "step_file": "string",      // Filename (present if exported=true)
      "size_kb": "float",         // File size in KB (present if exported=true)
      "error": "string",          // Error message (present if exported=false)
      "valid": "bool"             // Shape validity (present if --validate flag used)
    }
  ],
  "total_exported": "int",        // Count of successfully exported states
  "total_operations": "int"       // Same as num_operations
}
```

### 5.3 Batch Results

The batch runner produces `batch_results.json` with aggregate statistics:

```json
{
  "timestamp": "2026-04-14T16:40:41.983149",
  "total": 200,
  "succeeded": 200,
  "failed": 0,
  "total_files": 395,
  "total_size_kb": 32752.2,
  "total_time": 1.54,
  "workers": 8
}
```

---

## 6. Potential Training Approaches

The CAD-Steps dataset enables several learning paradigms:

### 6.1 Next-State Prediction
Given `(Gₙ, opₙ₊₁)`, predict `Gₙ₊₁`. This is the most direct use of the dataset, analogous to next-token prediction in language models but in geometric space.

### 6.2 Inverse Modeling (Operation Prediction)
Given `(Gₙ, Gₙ₊₁)`, predict `opₙ₊₁`. Useful for understanding what operation transforms one shape into another.

### 6.3 Process Reward Modeling
Train a reward model on `(Gₙ, opₙ₊₁, Gₙ₊₁)` triples to score whether each step is "correct" (valid geometry, reasonable operation). Analogous to PRM800K for math.

### 6.4 Trajectory-Level Generation
Generate complete construction sequences by autoregressively predicting `(op₁, G₁, op₂, G₂, ...)`. Can condition on target geometry for reconstruction, or generate unconditionally for novel design.

### 6.5 Diffusion Over Trajectories
Apply diffusion models to the full trajectory representation, denoising from random geometry sequences to valid construction trajectories.

### 6.6 Retrieval-Augmented CAD
Use intermediate states as a retrieval index. Given a partially constructed model, find similar intermediate states in the dataset and suggest next operations based on how those models were completed.
