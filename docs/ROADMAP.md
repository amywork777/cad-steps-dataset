# Roadmap

## Phase 1: Setup and Proof of Concept ✅ COMPLETE (Week 1)

- [x] Create GitHub repository and documentation structure
- [x] Document research motivation (intermediate supervision from math/robotics)
- [x] Plan infrastructure (compute budget, storage, GPU rental)
- [x] Obtain Onshape API credentials
- [x] Port `onshape-cad-parser` from Python 2 to Python 3
- [x] Build Onshape API pipeline (copy → rollback → STEP export → cleanup)
- [x] Test on 15 DeepCAD models via Onshape API
  - 86.7% success rate (13/15), avg 23s/model, 21 STEP files
- [x] Discover rate limit wall (HTTP 429 after ~300 calls, 20-hour lockout)
- [x] Full rate limit analysis (Enterprise plan = 392 years for 178K models)
- [x] Document Onshape API negative result

## Phase 2: Local Pipeline Development ✅ COMPLETE (Week 1-2)

- [x] Download DeepCAD pre-parsed JSON data (178K models, 185 MB compressed)
- [x] Build local reconstruction pipeline using OpenCascade (CadQuery/OCP)
  - Sketch → Face → Extrude → Boolean → STEP export at each step
- [x] Validate on 200-model batch
  - 100% success rate, 395 STEP files, 32.8 MB, 1.5 seconds (8 workers)
- [x] Implement parallelization with ProcessPoolExecutor
- [x] Add checkpointing (skip already-processed models)
- [x] Performance benchmarking: 7.7 ms/model (885× faster than Onshape API)
- [x] Full dataset projections: ~3 minutes with 8 workers, ~29 GB, ~352K files

## Phase 3: Full Dataset Extraction — IN PROGRESS (Week 3)

- [x] Download full DeepCAD data (178K models across 100 bucket directories)
- [x] Validate local pipeline at 200-model scale
- [ ] Run on full 178K DeepCAD dataset (~3 minutes with 8 workers)
- [ ] Compute dataset statistics (operation distributions, file sizes, failure analysis)
- [ ] Quality validation (compare local exports with Onshape API exports)
- [ ] Upload to HuggingFace Datasets (public, CC BY 4.0)

## Phase 4: Paper and Documentation (Week 4-6)

- [x] Draft paper outline (`docs/PAPER_OUTLINE.md`)
- [x] Write detailed methodology (`docs/METHODOLOGY.md`)
- [x] Document Onshape analysis as negative result (`docs/ONSHAPE_ANALYSIS.md`)
- [ ] Generate dataset statistics figures (histograms, distributions)
- [ ] Create example visualizations (intermediate state sequences)
- [ ] Write full paper draft (target: arXiv preprint)

## Phase 5: Baseline Experiments (Week 6-10)

- [ ] Define evaluation metrics (Chamfer distance, IoU, operation accuracy)
- [ ] Implement geometry representations (voxelized, point cloud)
- [ ] Train next-state prediction baseline
- [ ] Train operation prediction (inverse modeling) baseline
- [ ] Compare with/without intermediate geometry supervision
- [ ] Ablation studies
- [ ] Document results

## Phase 6: Release and Extension (Week 10-14)

- [ ] Final paper submission (venue TBD: CVPR workshop, ICCV, or arXiv)
- [ ] Release pre-trained baseline models on HuggingFace
- [ ] Extend to Fusion 360 Gallery (~20K models, richer operations)
- [ ] Community engagement (Reddit r/MachineLearning, Twitter, HuggingFace)

---

## Key Metrics

### Pipeline Performance Comparison

| Metric | Onshape API | Local (OCC) | Improvement |
|--------|------------|-------------|-------------|
| Time/model | 23,000 ms | 7.7 ms | 2,987× |
| API calls/model | 22 | 0 | ∞ |
| Rate limited | Yes (20h lockout) | No | — |
| 178K models | 392 years | ~3 minutes | ~10⁸× |
| Dependencies | Internet + API keys | Python + CadQuery | Simpler |
| Cost | Enterprise plan needed | Free | ∞ |

### 200-Model Validation Results

| Metric | Value |
|--------|-------|
| Success rate | 100% (200/200) |
| STEP files generated | 395 |
| Total size | 32.8 MB |
| Wall clock time | 1.54 seconds |
| Workers | 8 |
| Avg files/model | 1.98 |
| Avg size/model | 163.8 KB |

### Full Dataset Projections

| Metric | Estimate |
|--------|----------|
| Total models | 178,238 |
| STEP files | ~352,000 |
| Total size | ~29 GB |
| Processing time (8 workers) | ~3 minutes |
| Processing time (sequential) | ~23 minutes |

---

## Known Limitations

1. **Sketch-and-extrude only**: No fillets, chamfers, revolves, patterns (inherited from DeepCAD)
2. **Reconstructed geometry**: OpenCascade reconstruction, not original Onshape exports
3. **Normalized coordinates**: DeepCAD uses normalized dimensions
4. **Some failure modes**: Degenerate sketches, boolean edge cases (logged in metadata)
