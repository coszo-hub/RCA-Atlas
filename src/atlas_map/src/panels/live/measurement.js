// The measurement a sensor is for, by instrument class (the refdes's fourth part, e.g. PHSENA302 -> PHSEN).
// Many datasets also carry the co-located CTD's temperature and pressure, so "first listed" or "temperature"
// would show a pH sensor's salinity or a fluorometer's depth. Names may carry a "_profiler_depth_enabled" suffix.
const PRIMARY = {
  CTDPF: "sea_water_temperature", DOSTA: "moles_of_oxygen_per_unit_mass_in_sea_water", DOFST: "moles_of_oxygen_per_unit_mass_in_sea_water",
  PHSEN: "sea_water_ph_reported_on_total_scale", FLORT: "mass_concentration_of_chlorophyll_a_in_sea_water",
  FLORD: "mass_concentration_of_chlorophyll_a_in_sea_water", FLNTU: "mass_concentration_of_chlorophyll_a_in_sea_water",
  FLCDR: "concentration_of_colored_dissolved_organic_matter", NUTNR: "mole_concentration_of_nitrate_in_sea_water",
  PCO2W: "partial_pressure_of_carbon_dioxide_in_sea_water", PARAD: "downwelling_photosynthetic_photon_flux_in_sea_water",
  SPKIR: "spectir_490nm", VEL3D: "eastward_sea_water_velocity", VELPT: "eastward_sea_water_velocity", VADCP: "eastward_sea_water_velocity",
  PREST: "sea_water_pressure_at_sea_floor", BOTPT: "botpres", TRHPH: "trhphte_abs", THSPH: "thsphte_th", TMPSF: "tempsfl_01",
};

export function defaultMeasurement(refdes, names) {
  const want = PRIMARY[(refdes ?? "").split("-")[3]?.slice(0, 5)];
  return (want && names.find(n => n.startsWith(want)))
    ?? (names.includes("sea_water_temperature") ? "sea_water_temperature" : names[0]);
}
