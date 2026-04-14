# Paper Notes: CAD-Steps

Raw notes and outlines for writing the research paper.

## Working Title

**CAD-Steps: A Large-Scale Dataset of Intermediate Construction States for Parametric CAD**

Alternative titles:
- "Showing Your Work: Intermediate Geometry States for CAD Machine Learning"
- "Step-by-Step CAD: Dense Geometric Supervision for Construction Sequence Learning"

## Target Venues

- **Primary**: Workshop paper at CVPR/ICCV/ECCV (e.g., CV4AEC, AI4CE)
- **Alternative**: NeurIPS Datasets & Benchmarks track
- **Fallback**: arXiv preprint + HuggingFace dataset card

## Abstract Draft

Parametric CAD construction is inherently sequential: a model is built through a series of sketch and extrude operations. Existing CAD datasets provide either final geometry (ABC, 1M models) or symbolic operation sequences (DeepCAD, 178K models), but not the intermediate geometry at each construction step. This gap prevents training models with process-level supervision, which has been shown to outperform outcome-only supervision in math reasoning (PRM, 12%+), robotics (trajectory learning), and code generation. We present CAD-Steps, the first large-scale dataset of intermediate CAD construction states. Starting from DeepCAD's 178K parametric models, we replay each construction sequence using OpenCascade and export STEP geometry at every step, including 2D sketch wireframes. Our local reconstruction pipeline processes the full dataset in under 5 minutes on commodity hardware, producing ~352K STEP files (~29 GB). We document a failed attempt to extract this data via the Onshape API (rate limits make it infeasible at scale) as a valuable negative result. We release the dataset, pipeline code, and analysis to enable research on process reward models, imitation learning, and step-level verification for CAD.

## Related Work

### CAD Datasets

| Dataset | Year | Scale | What's Captured | Limitations |
|---------|------|-------|-----------------|-------------|
| ABC | 2019 | 1M | Final STEP geometry | No construction history |
| DeepCAD | 2021 | 178K | Symbolic construction sequences (sketch params + extrude params) | No intermediate geometry |
| Fusion 360 Gallery | 2021 | 8.6K | Construction sequences in sketch+extrude language, Gym environment | Small scale, no pre-computed intermediate STEP |
| SkexGen | 2022 | Uses DeepCAD | Disentangled codebook representation | Same data, no geometry states |
| Text2CAD | 2024 | 170K | Text annotations for DeepCAD models | Text-to-sequence, no geometry |
| **CAD-Steps (ours)** | **2026** | **178K** | **Intermediate STEP geometry at each step + sketch wireframes + parametric metadata** | Sketch+extrude only |

### Key distinction from DeepCAD

DeepCAD provides the *recipe* (parametric operation sequences). CAD-Steps provides the *result at each step* (B-Rep geometry). The relationship is:

```
DeepCAD: [op1_params, op2_params, op3_params]
CAD-Steps: [geometry_0.step, sketch_1.step, geometry_1.step, sketch_2.step, geometry_2.step, ...]
```

Together, they form complete (state, action, next_state) trajectories.

### Intermediate Supervision in Other Domains

**Math Reasoning:**
- Lightman et al. (2023). "Let's Verify Step by Step." Process Reward Models (PRMs) that verify each reasoning step outperform Outcome Reward Models (ORMs). PRM800K dataset of 800K step-level labels. Key result: process supervision achieves 78% on MATH benchmark subset.
- Cobbe et al. (2021). "Training Verifiers to Solve Math Word Problems." GSM8K dataset.
- Uesato et al. (2022). Outcome vs process supervision comparison.

**Robotics:**
- Brohan et al. (2023). RT-2: Vision-Language-Action models trained on trajectory data.
- Chi et al. (2023). Diffusion Policy: full action trajectories via denoising.
- RoboInter (Li et al., 2026). Intermediate representations for robotic manipulation.
- Robo-Dopamine (2026). Process reward modeling for robotics.

**Code:**
- Execution traces capture intermediate program states for debugging.
- Commit histories as edit sequences.

### CAD Generation Models (downstream users of our dataset)

- DeepCAD (Wu et al., 2021): Transformer-based autoregressive generation of CAD sequences
- SkexGen (Xu et al., 2022): disentangled codebooks for sketch+extrude
- CAD-SIGNet (Khan et al., 2024): point cloud to CAD sequence
- Text2CAD (Khan et al., 2024): text to parametric CAD
- CAD-LLaMA (Li et al., 2025): LLM-based CAD generation
- CADFusion (Wang et al., 2025): visual feedback for LLM-based CAD
- BrepGen (2025): B-Rep diffusion model
- Prompt2CAD (Zhou et al., 2026): LLM + visual feedback for CAD

## Our Contribution

1. **First large-scale intermediate CAD state dataset** (178K models, ~352K STEP files, ~29 GB)
2. **Both 2D and 3D states**: sketch wireframes exported as STEP, not just 3D solids
3. **Documented negative result**: Onshape API rate limits make large-scale extraction impossible (392 years for 178K models on Enterprise plan)
4. **Efficient local pipeline**: 885x faster than API-based extraction (7.7ms vs 23s per model)
5. **Rich metadata**: parametric operation details, sketch plane coordinates, curve-level geometry, loop topology

## Methodology Section Outline

### 3.1 Problem Formulation
- CAD construction as a Markov Decision Process
- State = B-Rep geometry (STEP), Action = parametric operation, Transition = CAD kernel execution
- Goal: provide (s_t, a_t, s_{t+1}) tuples at scale

### 3.2 Data Source
- DeepCAD dataset: 178,238 models with full parametric sequences
- Originally extracted from Onshape public documents
- Pre-filtered to sketch+extrude operations
- Data format: JSON with sketch profiles (Line3D, Circle3D, Arc3D), extrude parameters, coordinate systems

### 3.3 Failed Approach: Onshape API
- Attempted to roll back feature tree and export STEP at each state
- Built full Python 3 port of onshape-cad-parser
- Rate limits: HTTP 429 after ~300 calls, 20-hour lockout
- Annual limits: Free=unknown, Standard=2.5K, Pro=5K, Enterprise=10K
- Each model requires ~22 API calls
- 178K models / Enterprise = 392 years
- ToS prohibits data mining public documents
- **Conclusion**: API extraction does not scale

### 3.4 Successful Approach: Local Reconstruction
- Download DeepCAD's pre-parsed JSON data
- Replay construction sequences using OpenCascade (OCP/CadQuery bindings)
- For each model:
  1. Parse JSON into CADSequence objects
  2. For each extrude operation:
     a. Export 2D sketch wireframe as STEP (lines, arcs, circles on sketch plane)
     b. Create solid body via extrusion
     c. Apply boolean (join/cut/intersect) with accumulated body
     d. Export 3D geometry as STEP
  3. Save metadata.json with full parametric details
- Parallel processing via ProcessPoolExecutor
- Checkpointing: skip already-processed models on resume

### 3.5 Data Validation
- 200-model validation batch: 100% success rate
- Comparison with Onshape API exports for 13 overlapping models (pending)

## Experiments We Could Run

### Experiment 1: Outcome vs Process Supervision for CAD Reconstruction
- **Task**: Given a target 3D geometry (point cloud or voxel), predict the construction sequence
- **Baseline (outcome only)**: Train on (final_geometry, sequence) pairs. Only supervise on final output matching target
- **Ours (process supervision)**: Train on intermediate states. Add loss term for each intermediate geometry matching the ground truth at that step
- **Expected result**: process supervision improves reconstruction accuracy, especially for complex multi-step models

### Experiment 2: Next-State Prediction
- **Task**: Given current geometry + next operation parameters, predict the resulting geometry
- **Input**: STEP geometry (as point cloud or voxel) + operation params
- **Output**: predicted next STEP geometry
- **Metric**: Chamfer distance, IoU with ground truth next state
- **This is only possible with our dataset** (no other dataset has intermediate geometry)

### Experiment 3: Step-Level Quality Estimation
- **Task**: Given a construction step, predict whether it will lead to a valid final model
- **Analogy**: Process Reward Model for CAD
- **Dataset**: use our intermediate states as "correct" trajectories, generate corrupted trajectories as "incorrect"

### Experiment 4: Operation Prediction from Geometry Delta
- **Task**: Given geometry_t and geometry_{t+1}, predict what operation was applied
- **This is inverse modeling** and tests whether the geometric changes are informative enough to infer operations

### Experiment 5: Sketch Complexity Analysis
- Analyze sketch-level statistics: curve counts, loop counts, profile types
- Correlate with model complexity and downstream task difficulty

## Figures to Create

1. **Overview figure**: pipeline diagram (DeepCAD JSON → local reconstruction → STEP at each step)
2. **Example sequences**: 3-4 models showing their intermediate states as rendered images
3. **Comparison table**: CAD-Steps vs existing datasets
4. **Rate limit analysis**: chart showing impossibility of API-based extraction
5. **Speedup comparison**: bar chart of API vs local pipeline
6. **Distribution plots**: number of steps per model, file sizes, operation types

## Limitations and Future Work

### Current Limitations
1. **Sketch+extrude only**: no revolve, fillet, chamfer, pattern, loft, sweep
2. **No parametric constraints**: DeepCAD's JSON does not preserve constraint data (concentric, parallel, equal, perpendicular, tangent, etc.). The geometry is fully resolved. The design intent encoded in constraints is lost
3. **Reconstructed vs original**: geometry is replayed from parsed parameters, not extracted from original Onshape. Numerical precision may differ slightly
4. **No sketch-on-face**: sketches are placed on reference planes, not on faces of existing bodies
5. **No assembly data**: single-part models only

### Future Work
1. **Constraint recovery**: Infer geometric constraints from sketch geometry (e.g., detect when two circles share a center = concentric, when lines have equal length = equal constraint). This is a constraint detection problem
2. **Expand operation support**: extend to revolve, fillet, chamfer, pattern
3. **Fusion 360 Gallery integration**: process the 8.6K Fusion 360 models with same pipeline
4. **ABC Dataset**: filter and process the sketch+extrude subset (~50K models)
5. **Baseline experiments**: train and evaluate next-state prediction and process reward models
6. **Onshape API access**: partner with PTC/Onshape for research-grade API access to extract constraint data

### The Constraint Gap (Important for Paper)

This is worth a dedicated paragraph in the paper. In real CAD, designers don't just draw lines; they apply constraints that encode design intent:
- "These two holes must be concentric" (concentric constraint)
- "These edges must be parallel" (parallel constraint)
- "This dimension must equal that dimension" (equal constraint)

DeepCAD's parsed JSON strips all constraints, providing only the final evaluated geometry. This means our dataset captures the *geometric trajectory* but not the *reasoning trajectory*. Recovering constraints from geometry is an open problem and could be a compelling follow-up paper.

## BibTeX References

```bibtex
@inproceedings{wu2021deepcad,
  title={DeepCAD: A Deep Generative Network for Computer-Aided Design Models},
  author={Wu, Rundi and Xiao, Chang and Zheng, Changxi},
  booktitle={ICCV},
  year={2021}
}

@inproceedings{koch2019abc,
  title={ABC: A Big CAD Model Dataset For Geometric Deep Learning},
  author={Koch, Sebastian and Matveev, Albert and Jiang, Zhongshi and Williams, Francis and Artemov, Alexey and Burnaev, Evgeny and Alexa, Marc and Zorin, Denis and Panozzo, Daniele},
  booktitle={CVPR},
  year={2019}
}

@article{willis2021fusion360,
  title={Fusion 360 Gallery: A Dataset and Environment for Programmatic CAD Construction from Human Design Sequences},
  author={Willis, Karl DD and Pu, Yewen and Luo, Jieliang and Chu, Hang and Du, Tao and Lambourne, Joseph G and Solar-Lezama, Armando and Matusik, Wojciech},
  journal={ACM Transactions on Graphics (TOG)},
  volume={40},
  number={4},
  year={2021}
}

@article{lightman2023verify,
  title={Let's Verify Step by Step},
  author={Lightman, Hunter and Kosaraju, Vineet and Burda, Yura and Edwards, Harri and Baker, Bowen and Lee, Teddy and Leike, Jan and Schulman, John and Sutskever, Ilya and Cobbe, Karl},
  journal={arXiv preprint arXiv:2305.20050},
  year={2023}
}

@inproceedings{xu2022skexgen,
  title={SkexGen: Autoregressive Generation of CAD Construction Sequences with Disentangled Codebooks},
  author={Xu, Xiang and Willis, Karl DD and Lambourne, Joseph G and Cheng, Chin-Yi and Jayaraman, Pradeep Kumar and Furukawa, Yasutaka},
  booktitle={ICML},
  year={2022}
}

@inproceedings{khan2024cadsignet,
  title={CAD-SIGNet: CAD Language Inference from Point Clouds using Layer-wise Sketch Instance Guided Attention},
  author={Khan, Mohammad Sadil and others},
  booktitle={CVPR},
  year={2024}
}

@inproceedings{khan2024text2cad,
  title={Text2CAD: Generating Sequential CAD Designs from Beginner-to-Expert Level Text Prompts},
  author={Khan, Mohammad Sadil and Sinha, Sankalp and Sheikh, Talha Uddin and Stricker, Didier and Ali, Sk Aziz and Afzal, Muhammad Zeshan},
  booktitle={NeurIPS},
  year={2024}
}

@inproceedings{li2025cadllama,
  title={CAD-Llama: Leveraging Large Language Models for Computer-Aided Design Parametric 3D Model Generation},
  author={Li, Jiahao and Ma, Weijian and Li, Xueyang and Lou, Yunzhong and Zhou, Guichun and Zhou, Xiangdong},
  booktitle={CVPR},
  year={2025}
}
```
