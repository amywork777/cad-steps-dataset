# CAD-Steps Test Batch Report

**Date:** 2026-04-14 14:24:57
**Total time:** 177.2s (3.0 min)
**Models tested:** 15

## Results Summary

| Status | Count |
|--------|-------|
| ✓ Success | 4 |
| ⊘ Filtered | 11 |
| ✗ Export Failed | 0 |
| ✗ Error | 0 |

## Performance

- Avg time per success: 40.2s
- Min/Max: 13.0s / 56.9s
- Total STEP files generated: 21
- Total output size: 998.0 KB
- Total states exported: 21

## Filter Reasons

- error: 3
- unsupported_types: 8

## Model Details

| ID | Status | Features | States Exported | Time (s) | Size (KB) |
|----|--------|----------|-----------------|----------|-----------|
| 00000352 | ✓ | 12 | 6/12 | 40.7 | 281.2 |
| 00001272 | ✓ | 7 | 5/7 | 50.3 | 360.3 |
| 00001616 | ✓ | 10 | 9/10 | 56.9 | 352.1 |
| 00000000 | ⊘ | - | error:Failed to get features:  | 0.16414356231689453 | - |
| 00000005 | ⊘ | - | error:Failed to get features:  | 0.11124467849731445 | - |
| 00000007 | ✓ | 2 | 1/2 | 13.0 | 4.4 |
| 00000010 | ⊘ | - | error:Failed to get features:  | 0.11882352828979492 | - |
| 00000011 | ⊘ | - | unsupported_types:fillet,cPlan | 0.5517361164093018 | - |
| 00000013 | ⊘ | - | unsupported_types:deleteBodies | 0.9844131469726562 | - |
| 00000014 | ⊘ | - | unsupported_types:fillet,copyP | 1.2672393321990967 | - |
| 00000036 | ⊘ | - | unsupported_types:circularPatt | 1.1944782733917236 | - |
| 00000037 | ⊘ | - | unsupported_types:circularPatt | 1.826817274093628 | - |
| 00000046 | ⊘ | - | unsupported_types:deleteFace,l | 1.2071850299835205 | - |
| 00000047 | ⊘ | - | unsupported_types:circularPatt | 0.39179039001464844 | - |
| 00000035 | ⊘ | - | unsupported_types:circularPatt | 0.379300594329834 | - |

## Full Run Estimates (178k models)

- Success rate: 27%
- Estimated processable models: 47466
- Sequential time: ~1989 hours (83 days)
- 10 parallel workers: ~199 hours (8.3 days)
- 50 parallel workers: ~40 hours (1.7 days)
