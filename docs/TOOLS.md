# Tools & Libraries

## For Data Collection

### Onshape API + Parser
- **onshape-cad-parser**: github.com/ChrisWu1997/onshape-cad-parser
- Python-based parser for extracting CAD construction sequences
- We'll fork and modify to add rollback + STEP export

### CadQuery / OpenCASCADE
- **CadQuery**: github.com/CadQuery/cadquery
- Python library for parametric CAD
- Uses OpenCASCADE (OCCT) kernel
- Can read/write STEP files programmatically

## For Synthetic Data Generation

### ForgeCAD ⭐
- **Website**: forgecad.io
- **GitHub**: github.com/KoStard/ForgeCAD (158 stars)
- **Author**: Ruben Kostandyan (@ruben_kostard, Amazon Applied Scientist)

Code-first parametric CAD in JavaScript/TypeScript:
- Browser IDE + CLI (same engine)
- Uses Manifold geometry kernel (fast WASM)
- Exports to STEP via CadQuery/OpenCascade
- Git-friendly .forge.js files
- **Designed for AI agents** - LLMs can write real CAD models

**Why it's useful for us:**
1. Generate synthetic training data programmatically
2. Each .forge.js script IS the construction sequence
3. Can export intermediate states by modifying scripts
4. AI-friendly means we can use LLMs to generate diverse models

**Example workflow:**
```javascript
// box.forge.js
const width = param("width", 50, {min:10, max:200})
const height = param("height", 30)

const base = sketch().rect(width, height).extrude(10)
const withFillet = base.fillet(2)
```

This script captures the construction sequence directly in code.

### Build123d
- **GitHub**: github.com/gumyr/build123d
- Python CAD library, similar to CadQuery but newer API
- Good for scripted CAD generation

## For Training

### GPU Providers
See [INFRASTRUCTURE.md](./INFRASTRUCTURE.md)

### ML Libraries
- PyTorch / JAX for model training
- HuggingFace Transformers for fine-tuning LLMs
- Diffusers for diffusion-based approaches

## Comparison

| Tool | Language | Kernel | STEP Export | AI-Friendly |
|------|----------|--------|-------------|-------------|
| Onshape | Cloud | Parasolid | ✅ via API | ❌ |
| CadQuery | Python | OCCT | ✅ | ⚠️ |
| ForgeCAD | JS/TS | Manifold+OCCT | ✅ | ✅ |
| Build123d | Python | OCCT | ✅ | ⚠️ |
| OpenSCAD | Custom | CGAL | ❌ (mesh only) | ⚠️ |
