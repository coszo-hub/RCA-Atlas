import io
import struct
import unittest

import msgpack

from extract_multidas_mask_metadata import MAGIC, mask_record, parse_header


class MultiDasMaskMetadataTests(unittest.TestCase):
    def test_parses_saved_intervals_from_header_only(self):
        metadata = {"masked": [[0.0, 110000.0], [170000.0, 200000.0]], "dx": 26.4644,
                    "fs2": 7.45058, "gauge": 64, "stream.proc_start": 1767229015.0}
        payload = b"".join((msgpack.packb({"shape": [1, 5289, 32]}, use_bin_type=True),
                            msgpack.packb({}, use_bin_type=True), msgpack.packb(metadata, use_bin_type=True)))
        blob = io.BytesIO(MAGIC + struct.pack("<BII", 1, len(payload), 4096) + payload)
        parsed = parse_header(blob)
        record = mask_record("http://example.org/nokia_DAS_north_sample", parsed, "2026-01-01T00:00:00Z")
        self.assertEqual(record["cable"], "north")
        self.assertEqual(record["saved_unmasked_length_m"], 140000.0)
        self.assertEqual(record["maximum_saved_distance_m"], 200000.0)
        self.assertEqual(record["saved_unmasked_intervals_m"][1]["start_m"], 170000.0)

    def test_rejects_non_multidas_input(self):
        with self.assertRaises(ValueError):
            parse_header(io.BytesIO(b"not-a-das-file"))


if __name__ == "__main__":
    unittest.main()
