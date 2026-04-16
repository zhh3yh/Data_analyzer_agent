"""PlotStr Wrapper tool.

Wraps the MATLAB-based PlotStr tool for:
  - Distilling raw data (MAT / MF4 / CSV) into unified ``_distilled.mat`` format
  - Opening distilled files in the PlotStr GUI (with optional timestamp & video)
  - Creating bird's-eye-view videos from distilled data
  - Exporting signal name lists from distilled MAT files
  - Parallel batch distillation via subprocess workers
  - Running bartender event detection (AEB, LDP, BR223, etc.)
  - Custom signal generation (project-specific derived signals)
  - Bookmark read / write on distilled MAT files
  - Data cropping (time-window extraction from MAT)
  - AVI→MP4 video compression via FFmpeg
  - ZIP/7z extraction for measurement archives
  - MF4 file download from network shares (robocopy)
  - Selena signal filter management
  - Batch signal reading from Port structs

PlotStr CLI modes (from parseInputs.m):
  PlotStr('--distill', '-mat|-MF4|-csv', sourceFolder [, targetFolder])
  PlotStr('--open', filename [, timestamp])
  PlotStr('--help')
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
from pathlib import Path
from typing import Any

import scipy.io as sio
from loguru import logger
from pydantic import BaseModel, Field

try:
    import h5py
except ImportError:
    h5py = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class PlotStrConfig(BaseModel):
    """Configuration model for the PlotStr tool."""

    plotstr_root: str = Field(
        ...,
        description="Root directory of the PlotStr MATLAB source tree (contains ps.m, @PlotStr/, +Data/, etc.).",
    )
    matlab_executable: str = Field(
        default="matlab",
        description="Path or alias for the MATLAB executable (e.g. 'matlab' or full path).",
    )
    mdf_exporter_path: str = Field(
        default="",
        description="Path to the mdf-exporter Python tool (needed for MF4→MAT conversion).",
    )
    mdf_exporter_conda_env: str = Field(
        default="mdf-exporter",
        description="Conda environment name that contains the mdf-exporter tool.",
    )
    regex_path: str = Field(
        default="",
        description="Path to the runnable-regex file for MF4 signal filtering.",
    )
    replacement_list_path: str = Field(
        default="",
        description="Path to signal-name replacement list for MDF export.",
    )
    output_dir: str = Field(
        default="src/data/plotstr_outputs",
        description="Default directory for generated images / videos.",
    )
    config_dir: str = Field(
        default="",
        description="Path to a PlotStr JSON config (birdseye/signals/bartender). "
        "If empty, PlotStr uses its built-in config/default.json.",
    )
    max_parallel_jobs: int = Field(
        default=4,
        description="Max parallel MATLAB processes for batch distillation (keep ≤ 6).",
    )
    ffmpeg_path: str = Field(
        default="ffmpeg",
        description="Path to FFmpeg executable (for AVI→MP4 video compression).",
    )
    signal_generator_path: str = Field(
        default="",
        description="Path to +CustomSignals folder for derived signal generation. "
        "If empty, defaults to <plotstr_root>/+CustomSignals/.",
    )
    seven_zip_path: str = Field(
        default="7z",
        description="Path to 7-Zip executable (for extracting .7z / .zip archives).",
    )


# ---------------------------------------------------------------------------
# Reserved struct fields that are not signals
# ---------------------------------------------------------------------------
_RESERVED_FIELDS = {"distillation", "bookmarks", "shotData", "Comment"}

# Supported data formats (mirrors openData.m file dialog)
SUPPORTED_FORMATS = {".mat", ".csv", ".txt", ".MF4", ".mf4", ".archive", ".zip", ".7z"}


class PlotStrWrapper:
    """Python wrapper around the MATLAB-based PlotStr tooling.

    All heavy operations delegate to MATLAB via ``subprocess`` (headless
    ``-nodesktop -nosplash``) or, for simple reads, use ``scipy.io``.
    """

    def __init__(self, config: PlotStrConfig) -> None:
        self._cfg = config
        self._root = Path(config.plotstr_root).resolve()
        self._output_dir = Path(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        if not (self._root / "ps.m").is_file():
            logger.warning(f"ps.m not found in PlotStr root: {self._root}")

        logger.info(
            f"PlotStrWrapper initialized (root={self._root}, "
            f"matlab={config.matlab_executable})."
        )

    # ------------------------------------------------------------------
    # Internal MAT file loader (supports v5 via scipy and v7.3 via h5py)
    # ------------------------------------------------------------------

    @staticmethod
    def _load_mat_hdf5(mat_path: Path) -> dict[str, Any]:
        """Load a MATLAB v7.3 (HDF5) MAT file using h5py.

        Returns a dict mimicking scipy.io.loadmat output: top-level keys
        map to HDF5 groups (treated as struct-like objects).
        """
        if h5py is None:
            raise ImportError(
                "h5py is required to read MATLAB v7.3 files. "
                "Install it with: pip install h5py"
            )
        return h5py.File(str(mat_path), "r")

    @staticmethod
    def _is_hdf5(mat_path: Path) -> bool:
        """Return True if the file is HDF5 (MATLAB v7.3).

        MATLAB v7.3 files start with 'MATLAB 7.3 MAT-file' in the header
        but use HDF5 internally. We check for both the MATLAB header marker
        and the standard HDF5 magic bytes (which appear at offset 512).
        """
        with open(mat_path, "rb") as f:
            header = f.read(20)
            if b"MATLAB 7.3" in header:
                return True
            # Also check standard HDF5 magic at offset 0
            return header[:8] == b"\x89HDF\r\n\x1a\n"

    def _load_mat(self, mat_path: Path) -> tuple[Any, bool]:
        """Load a MAT file, auto-detecting v5 vs v7.3 format.

        Returns:
            (data, is_hdf5): The loaded data object and whether it's HDF5.
            For v5: data is a dict from scipy.io.loadmat.
            For v7.3: data is an h5py.File object (use data[key] to access groups).
        """
        if self._is_hdf5(mat_path):
            return self._load_mat_hdf5(mat_path), True
        return sio.loadmat(str(mat_path), squeeze_me=True), False

    @staticmethod
    def _hdf5_get_port_names(hf: Any) -> list[str]:
        """Get port names from an HDF5 MAT file."""
        ports = []
        for key in hf.keys():
            if key.startswith("#") or key.startswith("__") or key in _RESERVED_FIELDS:
                continue
            if isinstance(hf[key], h5py.Group):
                ports.append(key)
        return sorted(ports)

    @staticmethod
    def _hdf5_get_signal_names(hf: Any) -> list[str]:
        """Recursively collect signal paths from an HDF5 MAT file."""
        import numpy as np

        signals = []

        def _walk(group, prefix: str):
            for key in group.keys():
                item = group[key]
                full = f"{prefix}.{key}" if prefix else key
                if isinstance(item, h5py.Group):
                    _walk(item, full)
                elif isinstance(item, h5py.Dataset):
                    signals.append(full)

        for port_name in hf.keys():
            if (
                port_name.startswith("#")
                or port_name.startswith("__")
                or port_name in _RESERVED_FIELDS
            ):
                continue
            obj = hf[port_name]
            if isinstance(obj, h5py.Group):
                for key in obj.keys():
                    item = obj[key]
                    if isinstance(item, h5py.Group):
                        _walk(item, f"{port_name}.{key}")
                    elif isinstance(item, h5py.Dataset):
                        signals.append(f"{port_name}.{key}")
        return sorted(signals)

    @staticmethod
    def _hdf5_resolve_signal(hf: Any, port_name: str, field_path: str) -> Any:
        """Navigate an HDF5 group to resolve a dotted field path like 'm_objectDataList.m_dx.m_value'."""
        import numpy as np

        node = hf[port_name]
        for part in field_path.split("."):
            if isinstance(node, h5py.Group) and part in node:
                node = node[part]
            else:
                raise KeyError(
                    f"Field '{part}' not found under '{port_name}' (path: {field_path})"
                )
        if isinstance(node, h5py.Dataset):
            return node[:]
        raise KeyError(
            f"Resolved path '{port_name}.{field_path}' is a group, not a dataset."
        )

    # ==================================================================
    # 1. Distill — convert raw data to unified _distilled.mat
    # ==================================================================

    def distill(
        self,
        source_folder: str,
        data_format: str = "-mat",
        target_folder: str | None = None,
    ) -> str:
        """Distill raw measurement files into PlotStr's ``_distilled.mat`` format.

        Equivalent to: ``PlotStr('--distill', '<format>', sourceFolder [, targetFolder])``

        Supported formats: ``-mat``, ``-MF4``, ``-csv``.

        Args:
            source_folder: Directory containing the raw files.
            data_format: One of ``-mat``, ``-MF4``, ``-csv``.
            target_folder: Optional output directory. Defaults to source_folder.

        Returns:
            Summary message.

        Raises:
            FileNotFoundError: If source_folder does not exist.
            ValueError: If data_format is invalid.
            RuntimeError: If MATLAB exits with error.
        """
        src = Path(source_folder)
        if not src.is_dir():
            raise FileNotFoundError(f"Source folder not found: {src}")

        valid_formats = {"-mat", "-MF4", "-csv"}
        if data_format not in valid_formats:
            raise ValueError(
                f"Invalid format '{data_format}'. Must be one of {valid_formats}."
            )

        matlab_args = f"'--distill', '{data_format}', '{src.as_posix()}'"
        if target_folder:
            tgt = Path(target_folder)
            tgt.mkdir(parents=True, exist_ok=True)
            matlab_args += f", '{tgt.as_posix()}'"

        matlab_cmd = f"cd('{self._root.as_posix()}'); PlotStr({matlab_args}); exit;"
        return self._run_matlab(matlab_cmd, timeout=1800)

    def distill_parallel(
        self,
        source_folder: str,
        data_format: str = "-mat",
        recursive: bool = False,
    ) -> list[str]:
        """Batch-distill files in parallel using multiple MATLAB processes.

        Mirrors ``parallelMatDistilling.py`` from ``+cli/``.

        Args:
            source_folder: Top-level directory containing raw files.
            data_format: ``-mat``, ``-MF4``, or ``-csv``.
            recursive: Whether to recurse into subdirectories.

        Returns:
            List of summary messages (one per worker).
        """
        src = Path(source_folder)
        if not src.is_dir():
            raise FileNotFoundError(f"Source folder not found: {src}")

        ext_map = {"-mat": "*.mat", "-MF4": "*.MF4", "-csv": "*.csv"}
        pattern = ext_map.get(data_format, "*.mat")
        glob_fn = src.rglob if recursive else src.glob
        files = sorted(glob_fn(pattern))
        if not files:
            logger.warning(f"No {pattern} files found in {src}.")
            return []

        logger.info(
            f"Parallel distillation: {len(files)} files, up to {self._cfg.max_parallel_jobs} workers."
        )
        work_items = [(str(f.parent), f.name) for f in files]

        with mp.Pool(
            processes=min(self._cfg.max_parallel_jobs, len(work_items))
        ) as pool:
            results = pool.starmap(self._distill_single_file_worker, work_items)
        return results

    def _distill_single_file_worker(self, dirname: str, filename: str) -> str:
        """Worker function that distills a single file via MATLAB."""
        matlab_cmd = (
            f"cd('{self._root.as_posix()}'); "
            f"Data.DataProviderMat().openFile('{Path(dirname).as_posix()}/{filename}'); "
            f"exit;"
        )
        return self._run_matlab(matlab_cmd, timeout=600)

    # ==================================================================
    # 2. Open — launch PlotStr GUI with a file (+ optional timestamp)
    # ==================================================================

    def open_in_gui(
        self,
        file_path: str,
        timestamp_s: float | list[float] | None = None,
        config_path: str | None = None,
    ) -> str:
        """Launch the PlotStr GUI with a data file.

        Equivalent to: ``PlotStr('--open', filename [, timestamp])``

        Args:
            file_path: Path to a .mat / .MF4 / .csv file.
            timestamp_s: Optional timestamp(s) in seconds to jump to on open.
                         A single float sets the cursor; a 2-element list sets the X-axis range.
            config_path: Optional path to a PlotStr JSON config to apply.

        Returns:
            Informational message.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        fp = Path(file_path)
        if not fp.is_file():
            raise FileNotFoundError(f"Data file not found: {fp}")

        matlab_args = f"'--open', '{fp.as_posix()}'"
        if timestamp_s is not None:
            if isinstance(timestamp_s, (list, tuple)):
                matlab_args += f", [{timestamp_s[0]}, {timestamp_s[1]}]"
            else:
                matlab_args += f", {timestamp_s}"

        addpath_cmd = f"addpath('{self._root.as_posix()}');"
        config_cmd = ""
        if config_path or self._cfg.config_dir:
            cfg = config_path or self._cfg.config_dir
            config_cmd = f", 'Config', '{Path(cfg).as_posix()}'"

        # Open in foreground (non-blocking via Popen)
        full_cmd = f"{addpath_cmd} PlotStr({matlab_args}{config_cmd});"
        cmd = self._build_matlab_cmd(full_cmd, desktop=True)
        logger.info(f"Launching PlotStr GUI: {full_cmd}")
        subprocess.Popen(cmd)

        msg = f"PlotStr GUI launched with '{fp.name}'"
        if timestamp_s is not None:
            msg += f" at t={timestamp_s}s"
        msg += ". Awaiting manual review."
        logger.info(msg)
        return msg

    # ==================================================================
    # 3. Create video — bird's-eye-view MP4 from distilled data
    # ==================================================================

    def create_video(
        self,
        mat_file_path: str,
        output_folder: str,
        time_range_s: tuple[float, float],
        video_name: str = "birdsEyeView",
        frame_rate: int = 10,
    ) -> str:
        """Create an MP4 bird's-eye-view video from a distilled MAT file.

        Mirrors ``+cli/createVideo.m``.

        Args:
            mat_file_path: Path to the distilled .mat file.
            output_folder: Directory where the video will be saved.
            time_range_s: (start, end) in seconds relative to measurement start.
            video_name: Output file name (without extension).
            frame_rate: Frames per second (default 10).

        Returns:
            Path to the generated video file.

        Raises:
            FileNotFoundError: If the MAT file or output folder doesn't exist.
            ValueError: If time_range is invalid.
        """
        mat_path = Path(mat_file_path)
        out_dir = Path(output_folder)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")
        out_dir.mkdir(parents=True, exist_ok=True)

        if time_range_s[0] >= time_range_s[1] or time_range_s[0] < 0:
            raise ValueError(f"Invalid time range: {time_range_s}")

        matlab_cmd = (
            f"cd('{self._root.as_posix()}'); "
            f"cli.createVideo("
            f"'{mat_path.as_posix()}', "
            f"'{out_dir.as_posix()}', "
            f"[{time_range_s[0]}, {time_range_s[1]}], "
            f"'{video_name}', "
            f"{frame_rate}); "
            f"exit;"
        )

        self._run_matlab(matlab_cmd, timeout=3600)

        output_path = out_dir / f"{video_name}.mp4"
        logger.info(f"Video created: {output_path}")
        return str(output_path)

    # ==================================================================
    # 4. Export signal names from a distilled .mat file
    # ==================================================================

    def export_signal_names(self, mat_file_path: str) -> list[str]:
        """Extract all signal names from a distilled MAT file.

        Supports both MATLAB v5 (scipy) and v7.3 HDF5 (h5py) formats.

        Args:
            mat_file_path: Path to a ``_distilled.mat`` file.

        Returns:
            Sorted list of fully-qualified signal names.

        Raises:
            FileNotFoundError: If the MAT file does not exist.
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")

        data, is_hdf5 = self._load_mat(mat_path)
        try:
            if is_hdf5:
                signals = self._hdf5_get_signal_names(data)
            else:
                signals: list[str] = []
                for port_name, port_val in data.items():
                    if port_name.startswith("__") or port_name in _RESERVED_FIELDS:
                        continue
                    if hasattr(port_val, "dtype") and port_val.dtype.names:
                        for sig_name in port_val.dtype.names:
                            signals.append(f"{port_name}.{sig_name}")
                signals.sort()
        finally:
            if is_hdf5:
                data.close()

        logger.info(f"Exported {len(signals)} signal names from {mat_path.name}.")
        return signals

    def export_signal_names_to_file(
        self, mat_file_path: str, output_path: str | None = None
    ) -> str:
        """Export signal names to a text file (one per line).

        Args:
            mat_file_path: Path to the distilled .mat file.
            output_path: Optional output .txt path. Defaults to ``<basename>_signals.txt``.

        Returns:
            Path to the written text file.
        """
        signals = self.export_signal_names(mat_file_path)
        mat_p = Path(mat_file_path)
        out = (
            Path(output_path)
            if output_path
            else mat_p.with_name(f"{mat_p.stem}_signals.txt")
        )
        out.write_text("\n".join(signals) + "\n", encoding="utf-8")
        logger.info(f"Signal names written to {out}")
        return str(out)

    # ==================================================================
    # 5. Read / query a distilled MAT file
    # ==================================================================

    def read_signal(
        self,
        mat_file_path: str,
        signal_name: str,
    ) -> dict[str, Any]:
        """Read a single signal's data from a distilled MAT file.

        Args:
            mat_file_path: Path to the distilled .mat file.
            signal_name: Fully-qualified name in ``Port.Signal`` format.

        Returns:
            Dictionary with ``time`` (array) and ``values`` (array).

        Raises:
            FileNotFoundError: If the file does not exist.
            KeyError: If the signal is not found.
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")

        parts = signal_name.split(".", 1)
        if len(parts) != 2:
            raise KeyError(f"Signal name must be 'Port.Signal', got: '{signal_name}'")
        port_name, sig_path = parts

        data, is_hdf5 = self._load_mat(mat_path)
        try:
            if is_hdf5:
                if port_name not in data:
                    raise KeyError(f"Port '{port_name}' not found in {mat_path.name}.")
                time_data = (
                    data[port_name]["time"][:].flatten()
                    if "time" in data[port_name]
                    else None
                )
                signal_data = self._hdf5_resolve_signal(data, port_name, sig_path)
            else:
                if port_name not in data:
                    raise KeyError(f"Port '{port_name}' not found in {mat_path.name}.")
                port = data[port_name]
                if not hasattr(port, "dtype") or port.dtype.names is None:
                    raise KeyError(f"Port '{port_name}' is not a struct.")
                if sig_path not in port.dtype.names:
                    raise KeyError(
                        f"Signal '{sig_path}' not found in port '{port_name}'."
                    )
                time_data = port["time"].item() if "time" in port.dtype.names else None
                signal_data = port[sig_path].item()
        finally:
            if is_hdf5:
                data.close()

        return {"time": time_data, "values": signal_data}

    # ==================================================================
    # 6. PlotStr JSON config helpers
    # ==================================================================

    def load_config(self, config_path: str) -> dict[str, Any]:
        """Load a PlotStr JSON configuration file.

        PlotStr configs contain sections: SBirdseye, SStates, SSignals,
        SBartenders, SGuiState.
        """
        cfg_path = Path(config_path)
        if not cfg_path.is_file():
            raise FileNotFoundError(f"Config not found: {cfg_path}")
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_config(self, config: dict[str, Any], output_path: str) -> str:
        """Save a PlotStr JSON configuration file."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"Config saved to {out}")
        return str(out)

    def build_signal_config(
        self,
        signals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build the SSignals section for a PlotStr config.

        Each signal dict can have keys matching PlotStr's internal format:
        sName, sDisplayName, sWildcardFilter, lActive, dNorm, dOffset,
        sUnit, iInd, dInvalid.
        """
        result = []
        for sig in signals:
            entry = {
                "sName": sig.get("sName", sig.get("name", "")),
                "sDisplayName": sig.get("sDisplayName", sig.get("display_name", "")),
                "sWildcardFilter": sig.get("sWildcardFilter", ""),
                "lActive": sig.get("lActive", True),
                "dNorm": sig.get("dNorm", 1.0),
                "dOffset": sig.get("dOffset", 0.0),
                "sUnit": sig.get("sUnit", sig.get("unit", "")),
                "iInd": sig.get("iInd", 1),
                "dInvalid": sig.get("dInvalid", []),
            }
            result.append(entry)
        return result

    # ==================================================================
    # 7. Bartender — headless event detection
    # ==================================================================

    def run_bartender(
        self,
        bartender_class: str,
        data_folder: str,
        output_dir: str | None = None,
        cut_shots: bool = True,
        print_jpegs: bool = False,
        write_table: bool = False,
        hold_time_s: float = 0.5,
        pre_event_time_s: float = 2.0,
        post_event_time_s: float = 1.0,
        data_type: int = 2,
        max_meas_time_h: float | None = None,
    ) -> str:
        """Run a bartender event detector headlessly on a folder of data.

        Mirrors ``AbstractBartender.run()`` from ``+bartender/``.

        Available bartender classes (examples):
          - ``bartender.AEB_E3``, ``bartender.AEB_HS``, ``bartender.AEB_VRU``
          - ``bartender.AEB_LTA``, ``bartender.AEB_M``, ``bartender.AEB_OD``
          - ``bartender.Ldp``
          - ``bartender.BR223.SearchAllTrucks``, ``bartender.BR223.AdapMonitoring``
          - ``bartender.FastSignalSearchTemplate``

        Args:
            bartender_class: Fully-qualified MATLAB class name (e.g. ``bartender.AEB_E3``).
            data_folder: Path to folder with distilled MAT files (or raw files).
            output_dir: Output directory for shots/tables. Defaults to
                        ``<data_folder>/bartender_<name>/``.
            cut_shots: Export cropped shot MAT files for each activation.
            print_jpegs: Export JPEG screenshots per activation.
            write_table: Write Excel results table.
            hold_time_s: Activation hold time (merges close activations).
            pre_event_time_s: Seconds before activation to include in shot.
            post_event_time_s: Seconds after activation to include in shot.
            data_type: 1=``*.mat``, 2=``*distilled.mat``, 3=``*.MF4``,
                       4=``*cluster_output.zip``, 5=``*.csv``.
            max_meas_time_h: Max accumulated measurement hours before stopping.

        Returns:
            MATLAB stdout summary.

        Raises:
            FileNotFoundError: If data_folder does not exist.
            RuntimeError: If MATLAB exits with error.
        """
        folder = Path(data_folder)
        if not folder.is_dir():
            raise FileNotFoundError(f"Data folder not found: {folder}")

        sig_gen = (
            self._cfg.signal_generator_path
            or f"{self._root.as_posix()}/+CustomSignals/"
        )
        output_cmd = ""
        if output_dir:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            output_cmd = f"hB.outputDir = '{Path(output_dir).as_posix()}';"

        max_meas_cmd = ""
        if max_meas_time_h is not None:
            max_meas_cmd = f"hB.dMaxMeasTime_h = {max_meas_time_h};"

        matlab_cmd = (
            f"cd('{self._root.as_posix()}'); "
            f"hF = str2func('{bartender_class}'); "
            f"hB = hF(PlotStr.empty, '{bartender_class.split('.')[-1]}', "
            f"CObject.CTooltip.empty, '{sig_gen}'); "
            f"hB.sPath = '{folder.as_posix()}'; "
            f"hB.bCutShots = {'true' if cut_shots else 'false'}; "
            f"hB.bPrintJpegs = {'true' if print_jpegs else 'false'}; "
            f"hB.bWriteTable = {'true' if write_table else 'false'}; "
            f"hB.dHoldTime_s = {hold_time_s}; "
            f"hB.dPreEventTime_s = {pre_event_time_s}; "
            f"hB.dPostEventTime_s = {post_event_time_s}; "
            f"hB.dataType = {data_type}; "
            f"{max_meas_cmd} "
            f"{output_cmd} "
            f"hB.run(); exit;"
        )
        return self._run_matlab(matlab_cmd, timeout=7200)

    def list_bartender_classes(self) -> list[str]:
        """List all available bartender .m files under +bartender/.

        Returns:
            List of fully-qualified bartender class names.
        """
        bartender_dir = self._root / "+bartender"
        if not bartender_dir.is_dir():
            logger.warning(f"+bartender/ not found in {self._root}")
            return []

        skip = {"AbstractBartender.m", "CCategory.m", "Template.m"}
        classes = []

        # Top-level bartenders
        for f in sorted(bartender_dir.glob("*.m")):
            if f.name not in skip:
                classes.append(f"bartender.{f.stem}")

        # Sub-namespace bartenders (e.g. +BR223/)
        for sub_dir in sorted(bartender_dir.iterdir()):
            if sub_dir.is_dir() and sub_dir.name.startswith("+"):
                ns = sub_dir.name[1:]  # strip '+'
                for f in sorted(sub_dir.glob("*.m")):
                    if f.name not in skip:
                        classes.append(f"bartender.{ns}.{f.stem}")

        logger.info(f"Found {len(classes)} bartender classes.")
        return classes

    # ==================================================================
    # 8. Custom Signal Generation
    # ==================================================================

    def run_custom_signal_generator(
        self,
        mat_file_path: str,
        custom_signals_path: str | None = None,
    ) -> str:
        """Run CustomSignalGenerator on a distilled MAT file.

        Mirrors ``+CustomSignals/CustomSignalGenerator.m``: scans a folder
        for .m scripts and applies each as a signal transformation.

        Args:
            mat_file_path: Path to the distilled .mat file.
            custom_signals_path: Path to +CustomSignals folder. Defaults to
                                 ``<plotstr_root>/+CustomSignals/``.

        Returns:
            MATLAB stdout.
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")

        sig_path = custom_signals_path or self._cfg.signal_generator_path
        if not sig_path:
            sig_path = f"{self._root.as_posix()}/+CustomSignals/"

        matlab_cmd = (
            f"cd('{self._root.as_posix()}'); "
            f"SData = load('{mat_path.as_posix()}'); "
            f"SData = CustomSignals.CustomSignalGenerator('{Path(sig_path).as_posix()}', SData); "
            f"save('{mat_path.as_posix()}', '-struct', 'SData', '-v7.3'); "
            f"disp('CustomSignalGenerator complete.'); exit;"
        )
        return self._run_matlab(matlab_cmd, timeout=600)

    def list_custom_signal_generators(
        self, custom_signals_path: str | None = None
    ) -> list[str]:
        """List available custom signal generator scripts.

        Returns:
            List of script names (without .m extension) organized by project namespace.
        """
        base = (
            Path(custom_signals_path)
            if custom_signals_path
            else (self._root / "+CustomSignals")
        )
        if not base.is_dir():
            return []

        generators = []
        # Top-level .m files
        for f in sorted(base.glob("*.m")):
            if f.stem != "CustomSignalGenerator":
                generators.append(f.stem)
        # Sub-namespaces (+BR223, +E3, +Common, etc.)
        for sub_dir in sorted(base.iterdir()):
            if sub_dir.is_dir() and sub_dir.name.startswith("+"):
                ns = sub_dir.name[1:]
                for f in sorted(sub_dir.glob("*.m")):
                    generators.append(f"{ns}.{f.stem}")

        return generators

    # ==================================================================
    # 9. Bookmark read / write
    # ==================================================================

    def read_bookmarks(self, mat_file_path: str) -> list[dict[str, Any]]:
        """Read bookmarks from a distilled MAT file.

        Bookmarks are stored as a cell array in the ``bookmarks`` field:
        each row is ``[category_id, category_text, timestamp_ms]``.

        Args:
            mat_file_path: Path to the distilled .mat file.

        Returns:
            List of dicts with ``category``, ``text``, and ``timestamp_ms``.
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")

        data, is_hdf5 = self._load_mat(mat_path)
        try:
            if is_hdf5:
                if "bookmarks" not in data or data["bookmarks"].size == 0:
                    return []
                bm = data["bookmarks"][:]
            else:
                if "bookmarks" not in data or data["bookmarks"].size == 0:
                    return []
                bm = data["bookmarks"]
        finally:
            if is_hdf5:
                data.close()

        result = []
        if bm.ndim == 1:
            bm = bm.reshape(1, -1)
        for row in bm:
            result.append(
                {
                    "category": (
                        int(row[0]) if hasattr(row[0], "__int__") else str(row[0])
                    ),
                    "text": str(row[1]),
                    "timestamp_ms": float(row[2]) if len(row) > 2 else 0.0,
                }
            )

        logger.info(f"Read {len(result)} bookmarks from {mat_path.name}.")
        return result

    def write_bookmarks(
        self,
        mat_file_path: str,
        bookmarks: list[dict[str, Any]],
    ) -> str:
        """Write/update bookmarks in a distilled MAT file.

        Args:
            mat_file_path: Path to the distilled .mat file.
            bookmarks: List of dicts with ``category`` (int/str), ``text`` (str),
                       ``timestamp_ms`` (float).

        Returns:
            Path to the updated file.
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")

        import numpy as np

        if not bookmarks:
            bm_array = np.array([])
        else:
            bm_array = np.empty((len(bookmarks), 3), dtype=object)
            for i, bm in enumerate(bookmarks):
                bm_array[i, 0] = str(bm["category"])
                bm_array[i, 1] = str(bm["text"])
                bm_array[i, 2] = str(bm["timestamp_ms"])

        # Load existing data, update bookmarks, save back.
        # Note: write-back only supported for v5 MAT files (scipy).
        if self._is_hdf5(mat_path):
            raise NotImplementedError(
                "Writing bookmarks to MATLAB v7.3 HDF5 files is not supported. "
                "Use MATLAB directly or convert the file to v5 format first."
            )
        data = sio.loadmat(str(mat_path))
        data["bookmarks"] = bm_array
        sio.savemat(str(mat_path), data, do_compression=True)

        logger.info(f"Wrote {len(bookmarks)} bookmarks to {mat_path.name}.")
        return str(mat_path)

    # ==================================================================
    # 10. Data cropping (time-window extraction)
    # ==================================================================

    def crop_mat_data(
        self,
        mat_file_path: str,
        start_times_ms: list[float],
        end_times_ms: list[float],
        output_dir: str | None = None,
    ) -> list[str]:
        """Crop a distilled MAT file into time-window segments.

        Mirrors ``+Data/fCropMatData.m``: for each (start, end) pair, extracts
        all port data within that time window and saves as a separate shot file.

        Args:
            mat_file_path: Path to the distilled .mat file.
            start_times_ms: List of start timestamps in milliseconds.
            end_times_ms: List of end timestamps in milliseconds.
            output_dir: Output directory for cropped files. Defaults to same dir.

        Returns:
            List of paths to the generated shot files.
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")
        if len(start_times_ms) != len(end_times_ms):
            raise ValueError(
                "start_times_ms and end_times_ms must have the same length."
            )

        out_dir = Path(output_dir) if output_dir else mat_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        starts_str = "[" + ", ".join(str(t) for t in start_times_ms) + "]"
        ends_str = "[" + ", ".join(str(t) for t in end_times_ms) + "]"

        matlab_cmd = (
            f"cd('{self._root.as_posix()}'); "
            f"SCropped = Data.fCropMatData('{mat_path.as_posix()}', {starts_str}, {ends_str}); "
            f"for i = 1:numel(SCropped), "
            f"  sOut = sprintf('{out_dir.as_posix()}/{mat_path.stem}_shot_%03d_distilled.mat', i); "
            f"  SSave = SCropped(i); "
            f"  save(sOut, '-struct', 'SSave', '-v7.3'); "
            f"end; "
            f"disp('Crop complete.'); exit;"
        )

        self._run_matlab(matlab_cmd, timeout=600)

        outputs = []
        for i in range(1, len(start_times_ms) + 1):
            p = out_dir / f"{mat_path.stem}_shot_{i:03d}_distilled.mat"
            outputs.append(str(p))
        logger.info(f"Cropped {len(outputs)} shots from {mat_path.name}.")
        return outputs

    # ==================================================================
    # 11. AVI→MP4 video compression (FFmpeg)
    # ==================================================================

    def compress_videos(
        self,
        input_dir: str,
        output_dir: str | None = None,
        crop: str = "crop=1014:512:325:0",
        crf: int = 31,
    ) -> list[str]:
        """Compress AVI files to MP4 using FFmpeg with libx264.

        Mirrors ``compress_20251120.py``.

        Args:
            input_dir: Directory containing .avi files.
            output_dir: Output directory for .mp4 files. Defaults to
                        ``<input_dir>/compressed/``.
            crop: FFmpeg crop filter string (e.g. ``crop=1014:512:325:0``).
            crf: Constant Rate Factor for libx264 (lower = higher quality).

        Returns:
            List of paths to compressed .mp4 files.
        """
        in_dir = Path(input_dir)
        if not in_dir.is_dir():
            raise FileNotFoundError(f"Input directory not found: {in_dir}")

        out_dir = Path(output_dir) if output_dir else in_dir / "compressed"
        out_dir.mkdir(parents=True, exist_ok=True)

        avi_files = sorted(in_dir.glob("*.avi"))
        if not avi_files:
            logger.warning(f"No .avi files found in {in_dir}.")
            return []

        ffmpeg = self._cfg.ffmpeg_path
        results = []
        for i, avi in enumerate(avi_files, 1):
            out_path = out_dir / f"{avi.stem}.mp4"
            if out_path.is_file():
                logger.info(f"[{i}/{len(avi_files)}] SKIP (exists): {out_path.name}")
                results.append(str(out_path))
                continue

            logger.info(f"[{i}/{len(avi_files)}] Compressing: {avi.name}")
            cmd = [
                ffmpeg,
                "-i",
                str(avi),
                "-c:v",
                "libx264",
                "-vf",
                crop,
                "-crf",
                str(crf),
                "-f",
                "mp4",
                str(out_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                logger.error(f"FFmpeg failed for {avi.name}: {result.stderr[-500:]}")
                if out_path.is_file():
                    out_path.unlink()
            else:
                results.append(str(out_path))

        logger.info(f"Compressed {len(results)}/{len(avi_files)} videos.")
        return results

    # ==================================================================
    # 12. ZIP / 7z extraction
    # ==================================================================

    def extract_archives(
        self,
        input_dir: str,
        output_dir: str | None = None,
        pattern: str = "*.zip",
    ) -> list[str]:
        """Extract ZIP or 7z measurement archives.

        Args:
            input_dir: Directory containing archive files.
            output_dir: Extraction destination. Defaults to input_dir.
            pattern: Glob pattern (``*.zip``, ``*.7z``, or ``*.zip;*.7z``).

        Returns:
            List of extracted directory paths.
        """
        in_dir = Path(input_dir)
        if not in_dir.is_dir():
            raise FileNotFoundError(f"Input directory not found: {in_dir}")

        out_dir = Path(output_dir) if output_dir else in_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        archives = sorted(in_dir.glob(pattern))
        if not archives:
            logger.warning(f"No archives matching '{pattern}' in {in_dir}.")
            return []

        results = []
        for arc in archives:
            logger.info(f"Extracting: {arc.name}")
            if arc.suffix == ".zip":
                import zipfile

                with zipfile.ZipFile(str(arc), "r") as zf:
                    zf.extractall(str(out_dir))
            elif arc.suffix == ".7z":
                cmd = [self._cfg.seven_zip_path, "x", str(arc), f"-o{out_dir}", "-y"]
                subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            results.append(str(out_dir / arc.stem))

        logger.info(f"Extracted {len(results)} archives.")
        return results

    # ==================================================================
    # 13. MF4 download via robocopy (network share)
    # ==================================================================

    def download_mf4_from_share(
        self,
        network_paths: list[str],
        destination: str,
        file_pattern: str = "*.mf4",
    ) -> list[str]:
        """Download MF4 files from network shares using robocopy.

        Mirrors ``download_mf4.ps1``: copies .mf4 files from UNC paths.

        Args:
            network_paths: List of UNC paths (e.g. ``\\\\server\\share\\folder``).
            destination: Local destination directory.
            file_pattern: File pattern to copy (default ``*.mf4``).

        Returns:
            List of copied file paths.
        """
        dest = Path(destination)
        dest.mkdir(parents=True, exist_ok=True)
        copied = []

        for net_path in network_paths:
            logger.info(f"Copying MF4 from {net_path} -> {dest}")
            cmd = f'robocopy "{net_path}" "{dest}" {file_pattern} /R:1 /W:1'
            result = subprocess.run(
                cmd, capture_output=True, text=True, shell=True, timeout=600
            )
            # robocopy: 0-7 = success, >=8 = error
            if result.returncode >= 8:
                logger.error(
                    f"Robocopy failed (rc={result.returncode}): {result.stderr}"
                )
            else:
                # Find copied files
                for f in dest.glob(file_pattern):
                    if str(f) not in copied:
                        copied.append(str(f))

        logger.info(f"Downloaded {len(copied)} MF4 file(s).")
        return copied

    # ==================================================================
    # 14. Selena signal filter management
    # ==================================================================

    def list_selena_filters(self) -> list[str]:
        """List available Selena filter files in the selena_filter/ directory.

        Returns:
            List of filter file names.
        """
        filter_dir = self._root / "selena_filter"
        if not filter_dir.is_dir():
            return []
        return [f.name for f in sorted(filter_dir.glob("*.filter"))]

    def read_selena_filter(self, filter_name: str) -> list[str]:
        """Read a Selena signal filter file and return its include/exclude patterns.

        Each line is like: ``include .*PerSepRunnable.*_m_internalStates_out.*``

        Args:
            filter_name: Name of the filter file (with or without .filter extension).

        Returns:
            List of filter lines.
        """
        if not filter_name.endswith(".filter"):
            filter_name += ".filter"
        filter_path = self._root / "selena_filter" / filter_name
        if not filter_path.is_file():
            raise FileNotFoundError(f"Filter file not found: {filter_path}")
        lines = filter_path.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip()]

    def apply_selena_filter(
        self,
        signal_names: list[str],
        filter_name: str,
    ) -> list[str]:
        """Apply a Selena filter to a list of signal names.

        ``include`` patterns keep matching signals; ``exclude`` patterns remove them.

        Args:
            signal_names: Full list of signal names.
            filter_name: Name of the .filter file.

        Returns:
            Filtered list of signal names.
        """
        import re

        rules = self.read_selena_filter(filter_name)

        includes = []
        excludes = []
        for rule in rules:
            parts = rule.split(None, 1)
            if len(parts) != 2:
                continue
            action, pattern = parts
            if action.lower() == "include":
                includes.append(pattern)
            elif action.lower() == "exclude":
                excludes.append(pattern)

        # If there are include rules, only keep signals matching at least one
        if includes:
            filtered = []
            for sig in signal_names:
                for pat in includes:
                    if re.search(pat, sig):
                        filtered.append(sig)
                        break
        else:
            filtered = list(signal_names)

        # Apply exclude rules
        for pat in excludes:
            filtered = [s for s in filtered if not re.search(pat, s)]

        logger.info(
            f"Selena filter '{filter_name}': {len(signal_names)} -> {len(filtered)} signals."
        )
        return filtered

    # ==================================================================
    # 15. Batch signal reading
    # ==================================================================

    def read_signals_batch(
        self,
        mat_file_path: str,
        signal_names: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Read multiple signals from a distilled MAT file in one load.

        Args:
            mat_file_path: Path to the distilled .mat file.
            signal_names: List of fully-qualified signal names (``Port.Signal``).

        Returns:
            Dict mapping signal name → {``time``: array, ``values``: array}.
            Signals not found are omitted with a warning.
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")

        data, is_hdf5 = self._load_mat(mat_path)
        results = {}

        try:
            for sig_name in signal_names:
                parts = sig_name.split(".", 1)
                if len(parts) != 2:
                    logger.warning(
                        f"Invalid signal format (need 'Port.Signal'): {sig_name}"
                    )
                    continue
                port_name, field_name = parts

                if is_hdf5:
                    if port_name not in data:
                        logger.warning(
                            f"Port '{port_name}' not found, skipping {sig_name}."
                        )
                        continue
                    try:
                        time_arr = (
                            data[port_name]["time"][:].flatten()
                            if "time" in data[port_name]
                            else None
                        )
                        values = self._hdf5_resolve_signal(data, port_name, field_name)
                        results[sig_name] = {"time": time_arr, "values": values}
                    except KeyError:
                        logger.warning(
                            f"Signal '{field_name}' not in port '{port_name}', skipping."
                        )
                else:
                    if port_name not in data:
                        logger.warning(
                            f"Port '{port_name}' not found, skipping {sig_name}."
                        )
                        continue
                    port = data[port_name]
                    if not hasattr(port, "dtype") or port.dtype.names is None:
                        logger.warning(
                            f"Port '{port_name}' is not a struct, skipping {sig_name}."
                        )
                        continue
                    if field_name not in port.dtype.names:
                        logger.warning(
                            f"Signal '{field_name}' not in port '{port_name}', skipping."
                        )
                        continue
                    time_arr = (
                        port["time"].item() if "time" in port.dtype.names else None
                    )
                    results[sig_name] = {
                        "time": time_arr,
                        "values": port[field_name].item(),
                    }
        finally:
            if is_hdf5:
                data.close()

        logger.info(
            f"Read {len(results)}/{len(signal_names)} signals from {mat_path.name}."
        )
        return results

    def list_ports(self, mat_file_path: str) -> list[str]:
        """List all port names in a distilled MAT file.

        Args:
            mat_file_path: Path to the distilled .mat file.

        Returns:
            List of port names (excluding reserved fields and MATLAB metadata).
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")

        data, is_hdf5 = self._load_mat(mat_path)
        try:
            if is_hdf5:
                ports = self._hdf5_get_port_names(data)
            else:
                ports = []
                for key, val in data.items():
                    if key.startswith("__") or key in _RESERVED_FIELDS:
                        continue
                    if hasattr(val, "dtype") and val.dtype.names:
                        ports.append(key)
                ports.sort()
        finally:
            if is_hdf5:
                data.close()
        return ports

    def get_time_span(self, mat_file_path: str) -> tuple[float, float]:
        """Get the time span (min, max) in milliseconds from a distilled MAT file.

        Scans all ports' ``time`` fields and returns the overall range.
        """
        mat_path = Path(mat_file_path)
        if not mat_path.is_file():
            raise FileNotFoundError(f"MAT file not found: {mat_path}")

        import numpy as np

        t_min, t_max = np.inf, -np.inf

        data, is_hdf5 = self._load_mat(mat_path)
        try:
            if is_hdf5:
                for key in data.keys():
                    if (
                        key.startswith("#")
                        or key.startswith("__")
                        or key in _RESERVED_FIELDS
                    ):
                        continue
                    grp = data[key]
                    if isinstance(grp, h5py.Group) and "time" in grp:
                        t = grp["time"][:].flatten()
                        if t.size > 0:
                            t_min = min(t_min, float(t.min()))
                            t_max = max(t_max, float(t.max()))
            else:
                for key, val in data.items():
                    if key.startswith("__") or key in _RESERVED_FIELDS:
                        continue
                    if (
                        hasattr(val, "dtype")
                        and val.dtype.names
                        and "time" in val.dtype.names
                    ):
                        t = val["time"].item()
                        if t.size > 0:
                            t_min = min(t_min, float(t.min()))
                            t_max = max(t_max, float(t.max()))
        finally:
            if is_hdf5:
                data.close()

        return (t_min, t_max)

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _build_matlab_cmd(self, matlab_code: str, desktop: bool = False) -> list[str]:
        """Build the MATLAB subprocess command list."""
        cmd = [self._cfg.matlab_executable, "-nosplash"]
        if not desktop:
            cmd.extend(["-nodesktop", "-wait"])
        cmd.extend(["-r", matlab_code])
        return cmd

    def _run_matlab(self, matlab_code: str, timeout: int = 600) -> str:
        """Execute MATLAB code in a headless subprocess.

        Returns:
            stdout of the MATLAB process.

        Raises:
            RuntimeError: If MATLAB exits with a non-zero code.
        """
        cmd = self._build_matlab_cmd(matlab_code)
        logger.info(f"MATLAB command: {matlab_code[:200]}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            logger.error(f"MATLAB failed (rc={result.returncode}): {result.stderr}")
            raise RuntimeError(
                f"MATLAB error (rc={result.returncode}): {result.stderr}"
            )

        logger.debug(f"MATLAB stdout (first 500 chars): {result.stdout[:500]}")
        return result.stdout

    # def _plot_via_matlab_engine(self, mat_file_path, signals, output_path, title):
    #     """Fallback using matlab.engine (requires MATLAB installation)."""
    #     import matlab.engine
    #     eng = matlab.engine.start_matlab()
    #     try:
    #         eng.addpath(str(Path(self._config.executable_path).parent))
    #         eng.plotstr_batch(mat_file_path, signals, str(output_path), title, nargout=0)
    #     finally:
    #         eng.quit()
    #     return str(output_path)
