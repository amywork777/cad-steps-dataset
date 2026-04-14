# CAD-Steps: Intermediate State Dataset for Parametric CAD

A large-scale dataset of CAD construction sequences with **intermediate geometry states** - capturing not just final models, but the geometry at each step of the construction process.

## Why This Matters

Existing CAD datasets give you either:
- Final geometry only (ABC Dataset)
- Construction sequences as symbolic operations (DeepCAD)

But to train models that understand *how* to build CAD, you need:
```
geometry_0 → operation_1 → geometry_1 → operation_2 → geometry_2 → ...
```

This is the first dataset to capture intermediate STEP geometry at each construction step.

## Research Motivation

### Intermediate Supervision > Outcome-Only Supervision

Other domains have shown that training on intermediate states dramatically improves model performance:

| Domain | Evidence |
|--------|----------|
| **Math** | Step-by-step solutions (GSM8K/MATH), Chain-of-thought, Process Reward Models (PRMs) outperform Outcome Reward Models (ORMs) - "Let's Verify Step by Step" (OpenAI, 2023) |
| **Robotics** | Trajectory data captures (state, action, next_state) at every timestep. RT-1/RT-2 trained on 130k demonstrations. Diffusion Policy uses full action trajectories |
| **Code** | Edit sequences and commit histories enable code evolution models. Intermediate compilation states provide richer supervision than final output alone |

**The pattern**: intermediate supervision produces stronger models than outcome-only supervision. CAD has the same structure (a sequence of operations transforming geometry) but no existing dataset captures intermediate geometry states.

### What CAD-Steps Enables

- **Process reward models for CAD** - reward each construction step, not just final geometry
- **Imitation learning on geometry trajectories** - (state, action, next_state) triples
- **Step-by-step CAD reasoning** - chain-of-thought for design
- **Next-state prediction** - given geometry + operation, predict resulting geometry
- **Plan verification** - check if a proposed construction plan produces valid intermediate states

## Dataset Structure

Each model contains STEP geometry files at every construction step, plus metadata:

```
data/
├── 00008841/
│   ├── state_0001.step     # After first extrude
│   ├── state_0002.step     # After second extrude
│   ├── state_0004.step     # After third extrude (odd indices = sketch-only, skipped)
│   ├── ...
│   └── metadata.json       # Feature tree + export status per state
├── 00007648/
│   └── ...
└── batch_results.json      # Aggregate statistics
```

### metadata.json format
```json
{
  "source_url": "https://cad.onshape.com/documents/.../e/...",
  "features": [
    {"featureId": "...", "featureType": "newSketch", "name": "Sketch 1"},
    {"featureId": "...", "featureType": "extrude", "name": "Extrude 1"}
  ],
  "states": [
    {"index": 0, "feature": {...}, "exported": false, "reason": "sketch-only"},
    {"index": 1, "feature": {...}, "exported": true, "step_file": "state_0001.step"}
  ]
}
```

## Data Pipeline

### Approach 1: Onshape API (current proof-of-concept)
For each model: copy document → rollback feature tree → export STEP at each state → cleanup.
Limited by Onshape free API rate limits (~15 exports/day).

### Approach 2: Local reconstruction (in development)
Parse DeepCAD's processed JSON sequences and reconstruct geometry using Open Cascade (cadquery/build123d).
No API limits; target 178K models in <24 hours.

## Progress

| Phase | Status | Notes |
|-------|--------|-------|
| Proof of concept (15 models) | ✅ Done | 86.7% success rate on DeepCAD pre-filtered models |
| Parallel runner | ✅ Done | ThreadPoolExecutor with rate limiting |
| 500K ABC links downloaded | ✅ Done | 50 YAML files × 10K models |
| Rate limit analysis | ✅ Done | Free tier too slow; pivoting to local reconstruction |
| Local reconstruction pipeline | 🔄 Next | cadquery/build123d from DeepCAD JSON |
| Full 178K extraction | ⏳ Planned | Depends on local pipeline |
| HuggingFace upload | ⏳ Planned | After extraction complete |

## Sources

| Source | Models | Type | Status |
|--------|--------|------|--------|
| DeepCAD (sketch+extrude subset) | ~178K | Pre-filtered, verified | 🔄 Primary target |
| ABC Dataset (full) | ~1M | Unfiltered (~10% sketch+extrude) | ⏳ Later |
| Fusion 360 Gallery | ~20K | Diverse operations | ⏳ Later |

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Test the Onshape export pipeline (requires API credentials)
cd code
python3 export_steps.py --test

# Run a batch (with rate limiting)
python3 run_parallel_batch.py \
    --link_file ../data/abc_links/objects_0000.yml \
    --output_dir ../data/batch_test \
    --limit 20 --workers 2 --rate 0.3
```

### API Credentials
Create `code/creds.json`:
```json
{
    "https://cad.onshape.com": {
        "access_key": "YOUR_ACCESS_KEY",
        "secret_key": "YOUR_SECRET_KEY"
    }
}
```

## Repository Structure

```
├── code/
│   ├── export_steps.py          # Core: rollback + STEP export pipeline
│   ├── run_parallel_batch.py    # Parallel batch runner with rate limiting
│   ├── run_deepcad_batch.py     # Sequential batch (original test)
│   ├── onshape_api/             # Onshape REST API client (Python 3 port)
│   └── parser.py                # DeepCAD feature parser
├── data/
│   ├── abc_links/               # 500K model URLs (50 YAML files)
│   └── deepcad_batch/           # Test batch output (13 models, 38 STEP files)
├── docs/
│   ├── METHODOLOGY.md
│   ├── ROADMAP.md
│   ├── INFRASTRUCTURE.md
│   └── reports/                 # Test batch reports
└── README.md
```

## Key Findings

- **Onshape free API**: ~1000 calls/day rolling limit. Each model export costs ~20 calls. Not viable for 178K+ models.
- **ABC dataset composition**: ~30% deleted (404), ~60% use unsupported ops, ~10% sketch+extrude only.
- **DeepCAD pre-filtered**: 86.7% export success rate, avg 23s/model, avg 2.5 states/model.
- **Local reconstruction**: Best path forward. No rate limits, 100x faster.

## Citation

TBD

## License

TBD
