# Roadmap

## Phase 1: Setup & Proof of Concept (Week 1-2)
- [x] Create GitHub repo
- [x] Document research motivation
- [x] Plan infrastructure
- [ ] Get Onshape API credentials
- [ ] Fork onshape-cad-parser
- [ ] Test rollback + STEP export on 1 model
- [ ] Test on 100 models
- [ ] Estimate success rate and time for full run

## Phase 2: DeepCAD Extraction (Week 3-6)
- [ ] Run parser on full 178k DeepCAD models
- [ ] Handle failures, log statistics
- [ ] Validate output quality
- [ ] Upload to HuggingFace Datasets

## Phase 3: Baseline Experiments (Week 7-10)
- [ ] Define evaluation metrics
- [ ] Train simple baseline (operation prediction)
- [ ] Compare with/without intermediate geometry
- [ ] Document results

## Phase 4: Paper (Week 11-14)
- [ ] Write methodology section
- [ ] Write experiments section
- [ ] Create figures
- [ ] Submit to venue (CVPR/ICCV workshop, or arxiv)

## Phase 5: Scale to ABC (Optional)
- [ ] Adapt parser for ABC's 1M models
- [ ] Run at scale
- [ ] Release v2 of dataset

## Stretch Goals
- [ ] Add Fusion 360 Gallery models
- [ ] Train larger models
- [ ] Release model weights
