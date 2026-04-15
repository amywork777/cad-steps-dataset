# Paper Notes: CAD-Steps

Raw notes and planning for a research paper on the CAD-Steps dataset.

## Working Title

**CAD-Steps: A Large-Scale Dataset of Intermediate CAD Construction States for Process-Level Supervision**

Alternative titles:
- "Showing Your Work in CAD: Intermediate Geometry States at Scale"
- "Beyond Final Geometry: 178K CAD Models with Step-by-Step Construction States"

## Core Contribution

**First large-scale dataset providing actual geometry (STEP files) at every intermediate construction step of a parametric CAD model.**

Existing datasets provide either (a) final geometry without construction history (ABC), or (b) symbolic operation sequences without intermediate geometry (DeepCAD). CAD-Steps bridges this gap by providing both the geometry AND the operation at every step, enabling (state, action, next_state) supervision for CAD.

## Related Work

### CAD Datasets

| Dataset | Year | Models | What It Provides | What It Lacks |
|---------|------|--------|-----------------|---------------|
| ABC Dataset | 2019 | 1M | Final STEP geometry, surface normals | No construction history |
| DeepCAD | 2021 | 178K | Symbolic sketch+extrude sequences (JSON) | No intermediate geometry |
| Fusion 360 Gallery | 2021 | 8,625 | Construction sequences + Gym environment | Small scale; no intermediate STEP |
| **CAD-Steps** | **2026** | **178K** | **STEP at every construction step** | Sketch+extrude only; no constraints |

**Key papers:**
- Koch et al. "ABC: A Big CAD Model Dataset for Geometric Deep Learning" (CVPR 2019)
- Wu et al. "DeepCAD: A Deep Generative Network for Computer-Aided Design Models" (ICCV 2021)
- Willis et al. "Fusion 360 Gallery: A Dataset and Environment for Programmatic CAD Construction from Human Design Sequences" (ACM TOG 2021)

### CAD Generation Models (downstream users of this data)

- **SkexGen** (ICML 2022): Autoregressive generation with disentangled codebooks for sketch+extrude
- **CAD-SIGNet** (CVPR 2024): Point cloud to CAD sequence via sketch-instance-guided attention
- **Text2CAD** (NeurIPS 2024): Text-to-parametric-CAD with multi-level annotations on DeepCAD
- **CAD-LLaMA** (CVPR 2025): LLM-based parametric 3D model generation
- **CADFusion** (ICML 2025): Visual feedback in LLMs for text-to-CAD
- **BrepDiff** (SIGGRAPH 2025): Single-stage B-rep diffusion model
- **Prompt2CAD** (2026): Lightweight LLM framework for conversational CAD

All of these train on DeepCAD's symbolic sequences. CAD-Steps enables training them with geometric intermediate supervision, which we hypothesize will improve performance.

### Intermediate Supervision (the theoretical motivation)

- **Lightman et al. "Let's Verify Step by Step"** (OpenAI, 2023): Process Reward Models (PRMs) that score each reasoning step outperform Outcome Reward Models (ORMs) by 12%+ on MATH. Released PRM800K with 800K step-level human labels.
- **Uesato et al. "Solving Math Word Problems with Process- and Outcome-Based Feedback"** (2022): Earlier comparison of process vs outcome supervision.
- **RT-1 / RT-2** (Google, 2022-2023): Robotics transformers trained on dense trajectory data (state, action, next_state) at every timestep.
- **Diffusion Policy** (Chi et al., 2023): Uses full action trajectories for imitation learning in robotics.
- **RoboInter** (2026): Intermediate representations for robotic manipulation, showing that intermediate supervision bridges the plan-to-execute gap.

**The pattern across all domains**: step-level supervision produces stronger models than outcome-only supervision. CAD is a natural fit because it IS a sequential process, but no existing dataset captures intermediate geometry.

### Process Reward Models for CAD (novel direction)

No one has built a Process Reward Model for CAD yet. With CAD-Steps, you could train a model that evaluates:
- "Is this sketch geometrically valid?"
- "Does this extrusion produce a reasonable solid?"
- "Is this construction step consistent with the design intent?"

This parallels how PRMs evaluate reasoning steps in math. The reward signal at each step enables better search and verification during CAD generation.

## Methodology Section Outline

### 3.1 Problem Formulation
- CAD construction as a Markov Decision Process: S_0 → a_0 → S_1 → a_1 → ... → S_n
- States S_i are geometry (STEP files); actions a_i are parametric operations (sketch or extrude)
- Existing data: only (a_0, a_1, ..., a_n) and S_n available. We provide all S_i.

### 3.2 Failed Approach: Onshape API Extraction
- Built full Python 3 port of onshape-cad-parser
- Pipeline: copy document → rollback feature tree → export STEP at each position → cleanup
- Results: 86.7% success rate, ~23s/model, 22 API calls/model
- **Critical failure**: rate limits (429 after ~300 calls, 20-hour lockout)
- Even Enterprise plan: 10k calls/year ÷ 22 calls/model = 454 models/year
- 178k models ÷ 454 models/year = **392 years**
- Also: ToS prohibits data mining public documents
- This is a valuable negative result: the "obvious" approach doesn't scale

### 3.3 Successful Approach: Local OpenCascade Reconstruction
- Source: DeepCAD's pre-parsed JSON (178k models with sketch+extrude sequences)
- Pipeline: parse JSON → replay operations with OCC → export STEP at each step
- Key insight: the geometry kernel is the bottleneck, not the CAD platform
- Sketch export: build 2D wireframes (edges/wires) from curve data, export as STEP
- Extrude export: build 3D solid from sketch face + prism, apply boolean, export as STEP
- Parallelized with ProcessPoolExecutor, checkpointing for crash recovery

### 3.4 Data Format
- Per-model directory with state_XXXX.step files and metadata.json
- Metadata includes: operation type, parameters, sketch geometry, sketch plane coordinate system
- Both 2D sketch states and 3D extrude states included

## Experiments We Could Run

### Experiment 1: Next-State Prediction
- **Task**: Given state S_i and action a_i, predict state S_{i+1}
- **Representation**: Point cloud or voxel grid for geometry, tokenized sequence for action
- **Baselines**: DeepCAD (no intermediate geometry), direct final-state prediction
- **Metric**: Chamfer distance, IoU between predicted and ground-truth S_{i+1}
- **Hypothesis**: Models trained with intermediate states will generalize better to unseen operations

### Experiment 2: Inverse CAD (Operation Prediction)
- **Task**: Given S_i and S_{i+1}, predict action a_i
- **Baselines**: Random, nearest-neighbor in operation space
- **Metric**: Operation type accuracy, parameter error
- **Why it matters**: This is reverse engineering at the step level

### Experiment 3: Process Reward Model for CAD
- **Task**: Train a reward model that scores (S_i, a_i, S_{i+1}) triples
- **Training**: Positive examples from dataset; negative examples from perturbed operations
- **Evaluation**: Use as a verifier during beam search in CAD generation
- **Comparison**: PRM vs ORM (only scores final geometry)
- **Hypothesis**: PRM catches errors earlier, produces better construction sequences

### Experiment 4: Trajectory Quality Assessment
- **Task**: Given a full sequence (S_0, a_0, S_1, ..., S_n), is it a valid CAD construction?
- **Baselines**: Rule-based validation (non-empty solid, increasing complexity)
- **Application**: Filtering generated CAD sequences

## Limitations (Important for Paper)

### Constraints Not Available
DeepCAD's JSON stores resolved geometry (final coordinates) but NOT the original parametric constraints from Onshape. Missing data includes:
- Geometric constraints: concentric, parallel, perpendicular, tangent, coincident, symmetric, equal-length, horizontal, vertical, midpoint
- Dimensional constraints: explicit distances, angles, radii as design parameters
- Feature references: which sketch plane references which face of an existing body

This is a significant limitation because constraints encode **design intent** - the "why" behind geometry. Two sketches can produce identical geometry but have very different constraint structures, implying different design intent. Constraints are the "reasoning" of CAD, analogous to chain-of-thought in language models.

**Why constraints are missing**: The onshape-cad-parser (used by DeepCAD) only exports resolved geometry, not the constraint solver state. Onshape's API does expose constraints via `GET /api/partstudios/.../features` in the `constraints` field of sketch features, but extracting this at scale hits the same rate limit wall.

**Future work**: Constraints could be:
1. Recovered from the Fusion 360 Gallery (which stores constraint data)
2. Inferred post-hoc from geometry (e.g., two circles at the same center → concentric)
3. Augmented by re-running designs through a constraint solver

### Sketch+Extrude Only
DeepCAD pre-filtered for models using only sketch and extrude. This covers a substantial portion of simple mechanical parts but excludes:
- Fillets and chamfers (edge treatments)
- Revolves (rotational symmetry)
- Patterns (circular/linear arrays)
- Sweeps, lofts, shells
- Assembly features

### Reconstructed vs Original Geometry
Geometry is rebuilt from parsed parameters, not extracted from original Onshape models. Potential differences:
- Numerical precision (floating point vs exact Parasolid representation)
- Different B-rep topology for equivalent geometry
- Sketch planes may not exactly match original model coordinate systems

## Target Venues

- **Workshop papers**: CAD/Graphics workshops at CVPR, ICCV, SIGGRAPH
- **Dataset track**: NeurIPS Datasets and Benchmarks
- **Full paper**: ICCV, ECCV, or AAAI (if we have strong experimental results)
- **arXiv preprint**: Publish early to establish priority

## Figures to Create

1. **Teaser figure**: Side-by-side comparison of what existing datasets provide vs CAD-Steps
   - ABC: just final geometry
   - DeepCAD: just symbolic sequence
   - CAD-Steps: geometry at every step (show 4-5 intermediate states of one model)

2. **Pipeline diagram**: DeepCAD JSON → Parse → Replay with OCC → Export STEP at each step

3. **The rate limit wall**: Chart showing API calls needed vs available for different Onshape plans

4. **Speed comparison**: Bar chart of Onshape API (23s) vs Local OCC (7.7ms) per model

5. **Dataset statistics**: Distribution of steps per model, sketch complexity, operation types

6. **Example intermediate states**: 3-4 models showing progressive construction (render STEP files)
