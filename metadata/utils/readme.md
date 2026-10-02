# Metadata utilities

These tools create and serve STAC metadata. They are grouped by data type:

| Folder | What it does |
| --- | --- |
| [`models/`](models/) | Creates standalone HEC-HMS and HEC-RAS Items; adds derived Parquet assets, version details, and source lineage. |
| [`terrain/`](terrain/) | Builds STAC metadata for terrain data. |
| [`dams/`](dams/README.md) | Builds an Allegheny watershed dam Collection with one Item and GeoJSON asset per dam. |

## Preview a catalog locally

[`serve_cors.py`](serve_cors.py) is a development HTTP server with CORS
enabled. It needs only Python's standard library. To install it on your PATH:

```bash
install -m 755 metadata/utils/serve_cors.py ~/.local/bin/serve-cors
cd /path/to/catalog
serve-cors
```

The server serves the current directory at `http://127.0.0.1:8000`. Ensure
`~/.local/bin` is on your PATH, or invoke the script directly.

| Option | Example | Purpose |
| --- | --- | --- |
| Port | `serve-cors 8080` | Use a port other than 8000. |
| Directory | `serve-cors --directory /path/to/catalog` | Serve a directory without changing into it. |
| Network access | `serve-cors --bind 0.0.0.0` | Allow other hosts to connect. |

STAC metadata can then be previewed in a browser via the localhost URL with a
STAC viewer:
- [STAC Browser](https://browser.moregeo.it/)
- [Portolan Browser](https://browser.portolan-sdi.org/)

**Caution:** Binding to `0.0.0.0` exposes the served files to the network. Use
this development server only on a trusted network, not in production.
