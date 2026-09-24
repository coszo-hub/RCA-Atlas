from datetime import datetime, timezone
from pathlib import Path

from atlas_map_gateway.app import Deps
from atlas_map_gateway.bundle_index import BundleIndex
from atlas_map_gateway.config import Settings

FIX = Path(__file__).parent / "fixtures"
SETTINGS = Settings(api_url="http://graphrag.test", api_key="k", bundle_dir=FIX / "bundle")


class FakeNereus:
    def __init__(self, response=None, exc=None):
        self.calls, self.response, self.exc = [], response, exc

    def instrument_status(self, designator):
        self.calls.append(designator)
        if self.exc:
            raise self.exc
        return self.response


class FakeQAQC:
    def __init__(self, response):
        self.calls, self.response = [], response

    def search_plots(self, reference_designator=None, limit=20):
        self.calls.append(reference_designator)
        return self.response


class FakePI:
    def __init__(self, response=None, exc=None):
        self.calls, self.limits, self.response, self.exc = [], [], response, exc

    def browse(self, instrument_id, endpoint_id=None, relative_path="", limit=500):
        self.calls.append((instrument_id, endpoint_id, relative_path))
        self.limits.append(limit)
        if self.exc:
            raise self.exc
        return self.response


class FakeEarthScope:
    def __init__(self, response):
        self.calls, self.response = [], response

    def download_waveform(self, network, station, channel, begin, end, location="--"):
        self.calls.append((network, station, channel, begin, end, location))
        return self.response


def deps(**kw):
    base = dict(index=BundleIndex.from_dir(FIX / "bundle"), nereus=FakeNereus(), qaqc=FakeQAQC({"ok": True, "plots": []}),
                pi=FakePI(), earthscope=FakeEarthScope({"ok": False}), erddap=None, chat=None,
                now=lambda: datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc))
    base.update(kw)
    return Deps(**base)
