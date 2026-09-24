import { describe, expect, it } from "vitest";
import { defaultMeasurement } from "./measurement.js";

describe("defaultMeasurement", () => {
  it("picks the sensor's own measurement over co-located CTD variables", () => {
    expect(defaultMeasurement("RS03AXPS-PC03A-4B-PHSENA302", ["sea_water_practical_salinity", "sea_water_pressure", "sea_water_ph_reported_on_total_scale"]))
      .toBe("sea_water_ph_reported_on_total_scale");
    expect(defaultMeasurement("RS03AXPS-SF03A-2A-DOFSTA302", ["depth_reading_profiler_depth_enabled", "moles_of_oxygen_per_unit_mass_in_sea_water_profiler_depth_enabled"]))
      .toBe("moles_of_oxygen_per_unit_mass_in_sea_water_profiler_depth_enabled");
  });
  it("falls back to temperature, then the first variable", () => {
    expect(defaultMeasurement("RS03AXBS-LJ03A-12-CTDPFB301", ["sea_water_pressure", "sea_water_temperature"])).toBe("sea_water_temperature");
    expect(defaultMeasurement("RS03AXBS-LJ03A-99-ZZZZZA301", ["a", "sea_water_temperature"])).toBe("sea_water_temperature");
    expect(defaultMeasurement(null, ["a", "b"])).toBe("a");
  });
});
