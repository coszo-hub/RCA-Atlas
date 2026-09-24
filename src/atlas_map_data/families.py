"""Instrument type → sensor family. One table; an unknown type is an error, never a default."""
from __future__ import annotations

FAMILIES = [
    {"key": "seismic", "label": "Seismic", "color": "#d95926", "glyph": "triangle"},
    {"key": "pressure", "label": "Pressure & strain", "color": "#c98500", "glyph": "square"},
    {"key": "chemistry", "label": "Water properties", "color": "#3987e5", "glyph": "circle"},
    {"key": "currents", "label": "Currents & light", "color": "#199e70", "glyph": "diamond"},
    {"key": "acoustic", "label": "Sound & imaging", "color": "#d55181", "glyph": "hexagon"},
    {"key": "fiber", "label": "Fiber-optic", "color": "#d9d6cc", "glyph": "bar"},
]
FAMILY_ORDER = {f["key"]: i for i, f in enumerate(FAMILIES)}

_TYPES = {
    "seismic": """seismometer broadband_seismometer short_period_seismometer ocean_bottom_seismic_package
                  geodetic_and_seismic_sensor_module tiltmeter bottom_pressure_tilt""",
    "pressure": """bottom_pressure_recorder pressure absolute_pressure_gauge differential_pressure_gauge
                   self_calibrating_pressure_recorder self_calibrating_pressure_sensor fiber_optic_strainmeter hpies""",
    "chemistry": """ctd dissolved_oxygen ph pco2 nitrate fluorometer spectrophotometer mass_spectrometer
                    dissolved_gas thermistor thermistor_ph thermistor_array osmotic_sampler dna_sampler fluid_sampler""",
    "currents": "adcp velocimeter three_dimensional_current_meter par irradiance",
    "acoustic": "hydrophone low_frequency_hydrophone camera sonar camera_temperature_campaign_system acoustic_ranging_station",
    "fiber": "das distributed_fiber_sensing_experiment",
}
FAMILY_OF_TYPE = {t: fam for fam, types in _TYPES.items() for t in types.split()}


class UnknownInstrumentType(ValueError):
    pass


def family_for(instrument_type: str) -> str:
    try:
        return FAMILY_OF_TYPE[instrument_type]
    except KeyError:
        raise UnknownInstrumentType(
            f"instrument type {instrument_type!r} has no family; add it to atlas_map_data/families.py"
        ) from None
