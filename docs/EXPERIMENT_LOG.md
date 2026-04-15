# Experiment Log

Chronological log of everything attempted in the CAD-Steps project, including failures. This document is intended to support a research paper and should contain enough detail to reproduce results.

---

## 2026-04-14 ~12:00pm — Project Initialization

**Goal**: Create a dataset of intermediate CAD construction states (geometry at every step, not just final).

**Motivation**: Intermediate supervision outperforms outcome-only supervision across ML domains (math PRMs, robotics trajectory learning, code execution traces). CAD has the same sequential structure but no existing dataset captures intermediate geometry.

**Data sources identified**:
- DeepCAD: 178,238 models, pre-filtered for sketch+extrude, JSON sequences available
- ABC Dataset: ~1M models on Onshape, but ~60% use unsupported operations
- Fusion 360 Gallery: 8,625 models with richer operations

**Initial plan**: Use Onshape API to rollback feature trees and export STEP at each position.

**Artifacts**: Created GitHub repo (github.com/amywork777/cad-steps-dataset), README, METHODOLOGY, ROADMAP, INFRASTRUCTURE docs.

---

## 2026-04-14 ~12:30pm — Onshape API Setup

**What we did**: Attempted to generate Onshape API keys for amzyst@gmail.com account.

**Problem**: Developer Portal requires accepting API agreement, then navigating to account settings to create API keys. Browser automation was flaky; the account settings pages kept hanging or rendering blank.

**Resolution**: Eventually got API keys generated. Set up credentials in code/creds.json.

---

## 2026-04-14 ~1:00pm — Onshape Parser Port (Python 3)

**What we did**: Ported github.com/ChrisWu1997/onshape-cad-parser from Python 2 to Python 3.

**Changes required**:
- Updated urllib2 → urllib, httplib → http.client, print statements → functions
- Fixed HMAC authentication (string vs bytes issues)
- Updated API client for current Onshape REST API endpoints
- Added rollback functionality (set_rollback_bar API call)
- Added STEP export at each rollback position

**Result**: Working Python 3 Onshape API client with rollback + STEP export capability.

**Files**: code/onshape_api/, code/export_steps.py

---

## 2026-04-14 ~1:30pm — First Successful Export (1 model)

**What we did**: Tested the rollback pipeline on a single DeepCAD model.

**Pipeline**: 
1. Copy document (to avoid modifying original)
2. Get feature list
3. For each feature: set rollback bar → check for parts → translate to STEP → download
4. Reset rollback bar, delete copy

**Result**: Successfully exported intermediate STEP files for model 00000007 (1 feature, 1 STEP file, 4 KB, 13 seconds).

---

## 2026-04-14 ~2:00pm — Test Batch (15 models via Onshape API)

**What we did**: Ran the export pipeline on 15 models from DeepCAD.

**Results**:
- 4/15 succeeded (26.7% raw success rate)
- 11/15 filtered out: 3 errors (404/deleted docs), 8 unsupported operations (fillet, revolve, circularPattern, chamfer, etc.)
- Of the 4 that could be processed: 4/4 = 100% success
- 21 STEP files generated, 998 KB total
- Average time: 40.2s per successful model (min 13s, max 57s)
- Average 5.25 states per successful model

**Learning**: Raw ABC links contain many models with unsupported operations. DeepCAD's pre-filtering is essential.

---

## 2026-04-14 ~2:30pm — DeepCAD-Verified Batch Test

**What we did**: Used links verified to be in the DeepCAD dataset (known sketch+extrude only).

**Results**:
- 13/15 succeeded (86.7% success rate)
- 2 failures were API errors / document access issues
- Average 23s per model
- Average 2.5 exportable states per model

**Learning**: Pre-filtered DeepCAD models have much higher success rates than random ABC models.

---

## 2026-04-14 ~3:00pm — RATE LIMIT WALL (Critical Finding)

**What we did**: Attempted to scale to 1000 models with 5 parallel workers.

**Result**: HTTP 429 (Too Many Requests) after ~300 API calls (~15 models).
- `Retry-After: 73808` seconds (**~20 hours**)
- `X-Rate-Limit-Remaining: 0`
- All remaining models in the batch returned 429 immediately

**Investigation**:
- Free plan: daily rolling limit of ~300-500 calls
- Standard plan: 2,500 calls/year
- Professional plan: 5,000 calls/year
- Enterprise plan: 10,000 calls/year
- Each model requires ~22 API calls (7 overhead + ~5 per feature state)

**Scale analysis**:

| Target | API Calls | Years on Enterprise (10k/yr) |
|--------|-----------|------------------------------|
| 178K models (DeepCAD) | 3.9M | **392 years** |
| 500K models (ABC) | 11M | **1,100 years** |

**Additional blocker**: Onshape ToS states "using the API to scrape or data mine the Onshape Public Documents is prohibited."

**Conclusion**: The Onshape API approach is fundamentally unscalable for dataset-size extraction.

**Report**: docs/reports/rate_limit_analysis_2026-04-14.md

---

## 2026-04-14 ~3:30pm — THE PIVOT: Local OpenCascade Pipeline

**Insight**: DeepCAD already provides pre-parsed JSON with the full construction sequence (sketch coordinates, extrude parameters, boolean operations). We don't need Onshape at all. We can replay these sequences locally using OpenCascade.

**What we built**: `code/local_export.py`
- Parses DeepCAD JSON (CADSequence objects)
- Creates OCC geometry: sketch curves → face → prism → boolean
- Exports STEP at each intermediate step
- Uses OCP (CadQuery's OpenCascade bindings), NOT pythonocc

**Key code path**:
1. `CADSequence.from_dict(json_data)` → parse JSON into structured objects
2. For each extrude operation:
   - `create_by_extrude()` → sketch profile face → BRepPrimAPI_MakePrism → solid
   - Apply boolean: BRepAlgoAPI_Fuse (join), BRepAlgoAPI_Cut (cut), BRepAlgoAPI_Common (intersect)
   - `write_step(body, path)` → STEPControl_Writer → .step file
3. Save metadata.json with operation details

---

## 2026-04-14 ~4:00pm — First Local Test (5 models)

**Result**: All 5 models succeeded. Average ~26ms per model.

**Comparison with Onshape API**:
- Speed: 26ms vs 23,000ms per model (**885x faster**)
- API calls: 0 vs 22 per model
- Rate limits: none vs 300/day
- Internet: not required vs required

---

## 2026-04-14 ~4:30pm — 200-Model Batch (Local Pipeline)

**What we did**: Built parallel batch runner (`code/run_local_batch.py`) with ProcessPoolExecutor.

**Results**:
- **200/200 succeeded (100% success rate)**
- 395 STEP files generated
- 32.8 MB total output
- 1.5 seconds total time with 8 workers
- 7.7ms per model effective time

**Full dataset projections**:
- 178K models: ~3 minutes with 8 workers
- ~352K STEP files
- ~29 GB

**Files**: code/run_local_batch.py, data/cad_steps_output/batch_results.json

---

## 2026-04-14 ~4:45pm — Documentation Sprint (This Session)

**What we're doing**: Creating comprehensive documentation for a research paper.

**Updates**:
- Rewritten README.md with research-quality content
- Created docs/PAPER_NOTES.md with related work and experiment ideas
- Created docs/EXPERIMENT_LOG.md (this file)
- Updated docs/METHODOLOGY.md with both approaches
- Updated docs/ROADMAP.md with current status

**Key discovery during documentation**: DeepCAD's JSON does NOT contain parametric constraints (concentric, parallel, equal-length, etc.). Only resolved geometry coordinates are stored. This is a significant limitation for the dataset and paper, but also an opportunity for future work.

---

## Summary of Key Metrics

| Approach | Models/day | Success Rate | Time/Model | API Calls |
|----------|-----------|-------------|------------|-----------|
| Onshape API (free) | ~15 | 87% | 23s | 22 |
| Onshape API (Enterprise) | ~1.2 | 87% | 23s | 22 |
| Local OCC (sequential) | ~4.7M | 100% | 7.7ms | 0 |
| Local OCC (8 workers) | ~37M | 100% | 7.7ms | 0 |
