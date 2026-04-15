---
license: cc-by-4.0
task_categories:
  - text-to-3d
  - other
tags:
  - cad
  - 3d
  - step
  - mechanical-engineering
  - intermediate-states
  - construction-sequence
  - geometric-constraints
  - deepcad
pretty_name: CAD-Steps
size_categories:
  - 100K<n<1M
---

# CAD-Steps: Intermediate CAD Construction States

**CAD-Steps** is the first large-scale dataset of intermediate CAD construction states with geometric constraints. For each of 178,238 parametric CAD models from the [DeepCAD](https://github.com/ChrisWu1997/DeepCAD) corpus, we export STEP geometry at every construction step (sketch, extrude, cut, etc.), not just the final result.

## Why intermediate states?

Current CAD datasets provide either final geometry ([ABC Dataset](https://deep-geometry.github.io/abc-dataset/)) or symbolic operation sequences (DeepCAD), but not the intermediate 3D geometry at each step. This gap matters because:

- **In math**, chain-of-thought and step-by-step solutions dramatically outperform outcome-only supervision
- **In robotics**, trajectory demonstrations beat goal-only demonstrations
- **In CAD**, models are built incrementally. Seeing how geometry evolves through each operation is critical for learning to design

CAD-Steps provides the missing link: paired (geometry, operation, next_geometry) tuples that capture **how** a model is built, not just **what** the final result looks like.

## Dataset Format

Each model is stored in its own directory:

```
{model_id}/
├── metadata.json        # Full construction metadata
├── state_0001.step.gz   # Sketch wireframe (2D)
├── state_0002.step.gz   # After first extrude (3D solid)
├── state_0003.step.gz   # After second operation
└── ...
```

### STEP Files

All geometry files are gzip-compressed STEP (ISO 10303-21) files. Sketch states are exported as 2D wire bodies; extrude states are exported as 3D solids. Decompress with `gzip -d` or read directly in Python with `gzip.open()`.

### Metadata

Each `metadata.json` contains:

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
          "plane": { "origin": [...], "normal": [...] },
          "curves": [
            { "type": "Line", "start": [...], "end": [...] },
            { "type": "Circle", "center": [...], "radius": 0.005 },
            { "type": "Arc", "center": [...], "start": [...], "end": [...] }
          ],
          "constraints": [
            { "type": "perpendicular", "curves": [0, 1] },
            { "type": "equal_length", "curves": [2, 3] },
            { "type": "coincident", "curves": [0, 1], "point": [...] }
          ]
        }
      }
    },
    {
      "state_num": 2,
      "type": "ExtrudeFeature",
      "operation": "NewBodyFeatureOperation",
      "extent_type": "OneSideFeatureExtentType",
      "extent_one": 0.01,
      "taper_angle": 0.0,
      "step_file": "state_0002.step.gz"
    }
  ],
  "bounding_box": { "min": [...], "max": [...] }
}
```

### Geometric Constraints

Sketches include inferred geometric constraints:

| Constraint | Description |
|---|---|
| `coincident` | Two curves meet at a point |
| `perpendicular` | Two lines are perpendicular |
| `parallel` | Two lines are parallel |
| `equal_length` | Two lines have equal length |
| `equal_radius` | Two arcs/circles have equal radius |
| `concentric` | Two arcs/circles share a center |
| `horizontal` | Line is horizontal |
| `vertical` | Line is vertical |

### Statistics (from 500-model sample)

- Average 3.5 construction states per model
- State types: Sketch (52%), ExtrudeFeature (48%)
- Average compressed size: ~84 KB per model
- Constraint distribution: parallel (24%), equal_length (22%), perpendicular (20%), equal_radius (18%), coincident (7%), concentric (5%), vertical (3%), horizontal (2%)

## Loading the Data

### Python

```python
import json, gzip
from pathlib import Path

model_dir = Path("00000062")

# Load metadata
with open(model_dir / "metadata.json") as f:
    meta = json.load(f)

# Load a STEP file
with gzip.open(model_dir / "state_0002.step.gz", "rt") as f:
    step_text = f.read()

# Parse with Open CASCADE (via CadQuery or OCP)
import cadquery as cq
solid = cq.importers.importStep(gzip.decompress(
    (model_dir / "state_0002.step.gz").read_bytes()
).decode())
```

### With HuggingFace Datasets

```python
from huggingface_hub import snapshot_download

# Download entire dataset
snapshot_download(
    repo_id="amzyst1/cad-steps",
    repo_type="dataset",
    local_dir="./cad-steps"
)
```

## Generation Pipeline

Models are generated locally using [CadQuery](https://github.com/CadQuery/cadquery) and the OpenCascade kernel (OCP). The pipeline:

1. Reads DeepCAD's pre-parsed JSON construction sequences (178K models)
2. Replays each operation using OCP (sketch wireframes, extrude/cut solids)
3. Exports STEP geometry at each intermediate state
4. Infers geometric constraints from curve geometry
5. Compresses output with gzip (~5.5x compression ratio)

Processing speed: ~17 models/second with 6 workers on a standard machine.

## Source Data

The construction sequences come from [DeepCAD](https://github.com/ChrisWu1997/DeepCAD) by Rundi Wu et al., which parsed public Onshape models into parametric operation sequences. We add the intermediate STEP geometry that DeepCAD's JSON format does not include.

## Citation

```bibtex
@dataset{cad_steps_2026,
  title={CAD-Steps: Intermediate CAD Construction States with Geometric Constraints},
  author={Amy Zhou},
  year={2026},
  url={https://huggingface.co/datasets/amzyst1/cad-steps}
}
```

## License

This dataset is released under [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). The underlying construction sequences are from DeepCAD (MIT License).
