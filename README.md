# CAD-Steps: Intermediate CAD Construction States Dataset

A large-scale dataset of intermediate CAD geometry states, capturing the step-by-step construction process of 3D models.

## Overview

**CAD-Steps** provides paired data of CAD construction operations and their resulting geometry at each intermediate step. Unlike existing CAD datasets that only provide final geometry (ABC) or symbolic operations (DeepCAD), this dataset includes the actual 3D geometry at every construction stage.

This is analogous to:
- **Math**: step-by-step solutions vs just final answers
- **Robotics**: full trajectories vs just start/end states
- **Code**: execution traces vs just input/output pairs

Intermediate supervision consistently outperforms outcome-only supervision in these domains.

## Dataset Statistics

| Metric | Count |
|--------|-------|
| Source models | 215,096 |
| Total STEP files | ~750,000 |
| Total size | ~16 GB (compressed) |
| Avg steps per model | ~3.5 |

## Data Format

Each model directory contains:
- `state_0.step.gz` - Initial geometry state
- `state_1.step.gz` - Geometry after first operation
- `state_N.step.gz` - Geometry after Nth operation
- `metadata.json` - Construction sequence and constraints

### Metadata Schema

```json
{
  "model_id": "00000007",
  "num_steps": 3,
  "operations": [
    {
      "step": 0,
      "type": "sketch",
      "curves": [...],
      "constraints": [...]
    },
    {
      "step": 1, 
      "type": "extrude",
      "extent": 0.5,
      "direction": [0, 0, 1]
    }
  ]
}
```

## Source Data

Built from [DeepCAD](https://github.com/ChrisWu1997/DeepCAD) construction sequences, which were originally derived from Onshape public documents.

## Generation Pipeline

1. Parse DeepCAD JSON construction sequences
2. Replay each operation using OpenCascade (via CadQuery)
3. Export STEP geometry at each intermediate state
4. Compress and package with metadata

Processing rate: ~27 models/second on 6 CPU workers.

## Use Cases

- **CAD generation models**: Train models to predict next construction step given current geometry
- **CAD understanding**: Learn to recognize construction patterns and operations
- **Geometry diffusion**: Condition generation on intermediate states
- **Manufacturing analysis**: Understand how designs are built up

## Citation

If you use this dataset, please cite:

```bibtex
@dataset{cad_steps_2026,
  title={CAD-Steps: Intermediate CAD Construction States Dataset},
  author={Zhou, Amy},
  year={2026},
  url={https://huggingface.co/datasets/amzyst1/cad-steps}
}
```

## License

This dataset is released under CC-BY-4.0. The source DeepCAD data is under MIT license.

## Acknowledgments

- DeepCAD team for the original construction sequence data
- OpenCascade/CadQuery for the geometry kernel
