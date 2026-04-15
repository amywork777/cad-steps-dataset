# CAD-Steps: A Dataset of Intermediate CAD Construction States

## Abstract

We introduce CAD-Steps, a large-scale dataset of intermediate CAD geometry states capturing the step-by-step construction process of 215,096 mechanical parts. Unlike existing CAD datasets that provide either final geometry (ABC) or symbolic operations (DeepCAD), CAD-Steps includes actual 3D geometry (STEP format) at every construction stage alongside structured operation metadata. This intermediate supervision paradigm—proven effective in mathematics, robotics, and code generation—enables new approaches to CAD generation, understanding, and manufacturing analysis. The dataset contains 750,000 STEP files totaling 16GB, with an average of 3.5 construction steps per model.

## 1. Introduction

### The Intermediate Supervision Gap in CAD

Machine learning approaches to CAD have made significant progress, but a fundamental gap remains: most datasets provide only endpoints, not journeys. The ABC Dataset offers 1M final CAD models. DeepCAD provides construction sequences as symbolic operations. Neither captures what happens geometrically at each intermediate step.

This matters because:
- **Training**: Models learn better from step-by-step supervision than outcome-only supervision (demonstrated in math reasoning, robotics trajectories, code execution traces)
- **Inference**: Intermediate checkpoints enable error correction, backtracking, and human-in-the-loop editing
- **Understanding**: Seeing how geometry evolves reveals design intent and manufacturing constraints

### Contributions

1. **CAD-Steps Dataset**: 215,096 models with 750,000 intermediate STEP files
2. **Generation Pipeline**: Open-source tooling for replaying construction sequences via OpenCascade
3. **Benchmark Tasks**: Proposed evaluation suite for next-step prediction, operation classification, and manufacturing analysis

## 2. Related Work

### CAD Datasets
- ABC Dataset (Koch et al., 2019): 1M models, final geometry only
- DeepCAD (Wu et al., 2021): 178K models, symbolic sequences, no intermediate geometry
- Fusion 360 Gallery: ~20K models with construction history
- SketchGraphs: 2D sketch constraint data

### Intermediate Supervision in Other Domains
- Mathematics: Chain-of-thought, step-by-step solutions
- Robotics: Full trajectory supervision vs. goal-only
- Code: Execution traces, debugging data

## 3. Dataset Construction

### 3.1 Source Data
We build on DeepCAD's parsed construction sequences from Onshape public documents.

### 3.2 Geometry Replay Pipeline
For each model:
1. Parse JSON construction sequence
2. Initialize OpenCascade (via CadQuery) workspace
3. For each operation (sketch, extrude, etc.):
   - Execute operation on current geometry
   - Export current state to STEP format
   - Record operation metadata
4. Compress and package

### 3.3 Handling Edge Cases
- Orphan sketches: Retained in metadata, geometry exported separately
- Failed operations: Logged and skipped
- Oversized models: Capped constraints at 500 curves, metadata at 1MB

### 3.4 Scale and Performance
- 215,096 models processed
- 750,000 STEP files generated
- 16 GB total (gzip compressed)
- Processing rate: 27 models/second on 6 CPU workers

## 4. Dataset Analysis

### 4.1 Statistics
| Metric | Value |
|--------|-------|
| Total models | 215,096 |
| Total STEP files | 750,000 |
| Avg steps per model | 3.5 |
| Median steps per model | 3 |
| Max steps per model | 12 |
| Total size (compressed) | 16 GB |

### 4.2 Operation Distribution
- Sketch: 51.2%
- Extrude: 48.8%

Note: The DeepCAD source data primarily contains sketch-and-extrude workflows. More complex operations (revolve, sweep, loft) are underrepresented.

### 4.3 Step Distribution
- Min steps: 2
- Max steps: 50
- Most models follow a simple pattern: sketch → extrude → (optional refinement)

## 5. Benchmark Tasks

### 5.1 Next-Step Geometry Prediction
Given: geometry at step N, operation description for step N+1
Predict: geometry at step N+1
Metrics: Chamfer distance, IoU

### 5.2 Operation Classification
Given: geometry at step N, geometry at step N+1
Predict: operation type and parameters
Metrics: Accuracy, parameter error

### 5.3 Construction Sequence Completion
Given: partial sequence (geometry + operations for steps 1..k)
Predict: remaining steps to reach target geometry
Metrics: Edit distance, final geometry similarity

## 6. Experiments

[TODO: Baseline results]

## 7. Limitations

- Source data from Onshape may have biases toward certain modeling styles
- STEP format loses some parametric information
- No assembly or multi-body context
- Sketch constraints recorded but not enforced in replay

## 8. Conclusion

CAD-Steps fills a critical gap in CAD machine learning by providing intermediate geometry supervision. We hope this enables new approaches to generative CAD, manufacturing-aware design, and human-AI collaborative modeling.

## Acknowledgments

- DeepCAD team for original construction sequence data
- OpenCascade/CadQuery for geometry kernel
- Vizcom for compute resources

## References

[TODO: Add full references]
