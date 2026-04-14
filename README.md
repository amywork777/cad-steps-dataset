# CAD-Steps: Intermediate State Dataset for Parametric CAD

A large-scale dataset of CAD construction sequences with **intermediate geometry states** - capturing not just final models, but the geometry at each step of the construction process.

## Why This Matters

Existing CAD datasets give you either:
- Final geometry only (ABC Dataset)
- Construction sequences as symbolic operations (DeepCAD)

But to train models that understand *how* to build CAD, you need:
```
geometry_0 → "sketch rectangle" → geometry_1 → "extrude 10mm" → geometry_2 → ...
```

This is the first dataset to capture intermediate STEP files at each construction step.

## Dataset Structure

```
data/
├── model_00001/
│   ├── step_00.step      # Initial state
│   ├── step_01.step      # After first operation
│   ├── step_02.step      # After second operation
│   └── sequence.json     # Operations + metadata
├── model_00002/
│   └── ...
```

## Sources

| Source | Models | Status |
|--------|--------|--------|
| DeepCAD (Onshape) | 178k | 🔄 In Progress |
| ABC Dataset | 1M | ⏳ Planned |
| Fusion 360 Gallery | ~20k | ⏳ Planned |

## Getting Started

```bash
pip install -r requirements.txt
python scripts/parse_onshape.py --input links.txt --output data/
```

## Citation

TBD

## License

TBD
