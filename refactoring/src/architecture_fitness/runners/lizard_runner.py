"""Runner for Lizard cyclomatic complexity analyzer."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pathspec

from ..config import FitnessConfig
from ..models import FunctionMetric, ToolStatus

try:
    import lizard
    LIZARD_LIB_AVAILABLE = True
except ImportError:
    lizard = None
    LIZARD_LIB_AVAILABLE = False


SUPPORTED_LIZARD_EXTENSIONS = {
    "c", "cpp", "cc", "cxx", "h", "hpp", "java", "cs", "js", "cjs", "mjs",
    "py", "pyw", "m", "mm", "ttcn", "ttcnpp", "rb", "php", "swift", "scala",
    "gd", "go", "lua", "rs", "ts", "f70", "f90", "f95", "f03", "f08", "f",
    "for", "ftn", "fpp", "kt", "kts", "sol", "erl", "hrl", "es", "escript",
    "zig", "tsx", "jsx", "vue", "pl", "pm", "st", "r", "sql", "pks", "pkb",
    "pls", "plb", "pck",
}


class LizardRunner:
    def __init__(self, config: Optional[FitnessConfig] = None):
        self.config = config or FitnessConfig()

    def get_version(self) -> Optional[str]:
        if LIZARD_LIB_AVAILABLE and hasattr(lizard, "version"):
            return lizard.version
        exe = shutil.which("lizard")
        if exe:
            import subprocess
            try:
                out = subprocess.check_output([exe, "--version"], text=True, stderr=subprocess.STDOUT)
                return out.strip()
            except Exception:
                pass
        return None

    def is_available(self) -> bool:
        return LIZARD_LIB_AVAILABLE or shutil.which("lizard") is not None

    def _is_supported_source_file(self, fpath: Path) -> bool:
        """Check if file is a supported source file for Lizard, respecting configured languages and max size."""
        if not fpath.is_file():
            return False
        try:
            # Skip files larger than 2MB to prevent runaway regex tokenization
            if fpath.stat().st_size > 2 * 1024 * 1024:
                return False
        except OSError:
            return False

        if LIZARD_LIB_AVAILABLE:
            reader = lizard.get_reader_for(fpath.name)
            if reader is None:
                return False
            if self.config.languages:
                req_langs = {l.lower() for l in self.config.languages}
                reader_langs = {l.lower() for l in getattr(reader, "language_names", [])}
                if not reader_langs.intersection(req_langs):
                    return False
            return True
        else:
            ext = fpath.suffix.lstrip(".").lower()
            if not ext or ext not in SUPPORTED_LIZARD_EXTENSIONS:
                return False
            if self.config.languages:
                req_langs = {l.lower() for l in self.config.languages}
                if ext not in req_langs:
                    return False
            return True

    def _collect_files(self, repo_path: Path, target_paths: Optional[List[str]] = None) -> List[Path]:
        """Collect source files respecting gitignore and exclude patterns."""
        # Build pathspec from excludes
        spec = pathspec.PathSpec.from_lines("gitignore", self.config.exclude_paths)
        
        # Read .gitignore if present
        gitignore = repo_path / ".gitignore"
        gi_spec = None
        if gitignore.exists():
            try:
                with open(gitignore, "r", encoding="utf-8") as f:
                    gi_spec = pathspec.PathSpec.from_lines("gitignore", f.readlines())
            except Exception:
                pass

        search_roots = [Path(p) if Path(p).is_absolute() else repo_path / p for p in target_paths] if target_paths else [repo_path]

        discovered: List[Path] = []
        for root in search_roots:
            if not root.exists():
                continue
            if root.is_file():
                rel = root.relative_to(repo_path).as_posix()
                if not spec.match_file(rel) and (not gi_spec or not gi_spec.match_file(rel)):
                    if self._is_supported_source_file(root):
                        discovered.append(root)
                continue

            for dirpath, dirnames, filenames in os.walk(root):
                rel_dir = Path(dirpath).relative_to(repo_path).as_posix()
                if rel_dir != "." and (
                    spec.match_file(rel_dir)
                    or spec.match_file(f"{rel_dir}/")
                    or (gi_spec and (gi_spec.match_file(rel_dir) or gi_spec.match_file(f"{rel_dir}/")))
                ):
                    dirnames.clear()
                    continue

                # Prune directory search space to avoid descending into ignored trees
                dirnames[:] = [
                    d for d in dirnames
                    if not (
                        spec.match_file(f"{rel_dir}/{d}" if rel_dir != "." else d)
                        or spec.match_file(f"{rel_dir}/{d}/" if rel_dir != "." else f"{d}/")
                        or (gi_spec and (gi_spec.match_file(f"{rel_dir}/{d}" if rel_dir != "." else d) or gi_spec.match_file(f"{rel_dir}/{d}/" if rel_dir != "." else f"{d}/")))
                    )
                ]

                for fn in filenames:
                    fpath = Path(dirpath) / fn
                    rel_file = fpath.relative_to(repo_path).as_posix()
                    if spec.match_file(rel_file):
                        continue
                    if gi_spec and gi_spec.match_file(rel_file):
                        continue
                    if not self._is_supported_source_file(fpath):
                        continue
                    discovered.append(fpath)

        return discovered

    def run(self, repo_path: Path | str, target_paths: Optional[List[str]] = None) -> Tuple[ToolStatus, List[FunctionMetric], Dict[str, Any]]:
        t0 = time.perf_counter()
        root = Path(repo_path).resolve()

        if not self.is_available():
            status = ToolStatus(
                name="lizard",
                available=False,
                version=None,
                duration_seconds=0.0,
                error="Lizard analyzer is not installed. Install via uv/pip ('uv pip install lizard') or pipx.",
            )
            return status, [], {}

        version = self.get_version()
        files = self._collect_files(root, target_paths)
        file_paths = [str(f) for f in files]

        functions: List[FunctionMetric] = []
        file_summaries: Dict[str, Any] = {}
        total_nloc = 0
        total_ccn = 0
        max_ccn = 0
        high_ccn_count = 0

        try:
            if LIZARD_LIB_AVAILABLE:
                # Use python API directly
                file_infos = lizard.analyze_files(file_paths)
                for fi in file_infos:
                    rel_file = Path(fi.filename).resolve()
                    try:
                        rel_path = rel_file.relative_to(root).as_posix()
                    except ValueError:
                        rel_path = str(rel_file)

                    total_nloc += fi.nloc
                    file_summaries[rel_path] = {
                        "nloc": fi.nloc,
                        "token_count": fi.token_count,
                        "function_count": len(fi.function_list),
                    }

                    for func in fi.function_list:
                        ccn = func.cyclomatic_complexity
                        total_ccn += ccn
                        if ccn > max_ccn:
                            max_ccn = ccn
                        if ccn > self.config.thresholds.max_function_ccn:
                            high_ccn_count += 1

                        metric = FunctionMetric(
                            file_path=rel_path,
                            name=func.name,
                            long_name=func.long_name,
                            start_line=func.start_line,
                            end_line=func.end_line,
                            cyclomatic_complexity=ccn,
                            nloc=func.nloc,
                            token_count=func.token_count,
                            parameter_count=len(func.full_parameters) if hasattr(func, "full_parameters") else 0,
                            max_nesting_depth=getattr(func, "max_nesting_depth", 0),
                        )
                        functions.append(metric)
            else:
                # Fallback to CLI
                import subprocess
                import xml.etree.ElementTree as ET
                cmd = ["lizard", "--xml"] + file_paths
                proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
                root_xml = ET.fromstring(proc.stdout)
                for item in root_xml.findall(".//item"):
                    # Parse xml output
                    pass

            duration = round(time.perf_counter() - t0, 3)
            status = ToolStatus(
                name="lizard",
                available=True,
                version=version,
                duration_seconds=duration,
            )

            func_count = len(functions)
            avg_ccn = round(total_ccn / func_count, 2) if func_count > 0 else 0.0

            raw_summary = {
                "total_nloc": total_nloc,
                "functions_count": func_count,
                "files_count": len(file_summaries),
                "total_ccn": total_ccn,
                "avg_ccn": avg_ccn,
                "max_ccn": max_ccn,
                "high_ccn_count": high_ccn_count,
                "file_summaries": file_summaries,
            }

            return status, functions, raw_summary

        except Exception as e:
            duration = round(time.perf_counter() - t0, 3)
            status = ToolStatus(
                name="lizard",
                available=True,
                version=version,
                duration_seconds=duration,
                error=f"Error executing Lizard: {e}",
            )
            return status, [], {}
