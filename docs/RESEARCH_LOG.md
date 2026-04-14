# Research Log

## Project Goal
Create the first large-scale dataset of intermediate CAD construction states with operation annotations.

## Key Insight
Training data for CAD AI needs (state, action, next_state) tuples - like robotics trajectory data. Current datasets only have final geometry or symbolic sequences, not intermediate geometry.

## Timeline

### Phase 1: DeepCAD Extraction
- [ ] Fork onshape-cad-parser
- [ ] Add rollback + STEP export functionality
- [ ] Test on 100 models
- [ ] Scale to full 178k

### Phase 2: ABC Dataset
- [ ] Adapt parser for ABC's Onshape links
- [ ] Handle failures/missing models
- [ ] Scale to 1M

### Phase 3: Paper
- [ ] Write methodology
- [ ] Run baseline experiments
- [ ] Submit to venue

---

## Log Entries

### 2026-04-14
- Project initialized
- Identified gap: no intermediate geometry datasets exist
- Sources: DeepCAD (178k), ABC (1M), Fusion 360 Gallery
