# Infrastructure & Compute

## Budget
- $500/month from Vizcom for tech/research

## Compute Strategy

**Don't buy hardware - rent GPUs as needed.**

### For Data Collection (Onshape parsing)
- Lightweight, CPU-only
- Can run on any laptop or cheap cloud VM
- Main bottleneck is API rate limits, not compute

### For Model Training
Rent GPU by the hour:

| Provider | GPU | Price | Notes |
|----------|-----|-------|-------|
| Lambda Labs | A100 80GB | ~$1.50/hr | Reliable, good for long runs |
| RunPod | A100/H100 | $1-3/hr | Flexible, community templates |
| Vast.ai | Various | $0.30-1/hr | Cheapest, spot instances |
| Modal | A100/H100 | ~$1.50/hr | Pay per second, great DX |
| Together.ai | - | Varies | Specifically for fine-tuning LLMs |

### Cost Estimates

**Phase 1: Data collection**
- ~$0 (runs on laptop or free tier VM)

**Phase 2: Training experiments**
- Fine-tuning 7B model: ~10-20 GPU hours = $15-40
- Fine-tuning 14B model: ~30-50 GPU hours = $45-100
- Multiple experiments: budget ~$200/month

**Phase 3: Scaling up**
- Larger runs, ablations: remaining budget

$500/month is plenty for side-project scale research.

## Storage

STEP files are small (~50-500KB each), but at scale:
- 178k models × 10 steps × 100KB = ~178GB (DeepCAD)
- 1M models × 10 steps × 100KB = ~1TB (ABC)

Options:
- **HuggingFace Datasets**: Free hosting for public datasets
- **AWS S3**: ~$23/TB/month
- **Backblaze B2**: ~$5/TB/month

Recommend: HuggingFace for final dataset (free, discoverable)

## Development Setup

Use Mac for:
- Code development
- Running Onshape parser scripts
- Testing locally

Use rented GPU for:
- Training runs
- Large batch inference

## Services Needed

1. **Onshape API** - Free tier should work
2. **HuggingFace** - Free for public datasets
3. **GPU provider** - Lambda/RunPod/Modal account
4. **GitHub** - Already set up
