# Methodology

## Research Approach

### Core Insight: Trajectory Data for CAD

Just as robotics uses demonstration trajectories (state → action → next_state) and math reasoning uses step-by-step solutions, CAD construction can be framed as:

```
geometry_n → operation_n → geometry_n+1
```

This framing enables:
1. **Process Reward Models**: Reward correctness at each step, not just final output
2. **Imitation Learning**: Train policies to replicate expert construction sequences
3. **Step-level Verification**: Check each intermediate state, catch errors early

### Why Intermediate Geometry Matters

**Without intermediate geometry (current state):**
- Model sees: `[sketch, extrude, fillet, chamfer]` → final.step
- Can only verify if final output matches target
- No signal about which step went wrong

**With intermediate geometry (our dataset):**
- Model sees: `step_0.step → sketch → step_1.step → extrude → step_2.step → ...`
- Can verify each transition
- Can train reward models on individual operations
- Can do "early stopping" when detecting bad trajectory

### Precedent from Other Domains

**Math (GSM8K, MATH, PRM800K):**
- Human annotators write step-by-step solutions
- Process Reward Models check each reasoning step
- Result: 12%+ improvement over outcome-only supervision

**Robotics (RT-1, RT-2, Diffusion Policy):**
- Teleoperation captures (observation, action, next_observation)
- Imitation learning clones expert trajectories
- Dense supervision at 10-50Hz

**Code (execution traces):**
- Some datasets capture intermediate program states
- Enables debugging and step-through verification

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

## Potential Training Approaches Enabled

1. **Autoregressive generation**: Predict next geometry given current geometry + operation
2. **Inverse modeling**: Predict operation given before/after geometry
3. **Process reward**: Train reward model on (geometry, operation, next_geometry) quality
4. **Diffusion over trajectories**: Generate full construction sequence via denoising
5. **Retrieval-augmented CAD**: Find similar intermediate states from dataset
