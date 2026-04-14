# CAD-Steps: Intermediate Geometry States for Parametric CAD Construction

**The first large-scale dataset of intermediate CAD geometry at every construction step.**

CAD-Steps provides STEP geometry files at each stage of a parametric CAD model's construction, not just the final result. For a model built with 3 sketch-extrude pairs, we export 6 separate STEP files capturing the 2D sketch wireframes and the evolving 3D solid after each operation.

This is analogous to showing your work in math, recording every frame of a robot's trajectory, or capturing intermediate compiler states during code execution. Existing CAD datasets give you the answer; CAD-Steps shows the process.

## Why This Matters

Intermediate supervision consistently outperforms outcome-only supervision across ML:

| Domain | Outcome-Only | With Intermediate States | Key Paper |
|--------|-------------|--------------------------|-----------|
| **Math** | Final answer only | Step-by-step solutions; PRMs outperform ORMs by 12%+ | Lightman et al. "Let's Verify Step by Step" (2023) |
| **Robotics** | Success/failure signal | Dense trajectory (state, action, next_state) at 10-50Hz | RT-2 (2023), Diffusion Policy (2023) |
| **Code** | Final output | Execution traces, intermediate states | - |
| **CAD** | Final .step file only | **CAD-Steps: geometry at every construction step** | **This work** |

CAD has the same sequential structure as these domains, but until now, no dataset captured the intermediate geometry. DeepCAD provides symbolic operation sequences; the ABC Dataset provides final geometry; CAD-Steps bridges the gap with actual geometry at every step.

## What's In the Dataset

Each model contains STEP files for every construction step, plus rich metadata:

```
data/cad_steps_output/
├── 00000007/
│   ├── state_0000.step        # Sketch 1 (2D wireframe)
│   ├── state_0001.step        # Extrude 1 (3D solid)
│   └── metadata.json          # Operations, sketch geometry, parameters
├── 00000061/
│   ├── state_0000.step        # Sketch 1
│   ├── state_0001.step        # Extrude 1
│   ├── state_0002.step        # Sketch 2 (on existing solid)
│   ├── state_0003.step        # Extrude 2 (cut/join)
│   └── metadata.json
└── ...
```

### State Types

- **Sketch states**: 2D wireframe geometry (edges/wires on the sketch plane), exported as STEP containing curves. Captures the "drawing" phase of CAD.
- **Extrude states**: 3D solid geometry after applying the extrusion (new body, join, cut, or intersect). Captures the cumulative solid.

### metadata.json

```json
{
  "data_id": "00000061",
  "num_sequence_steps": 4,
  "states": [
    {
      "index": 0,
      "type": "sketch",
      "name": "Sketch 1",
      "step_file": "state_0000.step",
      "sketch_plane": {
        "origin": [0, 0, 0],
        "normal": [0, 0, 1],
        "x_axis": [1, 0, 0]
      },
      "profiles": [
        {
          "id": "JGC",
          "loops": [
            {
              "is_outer": true,
              "curves": [
                {"type": "Line3D", "start": [0, 0, 0], "end": [0.025, 0, 0]},
                {"type": "Arc3D", "start": [0.025, 0, 0], "end": [0, -0.025, 0], "center": [0, 0, 0], "radius": 0.025}
              ]
            }
          ]
        }
      ]
    },
    {
      "index": 1,
      "type": "extrude",
      "name": "Extrude 1",
      "step_file": "state_0001.step",
      "operation": "NewBodyFeatureOperation",
      "extent_type": "OneSideFeatureExtentType",
      "extent_one": 0.0127,
      "profiles_used": ["JGC"]
    }
  ]
}
```

## Dataset Statistics (200-model pilot)

| Metric | Value |
|--------|-------|
| Models processed | 200 |
| Success rate | 100% |
| Total STEP files | 395 |
| Total size | 32.8 MB |
| Processing time (8 workers) | 1.5 seconds |
| Avg states per model | ~2.0 |
| Avg time per model | 7.7 ms |

### Full Dataset Projections (178,238 models)

| Metric | Estimate |
|--------|----------|
| Total STEP files | ~352,000 |
| Total size | ~29 GB |
| Processing time (8 workers) | ~3 minutes |
| Operations covered | Sketch, Extrude (New/Join/Cut/Intersect) |

## Data Sources

| Source | Models | Included | Notes |
|--------|--------|----------|-------|
| DeepCAD (sketch+extrude subset) | 178,238 | Primary | Pre-filtered, JSON sequences available |
| ABC Dataset | ~1M | Planned | ~10% are sketch+extrude; rest use unsupported ops |
| Fusion 360 Gallery | 8,625 | Planned | Richer operations (fillet, chamfer, etc.) |

## Quick Start

```bash
# Clone
git clone https://github.com/amywork777/cad-steps-dataset.git
cd cad-steps-dataset

# Install dependencies (requires Python 3.10+)
pip install cadquery numpy

# Download DeepCAD source data (~185 MB)
cd data && mkdir -p deepcad_raw && cd deepcad_raw
curl -L http://www.cs.columbia.edu/cg/deepcad/data.tar | tar x
cd ../..

# Test on 5 models
cd code
python3 local_export.py --test

# Run on 200 models with 8 workers
python3 run_local_batch.py --count 200 --workers 8

# Run on everything
python3 run_local_batch.py --all --workers 10
```

## Repository Structure

```
├── code/
│   ├── local_export.py          # Core: replay DeepCAD JSON → STEP at each step
│   ├── run_local_batch.py       # Parallel batch runner with checkpointing
│   ├── cadlib/                  # DeepCAD's CAD parsing library (from ChrisWu1997/DeepCAD)
│   ├── export_steps.py          # Onshape API pipeline (deprecated, rate-limited)
│   ├── run_parallel_batch.py    # Onshape API batch runner (deprecated)
│   └── onshape_api/             # Onshape REST API client (Python 3 port)
├── data/
│   ├── deepcad_raw/             # DeepCAD JSON source (178k models)
│   └── cad_steps_output/        # Generated STEP files + metadata
├── docs/
│   ├── METHODOLOGY.md           # Technical approach and pipeline details
│   ├── PAPER_NOTES.md           # Research paper planning and related work
│   ├── EXPERIMENT_LOG.md        # Chronological experiment log
│   ├── ROADMAP.md               # Project status and next steps
│   └── reports/                 # Batch test reports
└── README.md
```

## The Journey (TL;DR)

We initially built a full Onshape API pipeline to extract intermediate STEP geometry by rolling back the feature tree. After porting the Python 2 onshape-cad-parser to Python 3 and getting it working, we discovered Onshape's API rate limits make large-scale extraction impossible: even an Enterprise plan (10k calls/year) would take **392 years** for 178k models. Their ToS also prohibits data mining public documents.

We pivoted to a local pipeline using OpenCascade (via CadQuery/OCP). By replaying DeepCAD's pre-parsed JSON construction sequences locally, we achieved **885x speedup** (7.7ms vs 23s per model), **100% success rate**, and **zero API dependency**. The full 178k dataset can be generated in ~3 minutes.

See [docs/EXPERIMENT_LOG.md](docs/EXPERIMENT_LOG.md) for the full chronological story, and [docs/METHODOLOGY.md](docs/METHODOLOGY.md) for technical details.

## What CAD-Steps Enables

- **Process reward models for CAD**: Score each construction step, not just the final geometry
- **Imitation learning on geometry trajectories**: (state, action, next_state) triples for sequential CAD
- **Step-level verification**: Detect errors at the step where they occur
- **Next-state prediction**: Given current geometry + operation parameters, predict the resulting geometry
- **Inverse CAD**: Given before/after geometry, infer what operation was applied
- **Sketch understanding**: 2D wireframe geometry captures the "thinking" phase before 3D operations

## Known Limitations

- **Sketch+extrude only**: DeepCAD's data is limited to sketch and extrude operations. No fillets, chamfers, revolves, patterns, or other advanced features.
- **No parametric constraints**: DeepCAD's JSON contains resolved geometry (coordinates) but not the original design-intent constraints (concentric, parallel, equal-length, etc.). This is a significant limitation documented in [docs/PAPER_NOTES.md](docs/PAPER_NOTES.md).
- **Reconstructed geometry**: Shapes are rebuilt from parsed parameters, not extracted from the original Onshape models. Minor numerical differences are possible.

## Citation

```bibtex
@misc{zhou2026cadsteps,
  title={CAD-Steps: A Large-Scale Dataset of Intermediate CAD Construction States},
  author={Zhou, Amy},
  year={2026},
  howpublished={\url{https://github.com/amywork777/cad-steps-dataset}}
}
```

## Acknowledgments

This dataset builds on [DeepCAD](https://github.com/ChrisWu1997/DeepCAD) by Wu et al. (ICCV 2021) for source data and CAD parsing, and uses [OpenCASCADE](https://dev.opencascade.org/) via [CadQuery](https://github.com/CadQuery/cadquery) for geometry reconstruction and STEP export.

## License

Dataset: CC-BY-4.0. Code: MIT.
