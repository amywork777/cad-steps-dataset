# Methodology

## Data Collection Pipeline

### 1. Onshape API Access
- Use onshape-cad-parser as base
- Authenticate via API keys
- Rate limit: ~X requests/minute

### 2. For Each Model
```
1. Load document from Onshape link
2. Get feature list (construction history)
3. For i in range(len(features)):
   a. Set rollback bar to position i
   b. Export current geometry as STEP
   c. Record feature[i] as the operation
   d. Save (step_i.step, operation_i, step_i+1.step)
4. Save metadata as sequence.json
```

### 3. Quality Control
- Skip models with <2 features
- Skip models where rollback fails
- Validate STEP files are non-empty
- Track success/failure rates

## Technical Challenges

1. **Rollback API**: Need to verify Onshape API supports programmatic rollback
2. **Rate Limits**: May need to throttle requests
3. **Dead Links**: Some Onshape docs may be deleted/private
4. **Storage**: 1M models × ~10 steps × ~100KB = ~1TB

## Output Format

```json
{
  "model_id": "00001",
  "source": "deepcad",
  "onshape_url": "https://...",
  "num_steps": 5,
  "steps": [
    {
      "index": 0,
      "geometry_file": "step_00.step",
      "operation_after": {
        "type": "sketch",
        "params": {...}
      }
    },
    ...
  ]
}
```
