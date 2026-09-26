# -*- coding: utf-8 -*-
"""Tests for WebLens core class."""

import pytest

from weblens.config import Config
from weblens.core import WebLens


@pytest.fixture
def eyes(tmp_path):
    config = Config(config_path=tmp_path / "config.yaml")
    return WebLens(config=config)


class TestWebLens:
    def test_init(self, eyes):
        assert eyes.config is not None

    def test_doctor(self, eyes):
        results = eyes.doctor()
        assert isinstance(results, dict)
        assert "web" in results
        assert "github" in results

    def test_doctor_report(self, eyes):
        report = eyes.doctor_report()
        assert isinstance(report, str)
        assert "WebLens" in report
