# Roadmap

## Phase 1: Setup & Proof of Concept (Week 1-2) ✅ COMPLETE
- [x] Create GitHub repo
- [x] Document research motivation
- [x] Plan infrastructure
- [x] Get Onshape API credentials
- [x] Fork onshape-cad-parser
- [x] Test rollback + STEP export on 1 model (Onshape API)
- [x] Test on 15 models (Onshape API) - 86.7% success
- [x] **CRITICAL FINDING: Onshape API rate limits make large-scale extraction impossible**
  - Free plan: ~300 API calls hit the rate limit
  - Rate limit lockout: 20+ hours
  - Even Enterprise (10k/year) = only ~454 models/year
  - 178k models would require 392+ years
  - ToS prohibits data mining public documents
- [x] **PIVOT: Built local pipeline using OpenCascade (CadQuery/OCP)**
  - Uses DeepCAD's pre-parsed JSON data (178k models)
  - Replays construction sequences locally with OCC
  - Exports STEP at each intermediate state
  - 100% success rate on 100-model batch
  - 0.026 seconds/model (vs ~23 seconds on Onshape API)
  - Full 178k dataset: ~1.3 hours sequential, ~8 min with 10 workers
  - Estimated dataset size: ~39 GB

## Phase 2: Full DeepCAD Extraction (Week 3-4) - IN PROGRESS
- [x] Download full DeepCAD data (178k models, cad_json.tar.gz)
- [x] Build parallel local pipeline (run_parallel_local.py)
- [ ] Run on full 178k DeepCAD dataset
- [ ] Handle failures, log statistics
- [ ] Validate output quality (compare with Onshape exports)
- [ ] Upload to HuggingFace Datasets

## Phase 3: Baseline Experiments (Week 5-8)
- [ ] Define evaluation metrics
- [ ] Train simple baseline (operation prediction from geometry)
- [ ] Compare with/without intermediate geometry
- [ ] Document results

## Phase 4: Paper (Week 9-12)
- [ ] Write methodology section
- [ ] Write experiments section
- [ ] Create figures
- [ ] Submit to venue (CVPR/ICCV workshop, or arxiv)

## Phase 5: Scale to ABC (Optional)
- [ ] Download full ABC dataset links (1M models)
- [ ] Adapt pipeline for ABC models (need to filter for sketch+extrude)
- [ ] Run at scale
- [ ] Release v2 of dataset

## Technical Notes

### API vs Local Pipeline Comparison

| Metric | Onshape API | Local (OCC) |
|--------|------------|-------------|
| Time/model | ~23s | ~0.026s |
| API calls | ~22/model | 0 |
| Rate limits | ~300/day (free) | None |
| Cost | Paid plans needed | Free |
| 178k models | 392+ years | ~1.3 hours |
| Dependencies | Internet, Onshape account | Python, CadQuery |
| Data quality | Original geometry | Reconstructed from parsed JSON |

### Known Limitations of Local Pipeline
- Only supports sketch+extrude operations (same as DeepCAD)
- Geometry is reconstructed from parsed parameters, not original Onshape data
- Some models fail on boolean operations (e.g., self-intersecting geometry)
- Some models have 0 exportable states (empty operations list)
