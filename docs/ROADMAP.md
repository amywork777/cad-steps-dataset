# Roadmap

## Phase 1: Proof of Concept ✅ COMPLETE (April 14, 2026)

- [x] Create GitHub repo and research documentation
- [x] Port onshape-cad-parser to Python 3
- [x] Build Onshape API rollback + STEP export pipeline
- [x] Test on 15 models via API (86.7% success rate)
- [x] **Discover Onshape API rate limits make large-scale extraction impossible**
  - Free: ~300 calls/day → ~15 models/day
  - Enterprise: 10k calls/year → 454 models/year
  - 178k models = 392+ years
- [x] **Pivot to local pipeline using OpenCascade (CadQuery/OCP)**
- [x] Build local STEP export from DeepCAD JSON
- [x] Build parallel batch runner with checkpointing
- [x] Validate on 200 models (100% success, 1.5s total, 395 STEP files)
- [x] Document everything for paper (README, METHODOLOGY, EXPERIMENT_LOG, PAPER_NOTES)

## Phase 2: Full Dataset Generation — IN PROGRESS

- [x] Download full DeepCAD data (178k models, cad_json.tar.gz)
- [ ] Add 2D sketch wireframe export (export sketch curves as STEP edges/wires)
- [ ] Add inferred constraint annotations to metadata
  - Detect concentric circles (shared center)
  - Detect equal-length lines
  - Detect axis-aligned edges (horizontal/vertical)
  - Detect parallel/perpendicular edges
  - Detect symmetric profiles
- [ ] Run full 178k dataset extraction (~3 min with 8 workers)
- [ ] Quality audit: manually inspect 50 random models
- [ ] Compute dataset statistics (steps/model distribution, size distribution, operation types)
- [ ] Upload to HuggingFace Datasets

## Phase 3: Baseline Experiments

- [ ] Define evaluation metrics (Chamfer distance, IoU, operation prediction accuracy)
- [ ] Experiment 1: Next-state prediction (given S_i + a_i, predict S_{i+1})
- [ ] Experiment 2: Inverse CAD (given S_i and S_{i+1}, predict a_i)
- [ ] Experiment 3: Process reward model (score construction steps)
- [ ] Compare with/without intermediate geometry supervision

## Phase 4: Paper Writing

- [ ] Write methodology section (both approaches, with negative result)
- [ ] Write experiments section with results and analysis
- [ ] Create figures (pipeline diagram, examples, comparisons, statistics)
- [ ] Prepare dataset card for HuggingFace
- [ ] Submit to venue (NeurIPS Datasets & Benchmarks, or workshop at CVPR/ICCV)

## Phase 5: Extensions (Future Work)

- [ ] Add support for Fusion 360 Gallery (8.6K models with richer operations)
- [ ] Process ABC dataset sketch+extrude subset (~50K models)
- [ ] Investigate constraint recovery from resolved geometry
- [ ] Partner with Onshape/PTC for research API access (to extract true constraint data)
- [ ] Extend to operations beyond sketch+extrude (fillet, revolve, pattern)
- [ ] Build a "CAD-Steps Gym" (interactive environment like Fusion 360 Gym)

## Technical Notes

### API vs Local Pipeline Comparison

| Metric | Onshape API | Local (OCC) | Ratio |
|--------|------------|-------------|-------|
| Time/model | 23,000 ms | 7.7 ms | 885x |
| API calls/model | 22 | 0 | ∞ |
| Rate limits | ~300/day (free) | None | ∞ |
| Success rate | 86.7% | 100% | +13pp |
| 178k models | 392+ years | ~3 minutes | ~68M x |
| Dependencies | Internet, API keys | Python, CadQuery | - |
| Data quality | Original B-Rep | Reconstructed | - |
| Constraints | Available (not extracted) | Not available | - |

### Known Limitations of Local Pipeline
- Only supports sketch+extrude operations (same as DeepCAD)
- Geometry is reconstructed from parsed parameters, not original Onshape data
- No parametric constraints (concentric, parallel, etc.) in source data
- Some models may produce degenerate geometry (self-intersecting booleans)
- Sketch-on-face not supported (all sketches are on reference planes)
