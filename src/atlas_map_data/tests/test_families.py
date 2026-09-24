import unittest

from atlas_map_data import families


class FamilyTableTest(unittest.TestCase):
    def test_every_corpus_type_has_a_family(self):
        corpus_types = [
            "absolute_pressure_gauge", "adcp", "bottom_pressure_recorder", "bottom_pressure_tilt",
            "broadband_seismometer", "camera", "camera_temperature_campaign_system", "ctd", "das",
            "differential_pressure_gauge", "dissolved_gas", "dissolved_oxygen",
            "distributed_fiber_sensing_experiment", "dna_sampler", "fiber_optic_strainmeter",
            "fluid_sampler", "fluorometer", "geodetic_and_seismic_sensor_module", "hpies", "hydrophone",
            "irradiance", "low_frequency_hydrophone", "mass_spectrometer", "nitrate",
            "ocean_bottom_seismic_package", "osmotic_sampler", "par", "pco2", "ph", "pressure",
            "seismometer", "self_calibrating_pressure_recorder", "self_calibrating_pressure_sensor",
            "short_period_seismometer", "sonar", "spectrophotometer", "thermistor", "thermistor_array",
            "thermistor_ph", "three_dimensional_current_meter", "tiltmeter", "velocimeter",
        ]
        for t in corpus_types:
            self.assertIn(families.family_for(t), {f["key"] for f in families.FAMILIES}, t)

    def test_types_the_prototype_misfiled(self):
        self.assertEqual(families.family_for("short_period_seismometer"), "seismic")
        self.assertEqual(families.family_for("distributed_fiber_sensing_experiment"), "fiber")

    def test_unknown_type_fails_loudly(self):
        with self.assertRaises(families.UnknownInstrumentType) as ctx:
            families.family_for("gravimeter")
        self.assertIn("gravimeter", str(ctx.exception))

    def test_family_metadata_matches_spec(self):
        by_key = {f["key"]: f for f in families.FAMILIES}
        self.assertEqual(by_key["seismic"]["color"], "#d95926")
        self.assertEqual(by_key["pressure"]["color"], "#c98500")
        self.assertEqual(by_key["chemistry"]["color"], "#3987e5")
        self.assertEqual(by_key["currents"]["color"], "#199e70")
        self.assertEqual(by_key["acoustic"]["color"], "#d55181")
        self.assertEqual(by_key["fiber"]["color"], "#d9d6cc")
        self.assertEqual(len({f["glyph"] for f in families.FAMILIES}), 6)
        self.assertEqual(list(families.FAMILY_ORDER), [f["key"] for f in families.FAMILIES])


if __name__ == "__main__":
    unittest.main()
