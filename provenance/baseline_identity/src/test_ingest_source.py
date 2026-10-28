"""Small synthetic FITS checks for safe, chunked source conversion."""
import json
import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / ".deps"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pyarrow.parquet as pq
from astropy.io import fits

from ingest_source import convert_fits_to_parquet


class IngestSourceTests(unittest.TestCase):
    def make_fits(self, path):
        big_id = 9_223_372_036_854_775_000
        cols = [
            fits.Column(name="obsid", format="J", array=np.array([1001, 1002, 1003], dtype=np.int32)),
            fits.Column(name="uid", format="32A", array=np.array([b"G-first ", b"G-second", b"G-third"])),
            fits.Column(name="gp_id", format="K", array=np.array([big_id, big_id + 1, big_id + 2], dtype=np.int64)),
            fits.Column(name="designation", format="19A", array=np.array([b"DESIG-A", b"DESIG-B", b"DESIG-C"])),
            fits.Column(name="obsdate", format="10A", array=np.array([b"2020-01-01"] * 3)),
            fits.Column(name="lmjd", format="J", array=np.array([59000, 59000, 59001], dtype=np.int32)),
            fits.Column(name="mjd", format="J", array=np.array([59000, 59000, 59001], dtype=np.int32)),
            fits.Column(name="planid", format="40A", array=np.array([b"plan-A", b"plan-B", b"plan-C"])),
            fits.Column(name="spid", format="I", array=np.array([1, 2, 3], dtype=np.int16)),
            fits.Column(name="fiberid", format="I", array=np.array([10, 11, 12], dtype=np.int16)),
            fits.Column(name="ra_obs", format="D", array=np.array([1.25, 2.5, 3.75], dtype=np.float64)),
            fits.Column(name="dec_obs", format="D", array=np.array([-1.25, -2.5, -3.75], dtype=np.float64)),
            fits.Column(name="snru", format="E", array=np.array([1, 2, 3], dtype=np.float32)),
            fits.Column(name="snrg", format="E", array=np.array([4, 5, 6], dtype=np.float32)),
            fits.Column(name="snrr", format="E", array=np.array([7, 8, 9], dtype=np.float32)),
            fits.Column(name="snri", format="E", array=np.array([10, 11, 12], dtype=np.float32)),
            fits.Column(name="snrz", format="E", array=np.array([13, 14, 15], dtype=np.float32)),
            fits.Column(name="class", format="20A", array=np.array([b"STAR", b"GALAXY", b"QSO"])),
            fits.Column(name="subclass", format="20A", array=np.array([b"G7", b"", b""])),
            fits.Column(name="z", format="E", array=np.array([0.1, 0.2, 0.3], dtype=np.float32)),
            fits.Column(name="z_err", format="E", array=np.array([0.01, 0.02, 0.03], dtype=np.float32)),
            fits.Column(name="ps_id", format="K", array=np.array([big_id + 10, big_id + 11, big_id + 12], dtype=np.int64)),
            fits.Column(name="mag_ps_g", format="E", array=np.array([15, 16, 17], dtype=np.float32)),
            fits.Column(name="mag_ps_r", format="E", array=np.array([14, 15, 16], dtype=np.float32)),
            fits.Column(name="mag_ps_i", format="E", array=np.array([13, 14, 15], dtype=np.float32)),
            fits.Column(name="mag_ps_z", format="E", array=np.array([12, 13, 14], dtype=np.float32)),
            fits.Column(name="mag_ps_y", format="E", array=np.array([11, 12, 13], dtype=np.float32)),
            fits.Column(name="gaia_source_id", format="25A", array=np.array([b"2676862492063809792", b"0000000000000000002", b"id-3"])),
            fits.Column(name="gaia_g_mean_mag", format="E", array=np.array([15.2, 16.2, 17.2], dtype=np.float32)),
            fits.Column(name="fibertype", format="10A", array=np.array([b"L", b"L", b"B"])),
            fits.Column(name="offsets", format="I", array=np.array([0, 1, 2], dtype=np.int16)),
            fits.Column(name="offsets_v", format="E", array=np.array([0.1, 0.2, 0.3], dtype=np.float32)),
            fits.Column(name="ra", format="D", array=np.array([1.25, 2.5, 3.75], dtype=np.float64)),
            fits.Column(name="dec", format="D", array=np.array([-1.25, -2.5, -3.75], dtype=np.float64)),
            fits.Column(name="fibermask", format="I", array=np.array([0, 1, 2], dtype=np.int16)),
            fits.Column(name="with_norm_flux", format="I", array=np.array([1, 1, 0], dtype=np.int16)),
        ]
        fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(cols)]).writeto(path)
        return str(big_id)

    def test_chunked_conversion_preserves_schema_ids_and_native_numeric_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "tiny.fits"
            output = root / "catalog.parquet"
            provenance = root / "source_provenance.json"
            report_path = root / "audit" / "fits_schema.json"
            big_id = self.make_fits(source)
            provenance.write_text(json.dumps({"sha256": "synthetic"}), encoding="utf-8")

            report = convert_fits_to_parquet(
                source, output, provenance_path=provenance,
                schema_report_path=report_path, chunk_size=2,
            )
            table = pq.read_table(output)
            self.assertEqual(table.num_rows, 3)
            self.assertEqual(table.num_columns, 36)
            self.assertEqual(report["row_count_header"], 3)
            self.assertEqual(report["row_count_written"], 3)
            self.assertEqual(table.schema.field("ps_id").type, __import__("pyarrow").string())
            self.assertEqual(table["ps_id"].to_pylist()[0], str(int(big_id) + 10))
            self.assertEqual(table["gp_id"].to_pylist()[0], big_id)
            self.assertEqual(table["gaia_source_id"].to_pylist()[0], "2676862492063809792")
            self.assertEqual(table["uid"].to_pylist()[0], "G-first")
            self.assertEqual(table.schema.field("mag_ps_g").type, __import__("pyarrow").float32())
            self.assertEqual(table["mag_ps_g"].to_pylist(), [15.0, 16.0, 17.0])
            self.assertEqual(json.loads(report_path.read_text())["field_count_header"], 36)

    def test_requires_provenance_before_opening_fits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "tiny.fits"
            self.make_fits(source)
            with self.assertRaisesRegex(FileNotFoundError, "provenance is required"):
                convert_fits_to_parquet(
                    source, root / "out.parquet", provenance_path=root / "missing.json",
                    schema_report_path=root / "schema.json",
                )


if __name__ == "__main__":
    unittest.main()
