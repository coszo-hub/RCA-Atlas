import unittest

from clean_data_folder import orientation_chunk, station_chunk


def channel(code, azimuth, start="2014-08-01T00:00:00", end=None, sensor="CMG-6TF", rate=200.0):
    return {"channel_id": f"c_{code}_{azimuth}_{start}", "channel": code, "location": "", "azimuth_deg": azimuth,
            "start_time": start, "end_time": end, "sensor_description": sensor, "sample_rate_hz": rate}


def station(code):
    return {"station_id": f"station_OO_{code}", "network": "OO", "station": code, "name": f"RSN {code}",
            "latitude": 45.9, "longitude": -130.0, "elevation_m": -1500.0, "start_time": "2014-08-01T00:00:00",
            "end_time": None, "source_ids": [f"S_{code}"]}


class OrientationTests(unittest.TestCase):
    def setUp(self):
        self.stations = [station("AXEC2"), station("AXEC3"), station("AXID1")]
        self.channels = {
            "station_OO_AXEC2": [channel("HHN", 0.0), channel("HHE", 90.0), channel("HHZ", 0.0), channel("BK1", 0.0)],
            "station_OO_AXEC3": [channel("EHN", 35.0), channel("EHE", 125.0), channel("EHZ", 0.0)],
            "station_OO_AXID1": [channel("EHN", 0.0), channel("LHN", 35.0, rate=1.0), channel("EHE", 90.0)],
        }

    def test_the_network_chunk_names_the_seismometers_not_aligned_with_north(self):
        text = orientation_chunk(self.stations, self.channels)["text"]
        self.assertIn("Seismometers not at 0° azimuth now (rotated from north): AXEC3 (35°), AXID1 (EHN at 0°; LHN at 35°).", text)
        self.assertIn("Seismometers at 0° azimuth now: AXEC2 (0°).", text)

    def test_orientation_issues_are_metadata_one_sensor_cannot_have_not_a_rotation(self):
        self.channels["station_OO_AXEC3"].append(channel("LHE", 125.0, rate=1.0))
        self.channels["station_OO_AXID1"].append(channel("LHE", 125.0, rate=1.0))
        self.stations.append(station("HYS11"))
        self.channels["station_OO_HYS11"] = [channel("EHN", 0.0), channel("EHE", 125.0)]
        text = orientation_chunk(self.stations, self.channels)["text"]
        self.assertIn("Seismometers with orientation issues now: AXID1 (its north channels disagree: EHN at 0°; LHN at 35°), "
                      "HYS11 (EHN at 0° and EHE at 125° are not 90° apart).", text)   # AXEC3 is rotated, consistently

    def test_a_station_chunk_gives_each_horizontal_azimuth_and_skips_other_instruments(self):
        text = station_chunk(self.stations[0], self.channels["station_OO_AXEC2"])["text"]
        self.assertIn("Horizontal azimuths: HHE at 90°; HHN at 0°.", text)   # BK1 is a temperature channel
        self.assertIn("HHE, HHN, HHZ at 200 Hz", text)

    def test_an_ended_epoch_counts_as_earlier(self):
        chans = {"station_OO_AXEC3": [channel("EHN", 35.0, end="2019-06-25T00:00:00")]}
        text = orientation_chunk([station("AXEC3")], chans)["text"]
        self.assertIn("Earlier seismometer epochs not at 0°: AXEC3 (35°).", text)
        self.assertIn("Seismometers not at 0° azimuth now (rotated from north): none.", text)


if __name__ == "__main__":
    unittest.main()
