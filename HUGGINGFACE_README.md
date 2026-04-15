---
license: cc-by-4.0
task_categories:
  - other
tags:
  - cad
  - 3d
  - engineering
  - step
  - manufacturing
  - design
  - geometry
  - constraints
pretty_name: CAD-Steps
size_categories:
  - 100K<n<1M
---

# CAD-Steps: Intermediate CAD Construction States

**CAD-Steps** is a large-scale dataset of intermediate CAD construction states, derived from the [DeepCAD](https://github.com/ChrisWu1997/DeepCAD) dataset. While existing CAD datasets provide either final geometry or symbolic operation sequences, CAD-Steps provides the actual 3D geometry (STEP files) at every intermediate step of the construction process.

This is analogous to having step-by-step solutions in math or trajectory data in robotics, rather than just final answers.

## Why This Matters

Current approaches to CAD generation train on final shapes or symbolic operation sequences, but never see what the geometry looks like mid-construction. Research in other domains shows that intermediate supervision dramatically improves learning:

- **Math**: Chain-of-thought training outperforms outcome-only supervision
- **Robotics**: Trajectory-level data enables better policy learning than goal-only data  
- **Code**: Step-by-step execution traces improve code generation

CAD-Steps brings this insight to 3D CAD by capturing the geometry at every sketch and extrude operation.

## Dataset Structure

Each model is stored in its own directory with the following structure:

```
{model_id}/
├── metadata.json          # Full construction metadata
├── state_0001.step.gz     # First state (usually a 2D sketch wireframe)
├── state_0002.step.gz     # Second state (usually a 3D extrude)
├── state_0003.step.gz     # Third state (sketch on solid, or another extrude)
└── ...
```

### STEP Files

Each `.step.gz` file is a gzip-compressed STEP (ISO 10303-21) file representing the CAD geometry at that point in the construction sequence. States alternate between:

- **Sketch states**: 2D wireframe geometry (edges on a plane) representing the sketch profiles before extrusion
- **Extrude states**: 3D solid geometry after applying an extrude (add, cut, or intersect) operation

### Metadata

Each `metadata.json` contains rich information about the construction sequence:

```json
{
  "data_id": "00000062",
  "num_sequence_steps": 4,
  "states": [
    {
      "state_num": 1,
      "type": "Sketch",
      "exported": true,
      "step_file": "state_0001.step.gz",
      "size_kb": 15.5,
      "sketch": {
        "profile_id": {
          "plane": {"origin": [...], "normal": [...], "x_axis": [...], "y_axis": [...]},
          "curves": [
            {"loop": 0, "type": "Line", "start": [...], "end": [...]},
            {"loop": 0, "type": "Arc", "start": [...], "end": [...], "mid": [...]},
            {"loop": 0, "type": "Circle", "center": [...], "radius": 0.01}
          ],
          "constraints": [
            {"type": "perpendicular", "curves": [0, 1]},
            {"type": "equal_length", "curves": [0, 2]},
            {"type": "coincident", "curves": [0, 1], "point": [...]}
          ]
        }
      }
    },
    {
      "state_num": 2,
      "type": "ExtrudeFeature",
      "exported": true,
      "step_file": "state_0002.step.gz",
      "size_kb": 61.4,
      "operation": "NewBodyFeatureOperation",
      "extent_type": "OneSideFeatureExtentType",
      "extent_one": 0.005,
      "taper_angle": 0.0
    }
  ],
  "total_exported": 4,
  "total_states": 4,
  "bounding_box": {"min": [...], "max": [...]}
}
```

### Geometric Constraints

Sketch metadata includes inferred geometric constraints:

| Constraint | Description |
|---|---|
| `coincident` | Two curves share an endpoint |
| `parallel` | Two lines are parallel |
| `perpendicular` | Two lines are perpendicular |
| `equal_length` | Two lines have equal length |
| `equal_radius` | Two arcs/circles have equal radius |
| `horizontal` | A line is horizontal |
| `vertical` | A line is vertical |
| `concentric` | Two arcs/circles share a center |

### Curve Types

Sketches contain these primitive curve types:
- `Line` (start, end points)
- `Arc` (start, end, mid points)
- `Circle` (center, radius)

## Statistics

| Metric | Value |
|---|---|
| Source dataset | DeepCAD (178K models) |
| Avg states per model | ~3.6 |
| State types | Sketch, ExtrudeFeature |
| Constraint types | 8 (coincident, parallel, perpendicular, equal_length, equal_radius, horizontal, vertical, concentric) |
| File format | STEP (ISO 10303-21), gzip compressed |
| Compression ratio | ~5.5x |

## Loading the Data

### Python

```python
import json, gzip, os
from pathlib import Path

# Load a single model
model_dir = Path("00000062")
with open(model_dir / "metadata.json") as f:
    metadata = json.load(f)

# Read a STEP file
with gzip.open(model_dir / "state_0001.step.gz", "rt") as f:
    step_content = f.read()

# Parse with OCP/CadQuery
import cadquery as cq
from OCP.STEPControl import STEPControl_Reader
reader = STEPControl_Reader()
reader.ReadFile(str(model_dir / "state_0001.step"))  # decompress first
```

### Using HuggingFace datasets

```python
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="amzyst1/cad-steps",
    repo_type="dataset",
    local_dir="./cad-steps"
)
```

## Source Data

This dataset is derived from [DeepCAD](https://github.com/ChrisWu1997/DeepCAD) by Rundi Wu et al. The original DeepCAD dataset contains ~178K parametric CAD models with construction sequences sourced from Onshape public documents via the [ABC Dataset](https://deep-geometry.github.io/abc-dataset/).

### Processing Pipeline

1. Parse DeepCAD's JSON construction sequences
2. Replay each sketch + extrude operation using [OpenCascade](https://dev.opencascade.org/) (via CadQuery/OCP)
3. Export STEP geometry at each intermediate state
4. Infer geometric constraints from curve geometry
5. Compress with gzip

## Citation

If you use this dataset, please cite both CAD-Steps and the original DeepCAD paper:

```bibtex
@misc{cadsteps2026,
  title={CAD-Steps: A Dataset of Intermediate CAD Construction States},
  author={Amy Zhou},
  year={2026},
  url={https://huggingface.co/datasets/amzyst1/cad-steps}
}

@inproceedings{wu2021deepcad,
  title={DeepCAD: A Deep Generative Network for Computer-Aided Design Models},
  author={Wu, Rundi and Xiao, Chang and Zheng, Changxi},
  booktitle={Proceedings of the IEEE/CVF International Conference on Computer Vision},
  year={2021}
}
```

## License

This dataset is released under [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). The source data (DeepCAD / ABC Dataset) is from publicly shared Onshape documents.
