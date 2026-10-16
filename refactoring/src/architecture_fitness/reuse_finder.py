"""Reuse candidate finder using AST parsing, symbol indexing, and token heuristics."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pathspec

from .config import FitnessConfig
from .models import ReuseCandidate


class ReuseFinder:
    def __init__(self, config: Optional[FitnessConfig] = None):
        self.config = config or FitnessConfig()

    def _tokenize(self, text: str) -> Set[str]:
        # Split camelCase, snake_case, and non-alphanumeric
        words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|\d+", text)
        return {w.lower() for w in words if len(w) > 2}

    def _extract_python_symbols(self, file_path: Path, root: Path) -> List[Dict[str, Any]]:
        symbols: List[Dict[str, Any]] = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            tree = ast.parse(content, filename=str(file_path))
            rel_path = file_path.relative_to(root).as_posix()

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node)
                    args = [a.arg for a in node.args.args]
                    symbols.append({
                        "name": node.name,
                        "kind": "function",
                        "file_path": rel_path,
                        "line_number": node.lineno,
                        "signature": f"{node.name}({', '.join(args)})",
                        "docstring": doc,
                        "tokens": self._tokenize(node.name) | (self._tokenize(doc) if doc else set()) | {a.lower() for a in args},
                    })
                elif isinstance(node, ast.ClassDef):
                    doc = ast.get_docstring(node)
                    symbols.append({
                        "name": node.name,
                        "kind": "class",
                        "file_path": rel_path,
                        "line_number": node.lineno,
                        "signature": f"class {node.name}",
                        "docstring": doc,
                        "tokens": self._tokenize(node.name) | (self._tokenize(doc) if doc else set()),
                    })
        except Exception:
            pass
        return symbols

    def _extract_generic_symbols(self, file_path: Path, root: Path) -> List[Dict[str, Any]]:
        """Fallback regex-based symbol extractor for JS/TS/Rust/Go."""
        symbols: List[Dict[str, Any]] = []
        rel_path = file_path.relative_to(root).as_posix()
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            for idx, line in enumerate(lines, 1):
                # Functions in JS/TS: function foo(...) or const foo = (...) => or foo(...) {
                m_fn = re.search(r"(?:function\s+|const\s+|let\s+|fn\s+|func\s+)([A-Za-z0-9_]+)\s*(?:=\s*)?(?:\((.*?)\)|\{)", line)
                if m_fn:
                    name = m_fn.group(1)
                    params = m_fn.group(2) or ""
                    symbols.append({
                        "name": name,
                        "kind": "function",
                        "file_path": rel_path,
                        "line_number": idx,
                        "signature": f"{name}({params.strip()})",
                        "docstring": None,
                        "tokens": self._tokenize(name) | self._tokenize(params),
                    })
        except Exception:
            pass
        return symbols

    def find_candidates(
        self,
        repo_path: Path | str,
        query: str,
        context: Optional[str] = None,
        top_n: int = 5,
    ) -> List[ReuseCandidate]:
        root = Path(repo_path).resolve()
        spec = pathspec.PathSpec.from_lines("gitignore", self.config.exclude_paths)

        gitignore = root / ".gitignore"
        gi_spec = None
        if gitignore.exists():
            try:
                with open(gitignore, "r", encoding="utf-8") as f:
                    gi_spec = pathspec.PathSpec.from_lines("gitignore", f.readlines())
            except Exception:
                pass

        query_tokens = self._tokenize(query)
        if context:
            query_tokens |= self._tokenize(context)

        if not query_tokens:
            return []

        all_symbols: List[Dict[str, Any]] = []
        supported_suffixes = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go"}

        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = Path(dirpath).relative_to(root).as_posix()
            if rel_dir != "." and (
                spec.match_file(rel_dir)
                or spec.match_file(f"{rel_dir}/")
                or (gi_spec and (gi_spec.match_file(rel_dir) or gi_spec.match_file(f"{rel_dir}/")))
            ):
                dirnames.clear()
                continue

            dirnames[:] = [
                d for d in dirnames
                if not (
                    spec.match_file(f"{rel_dir}/{d}" if rel_dir != "." else d)
                    or spec.match_file(f"{rel_dir}/{d}/" if rel_dir != "." else f"{d}/")
                    or (gi_spec and (gi_spec.match_file(f"{rel_dir}/{d}" if rel_dir != "." else d) or gi_spec.match_file(f"{rel_dir}/{d}/" if rel_dir != "." else f"{d}/")))
                )
            ]

            for fn in filenames:
                p = Path(dirpath) / fn
                if p.suffix not in supported_suffixes:
                    continue
                rel = p.relative_to(root).as_posix()
                if spec.match_file(rel) or (gi_spec and gi_spec.match_file(rel)):
                    continue

                if p.suffix in [".py", ".pyi"]:
                    all_symbols.extend(self._extract_python_symbols(p, root))
                elif p.suffix in [".js", ".jsx", ".ts", ".tsx", ".rs", ".go"]:
                    all_symbols.extend(self._extract_generic_symbols(p, root))

        scored_candidates: List[Tuple[float, Dict[str, Any], str]] = []

        query_lower = query.lower()

        for sym in all_symbols:
            sym_tokens = sym["tokens"]
            if not sym_tokens:
                continue

            # Overlap score
            intersection = query_tokens & sym_tokens
            if not intersection:
                continue

            jaccard = len(intersection) / len(query_tokens | sym_tokens)
            exact_bonus = 0.5 if sym["name"].lower() in query_lower or query_lower in sym["name"].lower() else 0.0
            
            score = round(min(jaccard * 1.5 + exact_bonus, 1.0), 2)
            if score > 0.15:
                matching_words = ", ".join(sorted(list(intersection)))
                reason = f"Shares relevant vocabulary: {matching_words}"
                if exact_bonus > 0:
                    reason += f" (name '{sym['name']}' closely matches query)"
                scored_candidates.append((score, sym, reason))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        results: List[ReuseCandidate] = []
        for score, sym, reason in scored_candidates[:top_n]:
            results.append(ReuseCandidate(
                symbol_name=sym["name"],
                kind=sym["kind"],
                file_path=sym["file_path"],
                line_number=sym["line_number"],
                signature=sym.get("signature"),
                docstring=sym.get("docstring"),
                relevance_reason=reason,
                evidence=f"Matched tokens in {sym['file_path']} line {sym['line_number']}",
                confidence=score,
            ))

        return results
