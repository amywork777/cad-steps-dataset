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

## Research Motivation

### Intermediate Supervision > Outcome-Only Supervision

Other domains have shown that training on intermediate states dramatically improves model performance:

**Math Reasoning**
- GSM8K and MATH datasets include step-by-step solutions, not just final answers
- Chain-of-thought prompting works because models learn intermediate reasoning
- Process Reward Models (PRMs) that reward each step outperform Outcome Reward Models (ORMs) that only check final answers
- See: "Let's Verify Step by Step" (OpenAI, 2023)

**Robotics**
- Trajectory/demonstration data captures (state, action, next_state) at every timestep
- Imitation learning trains policies to reproduce expert behavior step-by-step
- Google's RT-1/RT-2 trained on 130k real robot demonstrations
- Diffusion Policy treats action trajectories as sequences to denoise

**The Pattern**
Both domains found that intermediate supervision produces stronger models than outcome-only supervision. CAD has the same structure - a sequence of operations transforming geometry - but no dataset captures intermediate geometry states.

### Current CAD Training Approaches (and their limits)

| Approach | Training Data | Limitation |
|----------|--------------|------------|
| DeepCAD | Operation sequences as tokens | No intermediate geometry |
| VideoCAD | Screen recordings | Pixels, not geometry |
| CAD-LLM | Sketch coordinates as code | Sketches only, no 3D |
| BrepGen | Final B-rep only | No construction history |

**CAD-Steps enables:**
- Process reward models for CAD (reward each construction step)
- Imitation learning on geometry trajectories
- Step-by-step CAD reasoning models

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

## Infrastructure

- **Budget**: $500/month (Vizcom research stipend)
- **Data collection**: Runs on laptop (API-bound, not compute-bound)
- **Training**: Rent GPU as needed (Lambda Labs, RunPod, Modal)
- **Storage**: HuggingFace Datasets (free for public datasets)

See [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) for details.

## Tools

### Data Collection
- **Onshape API** + modified parser for rollback + STEP export
- **CadQuery** for programmatic STEP handling

### Synthetic Data Generation
- **ForgeCAD** (forgecad.io) - code-first CAD in JS/TS, AI-friendly
  - Scripts ARE the construction sequence
  - Can generate diverse models with LLMs
  - Export STEP at any point

See [docs/TOOLS.md](docs/TOOLS.md) for full details.
