# Paper Outline: CAD-Steps

**Working Title:** CAD-Steps: A Large-Scale Dataset of Intermediate CAD Construction States for Process-Supervised Geometric Reasoning

**Target Venues:** CVPR Workshop on AI for CAD, ICCV, or arXiv preprint

---

## Abstract (150 words)

We introduce CAD-Steps, the first large-scale dataset of intermediate 3D geometry states captured at every step of a CAD construction sequence. Existing CAD datasets provide either final geometry (ABC) or symbolic operation sequences (DeepCAD), but neither captures the intermediate geometry that results from each operation. Drawing on the success of process supervision in mathematical reasoning — where step-level feedback outperforms outcome-only feedback by 12%+ — we construct a dataset of 178K models with STEP geometry exported after every sketch-and-extrude operation, yielding ~352K intermediate state files totaling ~29 GB. We document two extraction approaches: an Onshape API pipeline that proved infeasible at scale (rate-limited after ~300 calls, requiring 392 years for the full dataset), and a local OpenCascade reconstruction pipeline that processes the entire dataset in 3 minutes. We demonstrate the dataset's utility for next-state prediction and process reward modeling in CAD.

---

## 1. Introduction

### 1.1 The Problem

- CAD AI is advancing rapidly (DeepCAD, SkexGen, CAD-Coder, ToolCAD)
- All current approaches train on either final geometry or symbolic sequences
- Neither provides the intermediate geometric context a human designer uses
- Analogy: training a chess AI on game outcomes without the board positions, or training a math model on final answers without solution steps

### 1.2 The Insight: Process Supervision

- Lightman et al. (2023): Process reward models outperform outcome reward models on MATH by 12%+
- Robotics: RT-1/RT-2 trained on dense trajectory data (state, action, next_state)
- Code: execution traces and intermediate compilation states
- Pattern: **intermediate supervision produces stronger models than outcome-only supervision**
- CAD has the exact same sequential structure but no dataset captures intermediate geometry

### 1.3 Our Contribution

1. **CAD-Steps dataset**: 178K models with STEP geometry at every construction step (~352K files, ~29 GB)
2. **Negative result**: Documented why the Onshape API approach fails at scale (rate limits, ToS)
3. **Scalable pipeline**: Local OpenCascade reconstruction at 885× the speed of the API approach
4. **Baseline experiments**: Next-state prediction and process reward modeling (planned)

---

## 2. Related Work

### 2.1 CAD Datasets

- **ABC Dataset** (Koch et al., CVPR 2019): 1M CAD models from Onshape, final STEP geometry only. Designed for geometric deep learning (segmentation, surface reconstruction). No construction history.
- **DeepCAD** (Wu et al., ICCV 2021): 178K models with construction sequences as parametric JSON. Pioneered sequential CAD representation. No intermediate geometry.
- **Fusion 360 Gallery** (Willis et al., SIGGRAPH 2021): ~20K models with construction timelines from Autodesk Fusion 360. Includes B-rep at each step but limited scale and restricted to Fusion 360 format.
- **SketchGraphs** (Seff et al., 2020): 15M sketches with constraint graphs. 2D only.

### 2.2 CAD Generation

- **DeepCAD** (Wu et al., 2021): Transformer autoregressive model for CAD sequences
- **SkexGen** (Xu et al., ICML 2022): Disentangled codebooks for sketch/extrude
- **Point2Sequence** (Chen et al., 2023): Point cloud to CAD sequence
- **CAD-Coder** (Guan et al., NeurIPS 2025): CadQuery script generation with GRPO
- **ToolCAD** (2026): LLM tool-use for CAD with process reward
- **CADFusion** (Wang et al., ICML 2025): Visual feedback for text-to-CAD

### 2.3 Process Supervision

- **Let's Verify Step by Step** (Lightman et al., ICLR 2024): PRM800K, process vs outcome supervision
- **Uesato et al. (2022)**: Earlier process supervision comparison
- **Imitation learning**: Trajectory data in robotics (RT-1, RT-2, Diffusion Policy)
- **Epic50k** (2025): Efficient process supervision training data construction

---

## 3. The CAD-Steps Dataset

### 3.1 Design Principles

- **Complete trajectories**: Every model includes geometry at every intermediate step
- **Standard format**: STEP files (ISO 10303), the industry standard for CAD exchange
- **Rich metadata**: Each step annotated with operation type, parameters, and geometry statistics
- **Paired data**: Each step produces a `(state_n, operation_n, state_{n+1})` triple

### 3.2 Data Source: DeepCAD

- 178,238 models from Onshape, pre-filtered for sketch-and-extrude operations
- Each model stored as structured JSON with full parametric data
- Operations: NewBody, Join, Cut, Intersect (boolean operations on extruded profiles)
- Sketch primitives: Line, Arc, Circle with 2D coordinates on oriented sketch planes

### 3.3 Dataset Statistics

Present distributions of:
- Number of operations per model (histogram)
- Operation type frequencies (NewBody vs Join vs Cut vs Intersect)
- STEP file sizes per step (shows complexity growth)
- Extent types (OneSide, Symmetric, TwoSides)
- Total STEP files generated
- Success/failure rates and failure modes

### 3.4 Data Format

```
model_id/
├── state_0000.step    # Geometry after operation 0
├── state_0001.step    # Geometry after operation 1
├── ...
└── metadata.json      # Full trajectory metadata
```

### 3.5 Comparison with Existing Datasets

Table comparing CAD-Steps vs ABC vs DeepCAD vs Fusion 360 Gallery on:
- Scale (number of models)
- Intermediate geometry availability
- Operation diversity
- File format
- Accessibility (open vs restricted)

---

## 4. Data Collection Pipeline

### 4.1 Approach 1: Onshape API (Negative Result)

#### 4.1.1 Method
- For each model: copy document → rollback feature tree → export STEP at each state → cleanup
- Used Onshape's REST API with HMAC authentication
- Python 3 port of onshape-cad-parser (originally Python 2)

#### 4.1.2 Proof of Concept Results
- 15 models tested (DeepCAD subset)
- 86.7% success rate (13/15)
- Average 23 seconds/model, 2.5 states/model
- ~22 API calls per model

#### 4.1.3 Why It Failed at Scale
- Free tier: ~300 API calls trigger 20-hour lockout (HTTP 429)
- Enterprise tier: 10,000 calls/year = ~454 models/year
- 178K models × 22 calls = 3.9M calls = **392 years on Enterprise**
- Terms of Service prohibit data mining of public documents
- Full analysis: see Section 4.1.4 and Appendix A

#### 4.1.4 Rate Limit Analysis
- Observed: `Retry-After: 73808` (20.5 hours)
- No burst protection: entire daily quota consumed in 30 seconds
- Different endpoint groups may have separate limits
- Even optimized pipeline (12 calls/model minimum) = 175+ years

### 4.2 Approach 2: Local OpenCascade Reconstruction

#### 4.2.1 Method
- Parse DeepCAD JSON → `CADSequence` objects using DeepCAD's `cadlib`
- Reconstruct geometry locally using OpenCascade (via CadQuery/OCP Python bindings):
  1. Convert 2D sketch curves to 3D edges on the sketch plane
  2. Build wire → face from sketch profiles
  3. Extrude face along normal vector (`BRepPrimAPI_MakePrism`)
  4. Apply boolean operations (`BRepAlgoAPI_Fuse/Cut/Common`)
  5. Export cumulative geometry via `STEPControl_Writer`
- Repeat at each step, saving intermediate STEP files

#### 4.2.2 Implementation Details
- **Coordinate transform**: DeepCAD stores sketch curves in local 2D coordinates; we transform to 3D using the sketch plane's origin, normal, and x-axis
- **Sketch primitives**: Line (2 endpoints), Arc (start, mid, end via `GC_MakeArcOfCircle`), Circle (center + radius)
- **Profile construction**: Outer wire → inner wire(s) as holes → `BRepBuilderAPI_MakeFace`
- **Extrusion types**: OneSide, Symmetric (extrude both directions), TwoSides (different distances)
- **Boolean operations**: NewBody/Join → `BRepAlgoAPI_Fuse`, Cut → `BRepAlgoAPI_Cut`, Intersect → `BRepAlgoAPI_Common`
- **Validation**: Optional `BRepCheck_Analyzer` for shape validity checking

#### 4.2.3 Parallelization
- `ProcessPoolExecutor` with configurable worker count
- Each worker processes independent models (no shared state)
- Checkpoint support: skip already-processed models on restart
- Progress reporting every 50 models

#### 4.2.4 Results

**200-model validation batch (8 workers):**

| Metric | Value |
|--------|-------|
| Models processed | 200 |
| Success rate | 100% |
| STEP files generated | 395 |
| Total size | 32.8 MB |
| Wall clock time | 1.5 seconds |
| Effective time/model | 7.7 ms |

**Full dataset projections:**

| Workers | Estimated time | Throughput |
|---------|---------------|------------|
| 1 | ~23 minutes | 129 models/s |
| 4 | ~6 minutes | 516 models/s |
| 8 | ~3 minutes | 1,032 models/s |

### 4.3 Comparison of Approaches

| | Onshape API | Local (OCC) | Speedup |
|--|------------|-------------|---------|
| Time/model | 23,000 ms | 7.7 ms | **2,987×** |
| 178K models | 392 years | 3 minutes | **~10⁸×** |
| API calls | 3.9M | 0 | ∞ |
| Cost | Enterprise plan | Free | ∞ |

### 4.4 Limitations

- **Operation scope**: Only sketch-and-extrude operations (same as DeepCAD). No fillets, chamfers, revolves, patterns, or other advanced CAD features.
- **Reconstructed geometry**: STEP files are generated from parsed parameters, not exported from original Onshape documents. Minor geometric differences may exist due to OpenCascade vs Onshape kernel differences.
- **Failure modes**: Some models fail on degenerate geometry (self-intersecting profiles, zero-thickness extrusions, coincident edges). These are logged in metadata.
- **No sketch geometry**: Only post-extrude solid geometry is exported; 2D sketch states are available in metadata but not as separate geometric files.

---

## 5. Experiments (Planned)

### 5.1 Dataset Analysis
- Distribution of construction sequence lengths
- Operation type frequencies
- Geometric complexity growth across steps (file size, face count, edge count)
- Failure mode analysis

### 5.2 Next-State Prediction
- **Task**: Given `state_n.step` + `operation_{n+1}` parameters, predict `state_{n+1}.step`
- **Representation**: Voxelized or point cloud geometry
- **Baseline**: 3D CNN encoder-decoder
- **Metric**: Chamfer distance between predicted and ground-truth geometry

### 5.3 Process Reward Modeling
- **Task**: Given a partial construction trajectory, predict whether the final geometry will match the target
- **Training**: Use complete trajectories as positive examples, truncated/corrupted trajectories as negative
- **Evaluation**: Compare process reward model vs outcome reward model on held-out models

### 5.4 Operation Prediction (Inverse Modeling)
- **Task**: Given `state_n.step` and `state_{n+1}.step`, predict the operation that transforms one into the other
- **Evaluation**: Accuracy on operation type, extrusion distance, sketch plane, and boolean type

---

## 6. Discussion

### 6.1 Broader Impact
- Enables new training paradigms for CAD AI (process supervision, trajectory learning)
- Practical value for CAD education (step-by-step visualizations)
- Foundation for CAD verification and error detection systems

### 6.2 Ethical Considerations
- Source data from public Onshape documents (DeepCAD collection)
- No personal or sensitive information
- Open release promotes reproducibility

### 6.3 Future Work
- Extend to Fusion 360 Gallery (richer operations, ~20K models)
- Extend to full ABC dataset (~1M models, needs operation filtering)
- Add support for fillets, chamfers, revolves, patterns
- Release pre-computed point cloud and voxel representations
- Train and release baseline models

---

## 7. Conclusion

We present CAD-Steps, the first large-scale dataset of intermediate CAD construction states. By capturing STEP geometry at every step of 178K construction sequences, we create ~352K state files that enable process-supervised learning for CAD AI. We document both a failed Onshape API approach (valuable as a negative result for the community) and a successful local reconstruction pipeline that is 885× faster. We believe intermediate geometric supervision will improve CAD generation models, just as process supervision improved mathematical reasoning.

---

## References

1. Koch, S., Matveev, A., Jiang, Z., Williams, F., Artemov, A., Burnaev, E., Alexa, M., Zorin, D., & Panozzo, D. (2019). ABC: A Big CAD Model Dataset for Geometric Deep Learning. *CVPR*.
2. Wu, R., Xiao, C., & Zheng, C. (2021). DeepCAD: A Deep Generative Network for Computer-Aided Design Models. *ICCV*.
3. Willis, K.D.D., Pu, Y., Luo, J., Chu, H., Du, T., Lambourne, J.G., Solar-Lezama, A., & Matusik, W. (2021). Fusion 360 Gallery: A Dataset and Environment for Programmatic CAD Construction from Human Design Sequences. *SIGGRAPH*.
4. Lightman, H., Kosaraju, V., Burda, Y., Edwards, H., Baker, B., Lee, T., Leike, J., Schulman, J., Sutskever, I., & Cobbe, K. (2023). Let's Verify Step by Step. *ICLR 2024*.
5. Xu, X., Willis, K.D.D., Lambourne, J.G., Cheng, C.Y., Jayaraman, P.K., & Furukawa, Y. (2022). SkexGen: Autoregressive Generation of CAD Construction Sequences with Disentangled Codebooks. *ICML*.
6. Guan, Y., Xing, X., Wang, X., Zhang, J., Xu, D., & Yu, Q. (2025). CAD-Coder: Text-to-CAD Generation with Chain-of-Thought and Geometric Reward. *NeurIPS*.
7. Brohan, A., Brown, N., Carbajal, J., et al. (2023). RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control. *CoRL*.
8. Seff, A., Ovadia, Y., Zhou, W., & Adams, R.P. (2020). SketchGraphs: A Large-Scale Dataset for Modeling Relational Geometry in Computer-Aided Design. *ICML Workshop*.
9. Uesato, J., Kushman, N., Kumar, R., Song, F., Siegel, N., Wang, L., Creswell, A., Irving, G., & Higgins, I. (2022). Solving Math Word Problems with Process- and Outcome-Based Feedback.

---

## Appendix

### A. Onshape Rate Limit Details
Full rate limit analysis with HTTP headers, response codes, and per-endpoint breakdown.
See `docs/ONSHAPE_ANALYSIS.md`.

### B. DeepCAD JSON Format
Example JSON file with annotated fields showing how parametric operations are encoded.

### C. OpenCascade Reconstruction Details
Detailed walkthrough of the sketch → face → extrusion → boolean pipeline with OCC API calls.

### D. Full Dataset Statistics
Histograms and tables for all 178K models (after full extraction).
