"""Unit tests for PlotStrWrapper."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.tools.plotstr_wrapper import PlotStrConfig, PlotStrWrapper


@pytest.fixture
def plotstr_config(tmp_path: Path) -> PlotStrConfig:
    # Create a fake ps.m so the wrapper doesn't warn
    (tmp_path / "plotstr_root" / "ps.m").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "plotstr_root" / "ps.m").touch()
    return PlotStrConfig(
        plotstr_root=str(tmp_path / "plotstr_root"),
        matlab_executable="matlab",
        output_dir=str(tmp_path / "output"),
    )


@pytest.fixture
def wrapper(plotstr_config: PlotStrConfig) -> PlotStrWrapper:
    return PlotStrWrapper(plotstr_config)


# ------------------------------------------------------------------
# Distill
# ------------------------------------------------------------------


class TestDistill:
    def test_raises_if_source_folder_missing(self, wrapper: PlotStrWrapper) -> None:
        with pytest.raises(FileNotFoundError, match="Source folder not found"):
            wrapper.distill(source_folder="nonexistent_dir")

    def test_raises_on_invalid_format(
        self, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        src = tmp_path / "raw"
        src.mkdir()
        with pytest.raises(ValueError, match="Invalid format"):
            wrapper.distill(source_folder=str(src), data_format="-xyz")

    @patch("src.tools.plotstr_wrapper.subprocess.run")
    def test_distill_mat_success(
        self, mock_run: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        src = tmp_path / "raw"
        src.mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")

        result = wrapper.distill(source_folder=str(src), data_format="-mat")

        assert "Done" in result
        mock_run.assert_called_once()

    @patch("src.tools.plotstr_wrapper.subprocess.run")
    def test_distill_matlab_error(
        self, mock_run: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        src = tmp_path / "raw"
        src.mkdir()
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="MATLAB error"
        )

        with pytest.raises(RuntimeError, match="MATLAB error"):
            wrapper.distill(source_folder=str(src), data_format="-mat")


# ------------------------------------------------------------------
# Open in GUI
# ------------------------------------------------------------------


class TestOpenInGui:
    def test_raises_if_file_missing(self, wrapper: PlotStrWrapper) -> None:
        with pytest.raises(FileNotFoundError, match="Data file not found"):
            wrapper.open_in_gui(file_path="nope.mat")

    @patch("src.tools.plotstr_wrapper.subprocess.Popen")
    def test_open_success(
        self, mock_popen: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "test.mat"
        mat_file.touch()

        msg = wrapper.open_in_gui(file_path=str(mat_file))

        assert "PlotStr GUI launched" in msg
        mock_popen.assert_called_once()

    @patch("src.tools.plotstr_wrapper.subprocess.Popen")
    def test_open_with_timestamp(
        self, mock_popen: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "test.mat"
        mat_file.touch()

        msg = wrapper.open_in_gui(file_path=str(mat_file), timestamp_s=12.5)

        assert "t=12.5s" in msg

    @patch("src.tools.plotstr_wrapper.subprocess.Popen")
    def test_open_with_time_range(
        self, mock_popen: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "test.mat"
        mat_file.touch()

        msg = wrapper.open_in_gui(file_path=str(mat_file), timestamp_s=[10.0, 20.0])

        assert "PlotStr GUI launched" in msg


# ------------------------------------------------------------------
# Create video
# ------------------------------------------------------------------


class TestCreateVideo:
    def test_raises_if_mat_missing(
        self, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError, match="MAT file not found"):
            wrapper.create_video(
                mat_file_path="nope.mat",
                output_folder=str(tmp_path),
                time_range_s=(0.0, 10.0),
            )

    def test_raises_on_invalid_time_range(
        self, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "data.mat"
        mat_file.touch()
        with pytest.raises(ValueError, match="Invalid time range"):
            wrapper.create_video(
                mat_file_path=str(mat_file),
                output_folder=str(tmp_path),
                time_range_s=(10.0, 5.0),
            )


# ------------------------------------------------------------------
# Export signal names
# ------------------------------------------------------------------


class TestExportSignalNames:
    def test_raises_if_file_missing(self, wrapper: PlotStrWrapper) -> None:
        with pytest.raises(FileNotFoundError, match="MAT file not found"):
            wrapper.export_signal_names("nonexistent.mat")

    @patch("src.tools.plotstr_wrapper.sio.loadmat")
    def test_export_signals(
        self, mock_loadmat: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "test_distilled.mat"
        mat_file.touch()

        # Simulate a distilled MAT with one port containing time + 2 signals
        port_dtype = np.dtype([("time", "O"), ("speed", "O"), ("accel", "O")])
        port_data = np.zeros(1, dtype=port_dtype)
        mock_loadmat.return_value = {
            "__header__": b"",
            "__version__": "1.0",
            "__globals__": [],
            "MyPort": port_data,
            "bookmarks": np.array([]),
        }

        signals = wrapper.export_signal_names(str(mat_file))

        assert "MyPort.speed" in signals
        assert "MyPort.accel" in signals
        assert "MyPort.time" in signals
        # Reserved fields should be excluded
        assert not any(s.startswith("bookmarks") for s in signals)

    @patch("src.tools.plotstr_wrapper.sio.loadmat")
    def test_export_signals_to_file(
        self, mock_loadmat: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "data_distilled.mat"
        mat_file.touch()

        port_dtype = np.dtype([("time", "O"), ("sig1", "O")])
        mock_loadmat.return_value = {"Port1": np.zeros(1, dtype=port_dtype)}

        out_path = wrapper.export_signal_names_to_file(str(mat_file))

        assert Path(out_path).is_file()
        content = Path(out_path).read_text()
        assert "Port1.sig1" in content


# ------------------------------------------------------------------
# Config helpers
# ------------------------------------------------------------------


class TestConfigHelpers:
    def test_build_signal_config(self, wrapper: PlotStrWrapper) -> None:
        signals = [
            {"name": "Port1.speed", "display_name": "Speed", "unit": "m/s"},
            {"sName": "Port2.accel", "sDisplayName": "Acceleration"},
        ]
        result = wrapper.build_signal_config(signals)

        assert len(result) == 2
        assert result[0]["sName"] == "Port1.speed"
        assert result[0]["sUnit"] == "m/s"
        assert result[1]["sName"] == "Port2.accel"

    def test_save_and_load_config(
        self, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        config = {"SSignals": [{"sName": "test"}], "SBirdseye": []}
        path = str(tmp_path / "test_config.json")

        wrapper.save_config(config, path)
        loaded = wrapper.load_config(path)

        assert loaded == config


# ------------------------------------------------------------------
# Bartender
# ------------------------------------------------------------------


class TestBartender:
    def test_raises_if_folder_missing(self, wrapper: PlotStrWrapper) -> None:
        with pytest.raises(FileNotFoundError, match="Data folder not found"):
            wrapper.run_bartender(
                bartender_class="bartender.AEB_E3", data_folder="nope"
            )

    @patch("src.tools.plotstr_wrapper.subprocess.run")
    def test_run_bartender_success(
        self, mock_run: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        mock_run.return_value = MagicMock(
            returncode=0, stdout="2 activations found", stderr=""
        )

        result = wrapper.run_bartender(
            bartender_class="bartender.AEB_E3",
            data_folder=str(data_dir),
            cut_shots=True,
            write_table=True,
            data_type=2,
        )

        assert "activations" in result or result  # MATLAB returns stdout
        mock_run.assert_called_once()

    def test_list_bartender_classes(
        self, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        # Create fake +bartender dir structure
        bart_dir = tmp_path / "plotstr_root" / "+bartender"
        bart_dir.mkdir(parents=True, exist_ok=True)
        (bart_dir / "AbstractBartender.m").touch()
        (bart_dir / "Template.m").touch()
        (bart_dir / "AEB_E3.m").touch()
        (bart_dir / "Ldp.m").touch()
        br223 = bart_dir / "+BR223"
        br223.mkdir()
        (br223 / "SearchAllTrucks.m").touch()

        classes = wrapper.list_bartender_classes()

        assert "bartender.AEB_E3" in classes
        assert "bartender.Ldp" in classes
        assert "bartender.BR223.SearchAllTrucks" in classes
        # Skip abstract/template
        assert "bartender.AbstractBartender" not in classes
        assert "bartender.Template" not in classes


# ------------------------------------------------------------------
# Custom signal generation
# ------------------------------------------------------------------


class TestCustomSignalGenerator:
    def test_list_generators(self, wrapper: PlotStrWrapper, tmp_path: Path) -> None:
        cs_dir = tmp_path / "plotstr_root" / "+CustomSignals"
        cs_dir.mkdir(parents=True, exist_ok=True)
        (cs_dir / "CustomSignalGenerator.m").touch()
        br223 = cs_dir / "+BR223"
        br223.mkdir()
        (br223 / "CrossingDetection.m").touch()
        (br223 / "DetectFalsePositives.m").touch()

        generators = wrapper.list_custom_signal_generators(str(cs_dir))

        assert "BR223.CrossingDetection" in generators
        assert "BR223.DetectFalsePositives" in generators
        # CustomSignalGenerator.m itself should be excluded
        assert "CustomSignalGenerator" not in generators


# ------------------------------------------------------------------
# Bookmarks
# ------------------------------------------------------------------


class TestBookmarks:
    @patch("src.tools.plotstr_wrapper.sio.loadmat")
    def test_read_bookmarks_empty(
        self, mock_loadmat: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "test.mat"
        mat_file.touch()
        mock_loadmat.return_value = {"bookmarks": np.array([])}

        result = wrapper.read_bookmarks(str(mat_file))
        assert result == []

    @patch("src.tools.plotstr_wrapper.sio.loadmat")
    def test_read_bookmarks_with_data(
        self, mock_loadmat: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "test.mat"
        mat_file.touch()

        bm_data = np.array(
            [[1, "lane departure", 15000.0], [2, "AEB activation", 23500.0]],
            dtype=object,
        )
        mock_loadmat.return_value = {"bookmarks": bm_data}

        result = wrapper.read_bookmarks(str(mat_file))
        assert len(result) == 2
        assert result[0]["text"] == "lane departure"
        assert result[1]["timestamp_ms"] == 23500.0


# ------------------------------------------------------------------
# Video compression
# ------------------------------------------------------------------


class TestCompressVideos:
    def test_raises_if_dir_missing(self, wrapper: PlotStrWrapper) -> None:
        with pytest.raises(FileNotFoundError, match="Input directory not found"):
            wrapper.compress_videos(input_dir="nonexistent")

    @patch("src.tools.plotstr_wrapper.subprocess.run")
    def test_compress_success(
        self, mock_run: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        (tmp_path / "video1.avi").touch()
        (tmp_path / "video2.avi").touch()
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = wrapper.compress_videos(input_dir=str(tmp_path))

        assert len(result) == 2
        assert mock_run.call_count == 2


# ------------------------------------------------------------------
# ZIP extraction
# ------------------------------------------------------------------


class TestExtractArchives:
    def test_raises_if_dir_missing(self, wrapper: PlotStrWrapper) -> None:
        with pytest.raises(FileNotFoundError, match="Input directory not found"):
            wrapper.extract_archives(input_dir="nonexistent")

    def test_extract_zip(self, wrapper: PlotStrWrapper, tmp_path: Path) -> None:
        import zipfile

        # Create a test zip
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("signal_data.txt", "some data")

        out_dir = tmp_path / "extracted"
        result = wrapper.extract_archives(
            input_dir=str(tmp_path),
            output_dir=str(out_dir),
        )

        assert len(result) == 1
        assert (out_dir / "signal_data.txt").is_file()


# ------------------------------------------------------------------
# Selena filter
# ------------------------------------------------------------------


class TestSelenaFilter:
    def test_list_filters(self, wrapper: PlotStrWrapper, tmp_path: Path) -> None:
        filt_dir = tmp_path / "plotstr_root" / "selena_filter"
        filt_dir.mkdir(parents=True, exist_ok=True)
        (filt_dir / "FCT_Focus.filter").touch()
        (filt_dir / "PER_Heavy.filter").touch()

        filters = wrapper.list_selena_filters()
        assert "FCT_Focus.filter" in filters
        assert "PER_Heavy.filter" in filters

    def test_apply_filter(self, wrapper: PlotStrWrapper, tmp_path: Path) -> None:
        filt_dir = tmp_path / "plotstr_root" / "selena_filter"
        filt_dir.mkdir(parents=True, exist_ok=True)
        filt_file = filt_dir / "test.filter"
        filt_file.write_text("include .*Speed.*\ninclude .*Accel.*\n", encoding="utf-8")

        signals = [
            "Port1.VehicleSpeed_mps",
            "Port1.AccelPedal",
            "Port2.SteeringAngle",
            "Port2.BrakeStatus",
        ]

        filtered = wrapper.apply_selena_filter(signals, "test")
        assert "Port1.VehicleSpeed_mps" in filtered
        assert "Port1.AccelPedal" in filtered
        assert "Port2.SteeringAngle" not in filtered


# ------------------------------------------------------------------
# Batch signal reading
# ------------------------------------------------------------------


class TestBatchSignalRead:
    @patch("src.tools.plotstr_wrapper.sio.loadmat")
    def test_read_signals_batch(
        self, mock_loadmat: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "test.mat"
        mat_file.touch()

        port_dtype = np.dtype([("time", "O"), ("speed", "O"), ("accel", "O")])
        port_data = np.zeros(1, dtype=port_dtype)
        mock_loadmat.return_value = {"Port1": port_data}

        result = wrapper.read_signals_batch(
            str(mat_file),
            ["Port1.speed", "Port1.accel", "Port1.nonexist", "BadFormat"],
        )

        assert "Port1.speed" in result
        assert "Port1.accel" in result
        assert "Port1.nonexist" not in result
        assert "BadFormat" not in result

    @patch("src.tools.plotstr_wrapper.sio.loadmat")
    def test_list_ports(
        self, mock_loadmat: MagicMock, wrapper: PlotStrWrapper, tmp_path: Path
    ) -> None:
        mat_file = tmp_path / "test.mat"
        mat_file.touch()

        port_dtype = np.dtype([("time", "O"), ("sig", "O")])
        mock_loadmat.return_value = {
            "__header__": b"",
            "Port_A": np.zeros(1, dtype=port_dtype),
            "Port_B": np.zeros(1, dtype=port_dtype),
            "bookmarks": np.array([]),
        }

        ports = wrapper.list_ports(str(mat_file))
        assert ports == ["Port_A", "Port_B"]
