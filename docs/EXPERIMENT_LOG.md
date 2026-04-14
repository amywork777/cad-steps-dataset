# Experiment Log

Chronological record of everything attempted in the CAD-Steps project.

---

## 2026-04-14 (Day 1)

### Morning: Project Inception

**Time**: ~12:00pm
**What**: Identified gap in existing CAD datasets. None provide intermediate B-Rep geometry at each construction step.

**Key insight**: Training models on intermediate states (process supervision) outperforms outcome-only supervision in math (PRM, 12%+), robotics (trajectory learning), and code. CAD has the same sequential structure but no dataset captures intermediate geometry.

**Data sources identified**:
- DeepCAD: 178K models with Onshape links and pre-parsed JSON
- ABC Dataset: 1M models (need filtering)
- Fusion 360 Gallery: 8.6K models

**Created**: GitHub repo, README, METHODOLOGY.md, ROADMAP.md, INFRASTRUCTURE.md

---

### Early Afternoon: Onshape API Pipeline (Approach 1)

**Time**: ~12:30pm - 2:30pm
**What**: Built pipeline to extract intermediate STEP files via Onshape API.

**Steps**:
1. Ported `onshape-cad-parser` (github.com/ChrisWu1997/onshape-cad-parser) from Python 2 to Python 3
2. Added HMAC-based API authentication
3. Implemented feature tree rollback: set rollback bar to each feature position
4. Added STEP export at each state via Onshape's translation API
5. Built parallel batch runner with ThreadPoolExecutor

**API Pipeline Per Model** (~22 API calls):
1. GET features list (1 call)
2. Copy document to avoid modifying original (3 calls)
3. For each extrude state (N times):
   - SET rollback bar (1 call)
   - GET parts list (1 call)
   - POST create translation to STEP (1 call)
   - GET translation status, poll until done (1-3 calls)
   - GET download translated file (1 call)
4. Reset rollback bar (1 call)
5. DELETE copied document (1 call)

---

### Afternoon: First Test Batches

**Time**: ~2:30pm - 3:00pm

**Test Batch 1 (15 random ABC models, 3 workers)**:
- 3/15 = 404 (deleted documents)
- 8/15 = filtered (unsupported ops: fillet, revolve, circularPattern, chamfer)
- 4/15 = succeeded
- Success rate: 27% overall, but 57% of reachable docs
- Average time per successful model: 40.2s
- Total STEP files: 21

**Test Batch 2 (15 DeepCAD-verified models, 3 workers)**:
- 2/15 = 404 errors
- 0/15 = filtered (all pre-verified sketch+extrude)
- 13/15 = succeeded
- Success rate: 86.7% (93% of reachable docs)
- Average time per successful model: 23s
- Total STEP files: 38

**Learning**: DeepCAD pre-filtered models have much higher success rate than random ABC models.

---

### 3:00pm: RATE LIMIT DISASTER

**Time**: ~3:00pm
**What**: Attempted 1000-model batch. Immediately hit Onshape rate limits.

**What happened**:
- Launched 1000 models with 5 workers, no rate limiting
- Burned through entire daily API quota in ~30 seconds
- ALL 1000 models returned HTTP 429 "Too Many Requests"
- Response headers: `Retry-After: 73816` (20.5 hours), `X-Rate-Limit-Remaining: 0`

**Rate Limit Analysis**:

| Plan | Annual Calls | Models/Year (at 22 calls each) | Years for 178K |
|------|-------------|-------------------------------|----------------|
| Free | ~300/day? | ~15/day | ~32 years |
| Standard | 2,500/year | 113/year | 1,576 years |
| Professional | 5,000/year | 227/year | 785 years |
| Enterprise | 10,000/year | 454/year | **392 years** |

**ToS concern**: "using the API to scrape or data mine the Onshape Public Documents is prohibited"

**Conclusion**: Onshape API extraction is fundamentally impossible at scale. Even the most expensive plan would take centuries.

**Report written**: `docs/reports/rate_limit_analysis_2026-04-14.md`

---

### 3:30pm: THE PIVOT

**Time**: ~3:30pm
**What**: Pivoted to local reconstruction using OpenCascade.

**Key realization**: DeepCAD already parsed all 178K models into JSON with full parametric data (sketch curves, extrude params, boolean operations). We don't need Onshape at all. We can replay the construction sequence locally using any CAD kernel that supports STEP export.

**Built `local_export.py`**:
- Uses OCP (OpenCascade Python bindings via CadQuery)
- Reads DeepCAD JSON, creates CADSequence objects
- For each extrude operation:
  - Creates sketch face from profile curves (Line, Circle, Arc)
  - Extrudes to create solid body
  - Applies boolean (Fuse/Cut/Common) with accumulated body
  - Exports STEP at each intermediate state
- Saves metadata.json with operation details

**Adapted from**: DeepCAD's `cadlib/visualize.py`, replacing pythonocc (OCC.Core) with OCP

---

### 4:00pm: First Local Test

**Time**: ~4:00pm
**What**: Tested local pipeline on 5 models.

**Result**: All 5 succeeded. Average time: ~26ms per model.
**vs API**: 885x faster (7.7ms effective vs 23,000ms per model)

---

### 4:30pm: 200-Model Batch

**Time**: ~4:30pm
**What**: Full 200-model batch with 8 parallel workers.

**Built `run_local_batch.py`**:
- ProcessPoolExecutor (not Thread, to avoid GIL)
- Resume support: checks for existing metadata.json
- Progress reporting every 50 models
- Batch results saved to JSON

**Result**:

| Metric | Value |
|--------|-------|
| Models | 200 |
| Success | 200 (100%) |
| Failed | 0 |
| STEP files | 395 |
| Total size | 32.8 MB |
| Total time | 1.5 seconds |
| Avg time/model | 7.7 ms |

**Full dataset projections (178K models)**:
- 8 workers: ~3 minutes
- Estimated STEP files: ~352K
- Estimated size: ~29 GB

---

### Late Afternoon: Documentation + Push

**Time**: ~4:45pm
**What**: Committed all code, updated documentation, pushed to GitHub.

**Commits**:
- `c8579c4`: Add local STEP export pipeline (no API needed)
- `d18cd59`: feat: local STEP export pipeline using OpenCascade
- `df99dd8`: Add parallel local batch runner (200 models in 1.5s)
- `48b111a`: feat: parallel batch runner, local reconstruction pipeline, updated README

---

## Comparison: Approach 1 vs Approach 2

| Metric | Onshape API | Local (OpenCascade) |
|--------|-------------|---------------------|
| Time per model | ~23,000 ms | ~7.7 ms |
| Speedup | 1x | **885x** |
| API calls/model | ~22 | 0 |
| Rate limits | ~300/day (free) | None |
| Cost | Paid plans needed | Free |
| 178K models time | 392+ years | ~3 minutes |
| Dependencies | Internet, Onshape account | Python, CadQuery |
| Data quality | Original Onshape B-Rep | Reconstructed from parsed JSON |
| Success rate | 86.7% (DeepCAD) | 100% |
| Constraints data | Available via API (not extracted) | Not available in JSON |

---

## Next Steps (as of end of day 1)

1. ✅ Run full 178K dataset (~3 min)
2. Add 2D sketch wireframe export (STEP with curves only, no extrusion)
3. Investigate constraint inference from sketch geometry
4. Quality validation (compare subset with Onshape exports)
5. Upload to HuggingFace Datasets
6. Write paper methodology section
