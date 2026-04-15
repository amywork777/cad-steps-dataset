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

## 2. Background: CAD Modeling Paradigms

Understanding CAD modeling approaches is essential for contextualizing this dataset. We identify three primary paradigms in modern CAD, two of which are amenable to machine learning.

### 2.1 Feature-Based / Parametric Modeling (ML-Tractable)

The dominant paradigm in mechanical CAD. Models are constructed through a sequence of operations:

1. **Sketch**: Define 2D geometry on a plane with curves and constraints
2. **Feature Operations**: Extrude, revolve, sweep, or loft sketches into 3D solids
3. **Boolean Operations**: Combine solids via union, subtract, or intersect
4. **Refinement**: Add fillets, chamfers, holes, patterns

**Key characteristics:**
- Maintains a "feature tree" or "design history" that records every operation
- Parametric: dimensions can be changed and geometry updates automatically
- Captures design intent (e.g., "this hole should always be centered")

**Software**: SolidWorks, Onshape, Fusion 360, CATIA, Creo, NX

**ML Tractability**: High. The explicit operation sequence provides natural training data for sequence models. Each step has clear input (current geometry) and output (next geometry).

### 2.2 Constructive Solid Geometry (CSG) (ML-Tractable)

An older but mathematically elegant approach. Models are defined as boolean combinations of primitive shapes:

- **Primitives**: Box, sphere, cylinder, cone, torus
- **Operations**: Union (∪), intersection (∩), subtraction (−)
- **Representation**: Binary tree where leaves are primitives and internal nodes are boolean operations

**Key characteristics:**
- Compact representation
- Well-defined grammar
- Less common in modern professional CAD, but used in OpenSCAD, game engines, and educational tools

**ML Tractability**: High. The tree structure maps naturally to recursive neural networks or transformers. Operations are discrete and well-defined.

### 2.3 Direct Modeling (Not ML-Tractable)

A history-free approach where users manipulate geometry directly:

- Push/pull faces to change dimensions
- Drag edges to reshape
- No feature tree or parametric relationships

**Key characteristics:**
- Fast for quick edits and conceptual design
- Works well on imported geometry with no history
- No record of "how" the model was built

**Software**: SpaceClaim, Siemens NX Synchronous Technology, some Onshape tools

**ML Tractability**: Low. Without construction history, there is no sequence to learn from. The final geometry provides no information about the design process.

### 2.4 Other Paradigms

**Surface Modeling (NURBS)**: Freeform curves and patches for organic shapes. Common in automotive and industrial design. Different mathematical foundation (B-splines) than solid modeling.

**Mesh-Based**: Triangle meshes, common in graphics and 3D printing. Lacks the precision and editability of solid models.

**Implicit/SDF**: Signed distance functions. Gaining interest in ML due to differentiability (e.g., DeepSDF, Occupancy Networks).

### 2.5 Scope of This Dataset

CAD-Steps focuses on **feature-based modeling**, specifically the sketch-and-extrude workflow. This is the most common approach in mechanical engineering and captures rich design intent. We leave CSG and other paradigms for future work.

## 3. Related Work

### CAD Datasets
- ABC Dataset (Koch et al., 2019): 1M models, final geometry only
- DeepCAD (Wu et al., 2021): 178K models, symbolic sequences, no intermediate geometry
- Fusion 360 Gallery: ~20K models with construction history
- SketchGraphs: 2D sketch constraint data

### Intermediate Supervision in Other Domains
- Mathematics: Chain-of-thought, step-by-step solutions
- Robotics: Full trajectory supervision vs. goal-only
- Code: Execution traces, debugging data

## 4. Dataset Construction

### 4.1 Source Data
We build on DeepCAD's parsed construction sequences from Onshape public documents.

### 4.2 Geometry Replay Pipeline
For each model:
1. Parse JSON construction sequence
2. Initialize OpenCascade (via CadQuery) workspace
3. For each operation (sketch, extrude, etc.):
   - Execute operation on current geometry
   - Export current state to STEP format
   - Record operation metadata
4. Compress and package

### 4.3 Handling Edge Cases
- Orphan sketches: Retained in metadata, geometry exported separately
- Failed operations: Logged and skipped
- Oversized models: Capped constraints at 500 curves, metadata at 1MB

### 4.4 Scale and Performance
- 215,096 models processed
- 750,000 STEP files generated
- 16 GB total (gzip compressed)
- Processing rate: 27 models/second on 6 CPU workers

## 5. Dataset Analysis

### 5.1 Statistics
| Metric | Value |
|--------|-------|
| Total models | 215,096 |
| Total STEP files | 750,000 |
| Avg steps per model | 3.5 |
| Median steps per model | 3 |
| Max steps per model | 12 |
| Total size (compressed) | 16 GB |

### 5.2 Operation Distribution
- Sketch: 51.2%
- Extrude: 48.8%

Note: The DeepCAD source data primarily contains sketch-and-extrude workflows. More complex operations (revolve, sweep, loft) are underrepresented.

### 5.3 Step Distribution
- Min steps: 2
- Max steps: 50
- Most models follow a simple pattern: sketch → extrude → (optional refinement)

## 6. Benchmark Tasks

### 6.1 Next-Step Geometry Prediction
Given: geometry at step N, operation description for step N+1
Predict: geometry at step N+1
Metrics: Chamfer distance, IoU

### 6.2 Operation Classification
Given: geometry at step N, geometry at step N+1
Predict: operation type and parameters
Metrics: Accuracy, parameter error

### 6.3 Construction Sequence Completion
Given: partial sequence (geometry + operations for steps 1..k)
Predict: remaining steps to reach target geometry
Metrics: Edit distance, final geometry similarity

## 7. Experiments

[TODO: Baseline results]

## 8. Limitations

- Source data from Onshape may have biases toward certain modeling styles
- STEP format loses some parametric information
- No assembly or multi-body context
- Sketch constraints recorded but not enforced in replay

## 9. Conclusion

CAD-Steps fills a critical gap in CAD machine learning by providing intermediate geometry supervision. We hope this enables new approaches to generative CAD, manufacturing-aware design, and human-AI collaborative modeling.

## Acknowledgments

- DeepCAD team for original construction sequence data
- OpenCascade/CadQuery for geometry kernel
- Vizcom for compute resources

## References

[TODO: Add full references]
