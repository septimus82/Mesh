# Versioning Policy

Mesh uses SemVer guarantees only for the public API namespace:

- `engine.public_api.*`

All other modules are internal implementation details and may change without
notice between releases.

## SemVer Rules for `engine.public_api.*`

- **Patch** (`x.y.Z`): bug fixes and internal changes with no breaking public
  API changes.
- **Minor** (`x.Y.z`): additive public API changes (new symbols/wrappers) with
  backwards compatibility.
- **Major** (`X.y.z`): breaking changes to existing public API behavior or
  signatures.

## Public API Version Constants

- `engine.public_api.PUBLIC_API_VERSION`
- `engine.public_api.PUBLIC_API_SEMVER`

These constants identify the current supported public API generation.

