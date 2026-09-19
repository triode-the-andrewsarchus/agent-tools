# Standalone & Generic Agent Skills

This directory contains standalone and cross-agent skills for coding agents (Google Antigravity, OpenAI Codex, etc.) that do not require an active MCP server backend.

## Available Skills

- **`rust-development`**: Best practices for implementing, debugging, and reviewing Rust crates and Cargo workspaces.
- **`rust-doc-formatting`**: Rustdoc styling, layout, API documentation, and doctests following RFC 1574 conventions.
- **`debugging-code`**: Interactive source code debugging via Debug Adapter Protocol (DAP). Set breakpoints, step through code line by line, inspect variable state and call stack using the `dap` CLI (submoduled from [`AlmogBaku/debug-skill`](https://github.com/AlmogBaku/debug-skill)).
- **`lsp-code-analysis`**: Semantic code analysis and navigation via Language Server Protocol (LSP). Jump to definitions, search references/implementations, outline symbols, and safely preview refactorings using the `lsp` CLI (submoduled from [`lsp-client/lsp-skill`](https://github.com/lsp-client/lsp-skill)).

## Cross-Agent Integration

These skills are automatically symlinked into global agent configuration paths:
- Google Antigravity: `~/.gemini/config/skills/`
- OpenAI Codex: `~/.codex/skills/`

To synchronize or update symlinks across all agents:
```bash
./install.py --tool skills --agent all
# or
./install.py --all
```
