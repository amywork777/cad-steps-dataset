# Research Log

## Project

**CAD-Steps**: A Large-Scale Dataset of Intermediate CAD Construction States

**Goal**: Create the first large-scale dataset that captures 3D geometry at every step of a CAD construction sequence, enabling process-supervised learning for CAD AI.

**Key Insight**: Intermediate supervision outperforms outcome-only supervision (proven in math, robotics, code). CAD has the same sequential structure but no existing dataset captures intermediate geometry.

---

## 2026-04-14 — Project Inception

### Morning: Project Setup

- Initialized GitHub repo: `github.com/amywork777/cad-steps-dataset`
- Wrote research motivation connecting to process supervision literature:
  - Lightman et al. 2023: PRMs > ORMs for math (+12% on MATH)
  - RT-1/RT-2: dense trajectory data for robot imitation learning
  - Same principle applies to CAD: `(state, action, next_state)` triples
- Identified data sources: DeepCAD (178K), ABC (1M), Fusion 360 Gallery (20K)
- Created infrastructure plan ($500/mo Vizcom budget)
- Set up 14-week roadmap across 4 phases

### Afternoon: Onshape API Pipeline

- Built working Onshape API pipeline: copy doc → rollback feature tree → export STEP
- Ported onshape-cad-parser from Python 2 to Python 3
- Tested on 15 DeepCAD models:
  - 13/15 succeeded (86.7%)
  - Average 23 seconds/model
  - 21 STEP files, 998 KB total
  - Each model requires ~22 API calls

### Afternoon: Rate Limit Discovery

**CRITICAL FINDING**: Onshape API rate limits make this approach impossible at scale.

- After ~300 API calls: HTTP 429, `Retry-After: 73808` (20 hours)
- Enterprise plan: 10K calls/year = 454 models/year
- 178K models via API = **392 years**
- Even aggressively optimized (12 calls/model) = 214 years
- ToS explicitly prohibits data mining of public documents
- **Decision: Pivot to local reconstruction**

### Evening: Local Pipeline Built

- Realized DeepCAD already has all parametric data as JSON (178K models)
- Built local reconstruction pipeline using OpenCascade (CadQuery/OCP):
  - Parse JSON → sketch → face → extrude → boolean → STEP export
  - Export at each intermediate step (the key innovation)
- 200-model validation batch:
  - **100% success rate** (200/200)
  - 395 STEP files, 32.8 MB
  - 1.5 seconds total (8 workers)
  - 7.7 ms/model effective (vs 23,000 ms via API = 885× faster)
- Full dataset projection: ~3 minutes for 178K models, ~29 GB, ~352K files

### Key Architecture Decisions

1. **Local over API**: Rate limits made this the only viable path
2. **STEP format**: Industry standard, widely supported, preserves exact B-rep geometry
3. **Per-operation granularity**: Export after every extrude, not just every feature group
4. **ProcessPoolExecutor**: Each worker is a separate process (avoids OCC GIL issues)
5. **Checkpointing**: Skip models with existing metadata.json for crash recovery

### Files Created

- `code/local_export.py` — Core reconstruction and STEP export
- `code/run_local_batch.py` — Parallel batch runner
- `code/cadlib/` — DeepCAD's CAD parsing library
- `code/export_steps.py` — Onshape API pipeline (proof of concept)
- `code/run_parallel_batch.py` — Onshape API parallel runner
- `code/onshape_api/` — Onshape REST client (Python 3)
- `docs/METHODOLOGY.md` — Technical methodology
- `docs/ONSHAPE_ANALYSIS.md` — Rate limit analysis (negative result)
- `docs/PAPER_OUTLINE.md` — Draft paper structure
- `docs/ROADMAP.md` — Project timeline
- `docs/INFRASTRUCTURE.md` — Compute and storage planning
- `docs/reports/` — Batch run reports

### Next Steps

1. Run full 178K dataset extraction (~3 minutes)
2. Compute dataset statistics and distributions
3. Quality validation (compare with Onshape exports)
4. Upload to HuggingFace Datasets
5. Write paper

---

## References

- Wu, R., Xiao, C., & Zheng, C. (2021). DeepCAD. *ICCV*. [arXiv:2105.09492](https://arxiv.org/abs/2105.09492)
- Koch, S. et al. (2019). ABC Dataset. *CVPR*.
- Willis, K.D.D. et al. (2021). Fusion 360 Gallery. *SIGGRAPH*. [arXiv:2010.02392](https://arxiv.org/abs/2010.02392)
- Lightman, H. et al. (2023). Let's Verify Step by Step. *ICLR 2024*. [arXiv:2305.20050](https://arxiv.org/abs/2305.20050)
- Xu, X. et al. (2022). SkexGen. *ICML*. [arXiv:2207.04632](https://arxiv.org/abs/2207.04632)
- Guan, Y. et al. (2025). CAD-Coder. *NeurIPS*.
