# Onshape API Rate Limit Analysis

Date: April 14, 2026

## Critical Finding

The Onshape API has strict rate limits that make large-scale data extraction via API essentially impossible without special arrangements.

## Rate Limits Observed

- After processing ~15 models (test batch), hit 429 (Too Many Requests)
- `Retry-After: 73808` seconds (~20 hours)
- `X-Rate-Limit-Remaining: 0`
- Free plan daily rate limit appears to be very low (likely ~300-500 calls/day)

## Annual API Call Limits (Official)

| Plan | Annual Calls |
|------|-------------|
| Free | Not listed (very limited) |
| Standard | 2,500/user/year |
| Professional | 5,000/user/year |
| Enterprise | 10,000/user/year |

## API Calls Per Model

Each model in our pipeline requires ~22 API calls:
- 7 fixed overhead calls (get features, copy doc, find elements, etc)
- ~3 feature states × 5 calls each (rollback, check parts, translate, poll, download)

## Scale Problem

| Target | API Calls Needed | Years on Enterprise (10k/yr) |
|--------|-----------------|------------------------------|
| 1,000 models | 22,000 | 2.2 years |
| 10,000 models | 220,000 | 22 years |
| 178,000 models (DeepCAD) | 3,916,000 | 392 years |
| 500,000 models (ABC) | 11,000,000 | 1,100 years |

## Terms of Use Concern

From Onshape's blog: "using the API to scrape or data mine the Onshape Public Documents is prohibited."

Our dataset project (extracting geometry from public ABC/DeepCAD documents) likely falls under this restriction.

## Options

### 1. Partner with Onshape/PTC
- Contact onshape-developer-relations@ptc.com
- Publish as an App Store app (API calls from published apps don't count toward limits)
- Request research exemption

### 2. Reduce API calls per model
- Batch operations where possible
- Cache intermediate results
- Skip unnecessary calls (e.g., don't check parts separately from translation)
- Best case: reduce from ~22 to ~12 calls/model. Still not enough.

### 3. Alternative data sources
- Use Fusion 360 Gallery directly (Autodesk provides STEP files in the dataset)
- Use CadQuery or OpenCascade to generate synthetic models programmatically
- Work with the DeepCAD processed JSON data directly (symbolic operations) and reconstruct geometry using CadQuery

### 4. Browser automation (gray area)
- Script the Onshape web UI instead of API
- This avoids API call limits but likely violates ToS even more

### 5. Multiple free accounts (bad idea)
- Violates ToS
- Easily detected

## Recommendation

**Option 3 (alternative data sources) is the most viable path forward.** Specifically:

1. **CadQuery reconstruction**: The DeepCAD dataset already provides parametric operation sequences as JSON. Use CadQuery (Python wrapper for OpenCASCADE) to replay these operations programmatically, exporting STEP at each step. No Onshape API needed.

2. **Fusion 360 Gallery**: Already provides STEP files and construction history.

3. **Synthetic generation**: Use CadQuery/ForgeCAD to generate training data from scratch.

The Onshape API approach works for small-scale validation (~100-500 models) but cannot scale to full dataset generation.
