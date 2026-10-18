# Repo Notes

- Starlight v0.39.0 requires sidebar groups with autogeneration to be structured as `{ label: 'Group', items: [{ autogenerate: { directory: 'folder' } }] }`. Providing `autogenerate` directly alongside `label` produces a Starlight config error.
- Running `make check` requires running `make setup` (or `npm ci`) first if `node_modules` / workspace binaries like `prettier` are not installed.
