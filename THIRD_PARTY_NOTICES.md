# Third-party notices

The development tools download rendering inputs from
[NetNewsWire](https://github.com/Ranchero-Software/NetNewsWire), release `mac-7.1.3`,
commit `f2daca0f24f29c08d9cb16e1bdc56293fd6fe286`, into the ignored
`.cache/netnewswire/` directory. The `[tool.nnw-theme.netnewswire]` configuration in
`pyproject.toml` records and verifies the SHA-256 of every file, including
NetNewsWire’s MIT license. The cached inputs are not committed or included in theme
release archives.

The independently written starter theme files under `Starter.nnwtheme/` are provided
under the Zero-Clause BSD license in that directory.
