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

### 3.1 CAD Datasets

| Dataset | Size | Format | Intermediate States |
|---------|------|--------|---------------------|
| ABC Dataset [1] | 1M | STEP/OBJ | Final only |
| DeepCAD [2] | 178K | JSON sequences | Operations only |
| Fusion 360 Gallery [3] | 8.6K | Construction history | Operations only |
| SketchGraphs [4] | 15M | Constraint graphs | 2D sketches only |
| **CAD-Steps (ours)** | 215K | STEP files | **Full 3D geometry** |

The key gap: existing datasets provide either final geometry (ABC) or symbolic operations (DeepCAD), but not intermediate 3D geometry at each step.

### 3.2 CAD Generation Approaches

**Sequence-based / Feature-based:**
- **DeepCAD** [2]: Transformer autoencoder on sketch-extrude sequences. First generative model for CAD operations.
- **SkexGen** [12]: Disentangled codebooks for sketch and extrude, improved diversity.
- **Vitruvion** [13]: Generative model for parametric CAD sketches with constraints.

**Direct B-Rep Generation:**
- **SolidGen** [14]: Autoregressive B-Rep synthesis, first to generate CAD directly in boundary representation.
- **BRepGen** [15]: Diffusion on structured latent geometry trees. State-of-the-art, generates complex curved surfaces.
- **BRepDiff** [16]: Single-stage B-Rep diffusion, faster than BRepGen.
- **HoLa** [17]: Holistic latent representation for B-Rep generation.
- **DTGBrepGen** [18]: Decoupled topology-geometry generation.

**CSG-based:**
- **CSGNet** [19]: Neural shape parser for constructive solid geometry.
- **CSG-Stump** [20]: Learning-friendly CSG representation.
- **DualCSG** [21]: Learning dual CSG trees for compact modeling.

**LLM-based (emerging):**
- **CAD-Llama** [22]: Leveraging LLMs for parametric 3D modeling.
- **FlexCAD** [23]: Unified controllable CAD generation with fine-tuned LLMs.
- **Seek-CAD** [24]: Training-free CAD generation using DeepSeek-R1 with Chain-of-Thought.
- **Text2CAD** [25]: Text to 3D CAD via technical drawings.

### 3.3 Research Groups

- **Autodesk AI Lab**: World's leading publisher on generative CAD. Key contributors: Karl Willis, Joe Lambourne, Pradeep Jayaraman.
- **Columbia Graphics (Changxi Zheng)**: DeepCAD, foundational CAD generation work.
- **Simon Fraser (Yasutaka Furukawa)**: BRepGen, direct B-Rep generation.
- **Princeton LIPS**: SketchGraphs, Vitruvion, constraint-based sketch generation.
- **MIT CSAIL (Wojciech Matusik)**: Fusion 360 Gallery, programmatic CAD construction.

### 3.4 Intermediate Supervision in Other Domains
- **Mathematics**: Chain-of-thought prompting shows step-by-step reasoning outperforms direct answers [9].
- **Robotics**: Full trajectory supervision beats goal-only supervision.
- **Code**: Execution traces improve debugging and program synthesis.

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

## 6. Evaluation Framework

A comprehensive evaluation of CAD generation requires metrics beyond simple geometric similarity. We propose a multi-level evaluation framework.

### 6.1 Geometric Metrics

**Point-based metrics** (computed on sampled point clouds):
- **Chamfer Distance (CD)**: Average nearest-neighbor distance between point sets. Standard in 3D ML, but insensitive to topology.
- **Hausdorff Distance (HD)**: Maximum nearest-neighbor distance. Captures worst-case deviation, important for manufacturing tolerances.
- **F-Score**: Fraction of points within a threshold distance. Balances precision and recall.

**Volume-based metrics**:
- **Intersection over Union (IoU)**: Computed on voxelized representations. Captures overall shape overlap.
- **Volume Error**: Absolute difference in solid volume. Critical for mass/weight calculations.

### 6.2 Topological Metrics

Geometric metrics can miss critical structural differences. Two shapes may have similar Chamfer distance but completely different topology.

- **Euler Characteristic**: χ = V - E + F (vertices - edges + faces). Distinguishes genus (number of holes).
- **Betti Numbers**: β₀ = connected components, β₁ = holes/tunnels, β₂ = voids. More detailed topological signature.
- **Face/Edge/Vertex Counts**: Simple but informative. A correct reconstruction should match these exactly.

### 6.3 Parametric Fidelity Metrics

For CAD specifically, we care about design intent, not just final geometry.

- **Dimension Accuracy**: Error in key dimensions (lengths, radii, angles) vs. ground truth.
- **Constraint Satisfaction**: Percentage of original sketch constraints preserved (parallel, perpendicular, tangent, equal length, etc.).
- **Operation Sequence Similarity**: Edit distance between predicted and ground truth construction sequences.

### 6.4 Manufacturing Metrics

Ultimately, CAD models must be manufacturable.

- **Minimum Wall Thickness**: Thin walls may be unprintable or structurally weak.
- **Overhang Angle**: For 3D printing, overhangs >45° require support.
- **Draft Angle**: For injection molding, surfaces need draft for mold release.
- **Watertightness**: Closed manifold with no self-intersections.

### 6.5 Benchmark Tasks

**Task 1: Next-Step Geometry Prediction**
- Input: Geometry at step N, operation description for step N+1
- Output: Geometry at step N+1
- Evaluation: CD, HD, IoU, topology match

**Task 2: Operation Classification**
- Input: Geometry at step N, geometry at step N+1
- Output: Operation type and parameters
- Evaluation: Classification accuracy, parameter RMSE

**Task 3: Construction Sequence Completion**
- Input: Partial sequence (steps 1..k), target final geometry
- Output: Remaining operations to reach target
- Evaluation: Sequence edit distance, final geometry CD

## 7. Experiments

### 7.1 Baseline: Operation Sequence Prediction

As a simple baseline, we analyze the predictability of construction sequences using a Markov model.

**Method:**
Given the current operation type, predict the next operation type using maximum likelihood from training data.

**Results (500 model sample):**

| Current Operation | Most Likely Next | Accuracy |
|-------------------|------------------|----------|
| Sketch | ExtrudeFeature | 92.0% |
| ExtrudeFeature | Sketch | 75.4% |

The high predictability (92% for Sketch → Extrude) reflects the dataset's focus on sketch-and-extrude workflows. This establishes an upper bound for operation-type prediction but says nothing about geometric accuracy.

### 7.2 Baseline: Nearest-Neighbor Geometry Retrieval

For geometry prediction, we evaluate k-nearest-neighbor retrieval. Given geometry at step N, retrieve the most similar training example and return its next state.

**Method:**
1. Sample 2048 points uniformly from each STEP file surface
2. Compute point cloud embedding (mean + std of coordinates as simple baseline)
3. Retrieve k=1 nearest neighbor by L2 distance
4. Return retrieved example's next-step geometry

**Preliminary Results (100 test models):**

| Metric | NN Retrieval | Random |
|--------|--------------|--------|
| Chamfer Distance (×10⁻³) | ~15 | ~45 |
| Operation Type Match | 78% | 50% |

The nearest-neighbor approach beats random but leaves significant room for learned methods.

### 7.3 Discussion

Key findings:

1. **Operation sequences are predictable**: Sketch → Extrude pattern dominates (92% accuracy), suggesting the dataset captures consistent design workflows.
2. **Geometry requires learning**: Simple retrieval is insufficient for precise reconstruction.
3. **Intermediate states matter**: The 3.5 average steps per model provides meaningful supervision beyond just final geometry.

We leave training of neural sequence models (e.g., Transformer-based autoencoders following DeepCAD [2]) to future work, as our primary contribution is the dataset itself.

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

[1] S. Koch, A. Matveev, Z. Jiang, F. Williams, A. Artemov, E. Burnaev, M. Alexa, D. Zorin, and D. Panozzo. "ABC: A Big CAD Model Dataset For Geometric Deep Learning." CVPR 2019.

[2] R. Wu, C. Xiao, and C. Zheng. "DeepCAD: A Deep Generative Network for Computer-Aided Design Models." ICCV 2021.

[3] K. D. D. Willis, Y. Pu, J. Luo, H. Chu, T. Du, J. G. Lambourne, A. Solar-Lezama, and W. Matusik. "Fusion 360 Gallery: A Dataset and Environment for Programmatic CAD Construction from Human Design Sequences." SIGGRAPH 2021.

[4] A. Seff, Y. Ovadia, W. Zhou, and R. P. Adams. "SketchGraphs: A Large-Scale Dataset for Modeling Relational Geometry in Computer-Aided Design." ICML 2020 Workshop.

[5] J. J. Park, P. Florence, J. Straub, R. Newcombe, and S. Lovegrove. "DeepSDF: Learning Continuous Signed Distance Functions for Shape Representation." CVPR 2019.

[6] C. R. Qi, H. Su, K. Mo, and L. J. Guibas. "PointNet: Deep Learning on Point Sets for 3D Classification and Segmentation." CVPR 2017.

[7] C. R. Qi, L. Yi, H. Su, and L. J. Guibas. "PointNet++: Deep Hierarchical Feature Learning on Point Sets in a Metric Space." NeurIPS 2017.

[8] A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. N. Gomez, Ł. Kaiser, and I. Polosukhin. "Attention Is All You Need." NeurIPS 2017.

[9] J. Wei, X. Wang, D. Schuurmans, M. Bosma, B. Ichter, F. Xia, E. Chi, Q. Le, and D. Zhou. "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." NeurIPS 2022.

[10] Open CASCADE Technology. https://dev.opencascade.org/

[11] CadQuery. https://github.com/CadQuery/cadquery

[12] X. Xu, K. D. D. Willis, J. G. Lambourne, C.-F. Cheng, P. K. Jayaraman, and Y. Furukawa. "SkexGen: Autoregressive Generation of CAD Construction Sequences with Disentangled Codebooks." ICML 2022.

[13] A. Seff, W. Zhou, N. Richardson, and R. P. Adams. "Vitruvion: A Generative Model of Parametric CAD Sketches." ICLR 2022.

[14] P. K. Jayaraman, J. G. Lambourne, N. Desai, K. D. D. Willis, A. Sanghi, and N. J. W. Morris. "SolidGen: An Autoregressive Model for Direct B-rep Synthesis." TMLR 2023.

[15] X. Xu, J. G. Lambourne, P. K. Jayaraman, Z. Wang, K. D. D. Willis, and Y. Furukawa. "BrepGen: A B-rep Generative Diffusion Model with Structured Latent Geometry." SIGGRAPH 2024.

[16] M. Lee, et al. "BrepDiff: Single-Stage B-rep Diffusion Model." SIGGRAPH 2025.

[17] Y. Liu, et al. "HoLa: B-Rep Generation using a Holistic Latent Representation." SIGGRAPH 2025.

[18] J. Li, Y. Fu, and F. Chen. "DTGBrepGen: A Novel B-rep Generative Model through Decoupling Topology and Geometry." CVPR 2025.

[19] G. Sharma, R. Goyal, D. Liu, E. Kalogerakis, and S. Maji. "CSGNet: Neural Shape Parser for Constructive Solid Geometry." CVPR 2018.

[20] D. Ren, J. Zheng, J. Cai, J. Li, H. Jiang, Z. Cai, J. Zhang, L. Pan, M. Zhang, H. Zhao, and S. Liu. "CSG-Stump: A Learning Friendly CSG-Like Representation for Interpretable Shape Parsing." ICCV 2021.

[21] Q. Yu, et al. "DualCSG: Learning Dual CSG Trees for General and Compact CAD Modeling." arXiv 2023.

[22] Y. Li, et al. "CAD-Llama: Leveraging Large Language Models for Computer-Aided Design Parametric 3D Modeling." CVPR 2025.

[23] Z. Zhang, et al. "FlexCAD: Unified and Versatile Controllable CAD Generation with Fine-tuned Large Language Models." ICLR 2025.

[24] "Seek-CAD: A Self-refined Generative Modeling for 3D Parametric CAD Using Local Inference via DeepSeek." arXiv 2026.

[25] M. A. Sadil, et al. "Text2CAD: Text to 3D CAD Generation via Technical Drawings." NeurIPS 2024.
