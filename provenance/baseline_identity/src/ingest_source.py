"""Convert the LAMOST DR10 v2 LRS FITS catalogue to chunked Parquet.

Identifiers are written as strings so integer identifiers are never routed
through floating point. Numeric measurements remain numeric. The conversion
requires the downloader's source-provenance record before opening the source.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# The project keeps optional ingestion dependencies in its local .deps folder.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_LOCAL_DEPS = _PROJECT_ROOT / ".deps"
if _LOCAL_DEPS.is_dir() and str(_LOCAL_DEPS) not in sys.path:
    sys.path.insert(0, str(_LOCAL_DEPS))

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from astropy.io import fits

DEFAULT_SOURCE = _PROJECT_ROOT / "raw" / "dr10_v2.0_LRS_catalogue.fits"
DEFAULT_OUTPUT = _PROJECT_ROOT / "raw" / "catalog.parquet"
DEFAULT_PROVENANCE = _PROJECT_ROOT / "audit" / "source_provenance.json"
DEFAULT_SCHEMA_REPORT = _PROJECT_ROOT / "audit" / "fits_schema.json"
DEFAULT_CHUNK_SIZE = 200_000

# These are catalogue identifiers, even where the FITS representation is
# integral. Keep all exact lexical values; in particular ps_id may exceed 2^53.
IDENTIFIER_COLUMNS = frozenset({
    "obsid", "uid", "gp_id", "designation", "planid", "ps_id",
    "gaia_source_id",
})


def _require_provenance(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"source provenance is required before reading the FITS table: {path}"
        )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"source provenance is unreadable or invalid JSON: {path}") from exc
    if not isinstance(record, dict):
        raise ValueError("source provenance must be a JSON object")
    return record


def _native_array(values: np.ndarray) -> np.ndarray:
    """Convert FITS big-endian numeric arrays to native byte order losslessly."""
    arr = np.asarray(values)
    if arr.dtype.kind in "iuf" and not arr.dtype.isnative:
        return arr.byteswap().view(arr.dtype.newbyteorder("="))
    return arr


def _decode_identifier(values: np.ndarray) -> list[str]:
    """Decode/strip string IDs and stringify integral IDs without float casts."""
    arr = np.asarray(values)
    if arr.dtype.kind in "SUO":
        result: list[str] = []
        for value in arr:
            if isinstance(value, (bytes, np.bytes_)):
                decoded = bytes(value).decode("ascii", errors="strict")
            else:
                decoded = str(value)
            result.append(decoded.strip())
        return result
    if arr.dtype.kind in "iu":
        return [str(int(value)) for value in arr]
    raise TypeError(f"identifier column has unsupported FITS dtype {arr.dtype}")


def _arrow_type_for_column(name: str, dtype: np.dtype) -> pa.DataType:
    if name in IDENTIFIER_COLUMNS:
        return pa.string()
    if dtype.kind in "SUO":
        return pa.string()
    if dtype.kind not in "iuf":
        raise TypeError(f"unsupported column {name!r} with FITS dtype {dtype}")
    native = dtype.newbyteorder("=")
    return pa.from_numpy_dtype(native)


def _arrow_column(name: str, values: np.ndarray, arrow_type: pa.DataType) -> pa.Array:
    if name in IDENTIFIER_COLUMNS:
        return pa.array(_decode_identifier(values), type=pa.string())
    arr = np.asarray(values)
    if arrow_type == pa.string():
        return pa.array(_decode_identifier(arr), type=pa.string())
    return pa.array(_native_array(arr), type=arrow_type, from_pandas=False)


def convert_fits_to_parquet(
    source: str | Path = DEFAULT_SOURCE,
    output: str | Path = DEFAULT_OUTPUT,
    *,
    provenance_path: str | Path = DEFAULT_PROVENANCE,
    schema_report_path: str | Path = DEFAULT_SCHEMA_REPORT,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Stream a FITS binary table into a Zstandard-compressed Parquet file.

    The source is opened only after a provenance JSON record is present. The
    table is read in ``chunk_size`` row slices via Astropy's memory mapping.
    An output temp file is atomically renamed only after all rows are written.
    """
    source = Path(source)
    output = Path(output)
    provenance_path = Path(provenance_path)
    schema_report_path = Path(schema_report_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    provenance = _require_provenance(provenance_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    schema_report_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(output.name + ".partial")
    if temp_output.exists():
        temp_output.unlink()

    writer: pq.ParquetWriter | None = None
    rows_written = 0
    header_report: dict[str, Any] | None = None
    try:
        with fits.open(source, mode="readonly", memmap=True, lazy_load_hdus=True) as hdus:
            table_hdu = next(
                (hdu for hdu in hdus if isinstance(hdu, fits.BinTableHDU)), None
            )
            if table_hdu is None:
                raise ValueError(f"no FITS binary table found in {source}")
            header = table_hdu.header
            names = list(table_hdu.columns.names)
            nrows = int(header["NAXIS2"])
            if nrows != int(table_hdu.data.shape[0]):
                raise ValueError("FITS header row count does not match table data")
            columns = table_hdu.columns
            # Probe only one record to avoid Astropy decoding/caching every
            # string column across all 11M rows when determining Arrow types.
            data_probe = table_hdu.data[:1]
            field_dtypes = {
                name: np.asarray(data_probe[name]).dtype
                for name in names
            }
            types = {
                name: _arrow_type_for_column(name, field_dtypes[name])
                for name in names
            }
            schema = pa.schema([pa.field(name, types[name]) for name in names])
            header_report = {
                "source_file": source.name,
                "source_provenance": str(provenance_path),
                "source_sha256": provenance.get("sha256"),
                "hdu_index": hdus.index_of(table_hdu),
                "hdu_name": header.get("EXTNAME"),
                "row_count_header": nrows,
                "row_width_bytes": int(header["NAXIS1"]),
                "field_count_header": int(header["TFIELDS"]),
                "identifier_columns_written_as_string": [n for n in names if n in IDENTIFIER_COLUMNS],
                "columns": [
                    {
                        "name": name,
                        "fits_format": str(columns[name].format),
                        "fits_unit": columns[name].unit,
                        "fits_dtype": str(field_dtypes[name]),
                        "parquet_type": str(types[name]),
                    }
                    for name in names
                ],
                "parquet_compression": "zstd",
                "chunk_size_rows": int(chunk_size),
            }
            writer = pq.ParquetWriter(temp_output, schema, compression="zstd")
            table_data = table_hdu.data
            next_progress = 1_000_000
            for start in range(0, nrows, chunk_size):
                stop = min(start + chunk_size, nrows)
                chunk = table_data[start:stop]
                record_batch = pa.record_batch(
                    [
                        _arrow_column(name, chunk[name], types[name])
                        for name in names
                    ],
                    schema=schema,
                )
                writer.write_batch(record_batch)
                rows_written += stop - start
                if rows_written >= next_progress or rows_written == nrows:
                    print(f"Converted {rows_written:,}/{nrows:,} rows", flush=True)
                    while next_progress <= rows_written:
                        next_progress += 1_000_000
            writer.close()
            writer = None
        if rows_written != nrows:
            raise RuntimeError(f"wrote {rows_written:,} rows; expected {nrows:,}")
        os.replace(temp_output, output)
        assert header_report is not None
        header_report["row_count_written"] = rows_written
        header_report["output_file"] = str(output)
        header_report["output_size_bytes"] = output.stat().st_size
        report_tmp = schema_report_path.with_name(schema_report_path.name + ".partial")
        report_tmp.write_text(json.dumps(header_report, indent=2) + "\n", encoding="utf-8")
        os.replace(report_tmp, schema_report_path)
        return header_report
    except Exception:
        if writer is not None:
            writer.close()
        if temp_output.exists():
            temp_output.unlink()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--schema-report", type=Path, default=DEFAULT_SCHEMA_REPORT)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    args = parser.parse_args()
    report = convert_fits_to_parquet(
        args.source,
        args.output,
        provenance_path=args.provenance,
        schema_report_path=args.schema_report,
        chunk_size=args.chunk_size,
    )
    print(json.dumps({
        "rows": report["row_count_written"],
        "columns": report["field_count_header"],
        "output": report["output_file"],
        "schema_report": str(args.schema_report),
    }, indent=2))


if __name__ == "__main__":
    main()
