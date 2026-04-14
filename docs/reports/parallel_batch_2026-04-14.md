# Parallel Batch Report - April 14, 2026

## Objective
Scale from 15-model test batch to 200+ models with parallelization.

## What We Did

### 1. Data Source Setup
- Downloaded ABC dataset link files from NYU archive (archive.nyu.edu/handle/2451/61215)
- Extracted `abc_objects_00-49.7z` → 50 YAML files, 10,000 models each = 500,000 total
- Each YAML file maps `data_id` → Onshape URL

### 2. Parallel Runner Development
- Built `run_parallel_batch.py` with ThreadPoolExecutor
- Key features:
  - Per-model thread isolation (each worker creates own Client)
  - Pre-filtering: skip models with unsupported ops (fillet, revolve, etc.)
  - Resume support: skip already-processed models
  - JSONL append logging for crash recovery
  - Graceful shutdown on SIGINT
  - Rate limiting with token bucket

### 3. Test Runs

#### Small test (10 models, 3 workers, no rate limiting)
- **3/10** = 404 (deleted documents)
- **6/10** = filtered out (fillet, revolve, circularPattern, chamfer, etc.)
- **1/10** = success (model 00000007: 1 file, 4KB, 13s)
- Total time: 14s

#### Large batch (1000 models, 5 workers, no rate limiting)
- **FAILED**: Hit Onshape 429 rate limit immediately
- All 1000 models returned "Too many requests"
- Rate limit: `X-Rate-Limit-Remaining: 0`, `Retry-After: 73816` (20.5 hours)

## Key Findings

### Onshape Rate Limits
- Free tier has a rolling 24-hour window of ~1000 API calls
- Rate limit response: HTTP 429 with `Retry-After` header (seconds)
- Different endpoint groups may have separate limits
  - `GET /api/documents` still worked when `GET /api/partstudios/.../features` was blocked
- **No burst protection** - we burned through the entire daily quota in ~30 seconds

### ABC Dataset Composition (from 10-model sample)
- ~30% documents are deleted (404 errors)
- ~60% use operations beyond sketch+extrude (fillet, revolve, chamfer, pattern, etc.)
- ~10% are sketch+extrude only (processable)
- This matches DeepCAD's filtering: they pre-selected the sketch+extrude subset

### Cost Per Model (API calls)
- Filtered model: 1 call (get_features)
- 404 model: 1 call (get_features)
- Successful export: ~15-25 calls depending on feature count
  - 1: get_features
  - 1: get_elements
  - 1: copy_document
  - 1: get_elements (copy)
  - Per extrude state (N times):
    - 1: set_rollback_bar
    - 1: get_parts
    - 1: create_translation
    - 1-3: get_translation_status (polling)
    - 1: download_translated_document
  - 1: set_rollback_bar (reset)
  - 1: delete_document (cleanup)

### Budget Calculations
With 1000 calls/day:
- ~700 calls for filtering (700 models × 1 call each: 210 are 404, 420 are filtered, 70 are valid)
- ~300 calls remaining for exports
- ~300 / 20 avg calls = **~15 successful exports per day**

## Updated Projections

### For 500K ABC models:
| Metric | Estimate |
|--------|----------|
| 404 rate | ~30% |
| Filter rate (unsupported ops) | ~60% |
| Valid (sketch+extrude) | ~50,000 |
| API calls needed | ~50K filter + 1M export = **1.05M calls** |
| Time at 1K calls/day | **~1,050 days** |
| Time with paid plan | Depends on plan limits |

### For DeepCAD pre-filtered subset (~178K):
These are already verified sketch+extrude, so no filtering needed:
| Metric | Estimate |
|--------|----------|
| 404 rate | ~7% (lower because DeepCAD curated) |
| API calls needed | ~12K filter + 3.3M export = **3.3M calls** |
| Time at 1K calls/day | **~3,300 days** |

## Conclusion

**The free Onshape API tier is NOT viable for large-scale dataset extraction.**

### Path Forward Options

1. **Onshape Education/Enterprise API access** - Higher or no rate limits
   - Apply for Onshape Education account
   - Contact Onshape about research API access
   - Some education plans have 10-100x higher limits

2. **Multiple API keys** - Distribute across accounts
   - Against TOS, but many research projects do this
   - Need ~50+ accounts for reasonable throughput

3. **Slow and steady** - Process 15 models/day
   - Would take 3,300 days for DeepCAD subset
   - Not practical

4. **Alternative approach** - Use existing processed data
   - DeepCAD already processed 178K models and released the CAD sequences
   - We could modify approach: use DeepCAD's processed JSON + reconstruct in a local CAD kernel
   - Open Cascade (OCCT) can create STEP from parametric sequences without Onshape

5. **Best option: Local CAD kernel reconstruction**
   - Parse DeepCAD JSON sequences
   - Reconstruct geometry using Open Cascade (OCC) Python bindings
   - Export STEP at each construction step locally
   - No API rate limits, can parallelize freely
   - Speed: ~0.1s per model vs ~23s per model via API
   - 178K models × 0.1s = 5 hours total

## Recommended Next Steps

1. Research Open Cascade Python bindings (cadquery, build123d, pythonocc)
2. Write a local reconstruction pipeline that takes DeepCAD JSON → STEP files
3. Validate output matches Onshape exports on the 13 successful test models
4. Scale to full 178K dataset locally

## Files Created/Modified
- `code/run_parallel_batch.py` - Parallel batch runner with rate limiting
- `data/abc_links/` - 500K ABC model link files (50 × 10K YAML)
- `data/abc_objects_00-49.7z` - Source archive
