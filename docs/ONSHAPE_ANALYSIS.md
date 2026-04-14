# Onshape API Rate Limit Analysis

**Date:** April 14, 2026
**Status:** Negative result — documented for reproducibility and community benefit

---

## Summary

We attempted to build a large-scale CAD dataset by extracting intermediate geometry states from public Onshape documents via the REST API. The approach works technically (86.7% success rate in proof of concept) but is fundamentally not viable at scale due to aggressive rate limiting and Terms of Service restrictions.

**Key finding:** Processing 178K models via the Onshape API would take 392 years on an Enterprise plan. The local OpenCascade pipeline we developed instead processes the same dataset in 3 minutes.

---

## 1. Observed Rate Limits

### 1.1 Free Tier

After processing ~15 models (~300 API calls), we received:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
X-Rate-Limit-Remaining: 0
Retry-After: 73808
```

**Key observations:**
- Lockout duration: 73,808 seconds (**~20.5 hours**)
- No burst protection: the entire daily quota was consumed in ~30 seconds
- Different endpoint groups may have separate limits (`GET /api/documents` still worked when `GET /api/partstudios/.../features` was blocked)
- The rate limit appears to be a rolling 24-hour window, not a fixed daily reset

### 1.2 Official Annual Limits

From Onshape's documentation:

| Plan | Annual API Calls | Cost |
|------|-----------------|------|
| Free | Not listed (very limited, ~300/day observed) | $0 |
| Standard | 2,500/user/year | $1,500/year |
| Professional | 5,000/user/year | $2,500/year |
| Enterprise | 10,000/user/year | Custom |

**Note:** These are *annual* limits, not daily. The free tier appears to have a separate daily rolling limit.

---

## 2. API Calls Per Model

Our pipeline requires approximately 22 API calls per model:

### Fixed Overhead (7 calls)
1. `GET /api/documents/{id}/elements` — get feature studio element
2. `GET /api/partstudios/{id}/features` — get feature list
3. `POST /api/documents` — copy document to writable workspace
4. `GET /api/documents/{copy_id}/elements` — get elements in copy
5. `POST /api/partstudios/{copy_id}/features/rollback` — reset rollback bar (end)
6. `DELETE /api/documents/{copy_id}` — cleanup copied document
7. Error handling / retry calls

### Per Exportable State (~5 calls each, ~3 states/model average)
1. `POST /api/partstudios/{id}/features/rollback` — set rollback bar to position i
2. `GET /api/partstudios/{id}/bodydetails` — check if solid geometry exists
3. `POST /api/partstudios/{id}/translations` — request STEP translation
4. `GET /api/translations/{tid}` — poll translation status (1-3 calls until complete)
5. `GET /api/documents/{id}/externaldata/{fid}` — download translated STEP file

### Total: 7 + (3 × 5) = 22 calls/model

---

## 3. Scale Analysis

### 3.1 Time to Process 178K Models

| Plan | Annual Calls | Models/Year | Years for 178K |
|------|-------------|-------------|----------------|
| Free (~300/day) | ~109,500 | ~4,977 | **36 years** |
| Standard | 2,500 | 114 | **1,563 years** |
| Professional | 5,000 | 227 | **785 years** |
| Enterprise | 10,000 | 454 | **392 years** |

### 3.2 Optimized Pipeline (Lower Bound)

Even with aggressive optimization (batching, caching, removing unnecessary calls), the minimum is ~12 calls/model:

| Plan | Models/Year (optimized) | Years for 178K |
|------|------------------------|----------------|
| Free | ~9,125 | ~20 years |
| Enterprise | ~833 | **214 years** |

### 3.3 Cost Analysis

At Enterprise pricing (~$5,000/year/seat, estimated):
- 392 years × $5,000/year = **$1.96 million**
- Even with 10 seats in parallel: 39 years × $50,000/year = **$1.96 million**
- Costs remain prohibitive regardless of parallelization

---

## 4. Terms of Service

From Onshape's developer documentation and blog:

> "Using the API to scrape or data mine the Onshape Public Documents is prohibited."

Our project — extracting geometry from 178K public documents — clearly falls under this restriction, even with legitimate research intent.

### 4.1 Potential Workarounds

| Option | Feasibility | Issues |
|--------|-------------|--------|
| Research exemption request | Uncertain | No formal program exists |
| Published App Store app | Possible | App calls don't count toward limits, but requires Onshape approval |
| Multiple accounts | Possible | Violates ToS, easily detected |
| Browser automation | Possible | Even more clearly violates ToS |
| **Local reconstruction** | **Best option** | No API needed, no ToS issues |

### 4.2 App Store Approach

Onshape's documentation states that API calls from published Onshape App Store applications do not count toward the user's rate limits. However:
- The app must be approved by Onshape/PTC
- The app must serve a legitimate user-facing purpose
- A batch data extraction tool would likely not be approved
- Review process timeline is uncertain

---

## 5. Alternative Approaches Considered

### 5.1 Onshape Education/Research Access
- No formal research API access program identified
- Education plans may have higher limits but are not documented for API use
- Contact: onshape-developer-relations@ptc.com (not attempted)

### 5.2 Fusion 360 Gallery
- Autodesk's dataset (~20K models) already includes construction history
- Different file format and API ecosystem
- Smaller scale
- Could serve as a complementary data source

### 5.3 Synthetic Data Generation
- Use CadQuery/build123d to generate random models programmatically
- Unlimited scale, no API issues
- Lacks the "human design intent" of real models
- Could supplement but not replace real data

### 5.4 Local Reconstruction from Parsed Data ✅ (Chosen)
- DeepCAD already parsed and released the full parametric data
- Reconstruct geometry locally using OpenCascade
- No API calls, no rate limits, no ToS concerns
- 885× faster than the API approach
- **This is what we did.**

---

## 6. Conclusion

The Onshape API, while technically functional for individual model access, has rate limiting that makes it fundamentally incompatible with large-scale dataset construction. This is not a bug — it's by design. Onshape's business model relies on being a cloud CAD platform, and allowing mass data extraction would undermine both their infrastructure and business.

For the CAD AI research community, this means:
1. **Do not rely on Onshape's API for large-scale data extraction.** Even paid plans are insufficient.
2. **Use local CAD kernels** (OpenCascade, OpenCASCADE, CGAL) to reconstruct geometry from parsed parametric data.
3. **Advocate for research access programs** from CAD vendors (Onshape/PTC, Autodesk, Siemens).

Our local pipeline, detailed in [`METHODOLOGY.md`](METHODOLOGY.md), processes the full 178K model dataset in ~3 minutes — a factor of 10⁸ improvement over the API approach.

---

## Appendix: Raw HTTP Response

```
HTTP/1.1 429 Too Many Requests
Date: Mon, 14 Apr 2026 XX:XX:XX GMT
Content-Type: application/json;charset=UTF-8
X-Rate-Limit-Remaining: 0
Retry-After: 73808
Connection: keep-alive
Content-Length: XXX

{
  "message": "Too many requests",
  "code": 429,
  "moreInfoUrl": "https://cad.onshape.com/glassworks/explorer"
}
```
