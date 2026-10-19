import os
import shutil

import pytest
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLE = os.path.join(ROOT, "data", "sample")
AS_OF = "2026-07-15"
FAIL_KW = "가상 방수 파우치"


@pytest.fixture
def sample_env(tmp_path):
    """샘플 설정을 읽어 출력·DB·로그 경로만 tmp로 돌린 설정 파일을 만든다."""
    cfg = yaml.safe_load(open(os.path.join(SAMPLE, "config.sample.yaml"), encoding="utf-8"))
    cfg["paths"] = {"db_path": str(tmp_path / "out" / "t.db"), "output_dir": str(tmp_path / "out"),
                    "log_dir": str(tmp_path / "out" / "logs")}
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return {"cfg_path": str(cfg_path), "out": tmp_path / "out", "tmp": tmp_path,
            "files": {k: os.path.join(SAMPLE, f"{k}.csv") for k in ("keywords", "competitors", "costs", "trends")}}
