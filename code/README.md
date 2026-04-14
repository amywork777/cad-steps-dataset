# Code

Python 3 port of [onshape-cad-parser](https://github.com/ChrisWu1997/onshape-cad-parser) with new rollback + STEP export functionality.

## Setup

```bash
pip install -r ../requirements.txt
cp creds.json.example creds.json  # then fill in your Onshape API keys
```

## Scripts

- `test_connection.py` - Verify Onshape API credentials and connectivity
- `process.py` - Original parser (ported to Python 3), outputs Fusion360 Gallery format JSON
- `export_steps.py` - **NEW**: Export STEP geometry at each rollback state during CAD construction
- `parser.py` - Feature list parser (sketch + extrude)
- `cad_utils.py` - Geometry utilities

## Modules

- `onshape_api/` - Python 3 port of [onshape-public-apikey](https://github.com/onshape-public/apikey)
  - `client.py` - API client with all original methods + rollback + STEP export
  - `onshape.py` - HMAC authentication and request handling
  - `utils.py` - Logging

## Usage

### Test API connection
```bash
python3 test_connection.py
```

### Run original parser on test examples
```bash
python3 process.py --test
```

### Export STEP at each construction state
```bash
# Single model
python3 export_steps.py --url "https://cad.onshape.com/documents/{did}/w/{wid}/e/{eid}" --output_dir ./output

# Test example
python3 export_steps.py --test
```

## Changes from Original

1. **Python 3**: All code ported from Python 2.7 to Python 3.8+
2. **No git submodule**: Onshape API client is included directly in `onshape_api/`
3. **Rollback API**: New `set_rollback_bar()` method to move the rollback bar programmatically
4. **STEP export**: New `export_step()` method using Onshape's translation API
5. **`export_steps.py`**: New script that combines rollback + export to capture intermediate geometry
