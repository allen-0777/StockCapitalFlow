import builtins
from pathlib import Path
import runpy
import sys

import pytest


def test_missing_radar_exits_clearly_before_external_setup(monkeypatch, capsys):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "app.services.zheng2_radar":
            raise ModuleNotFoundError(name=name)
        if name in ("app.models.database", "dotenv") or "telegram" in name:
            pytest.fail(f"Unexpected external setup: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    script = Path(__file__).resolve().parents[1] / "scripts/zheng2_push.py"
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert exc.value.code == 1
    stderr = capsys.readouterr().err
    assert "app.services.zheng2_radar is missing" in stderr
    assert "Push aborted" in stderr
    assert "Traceback" not in stderr
