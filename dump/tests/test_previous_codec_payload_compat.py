import hashlib, importlib.util, pathlib, tempfile, unittest, zlib
from unittest.mock import patch
STAGE = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(STAGE / "source"))
import reversible_joblib_codec as current
OLD_PATH = STAGE / "tests/fixtures/reversible_joblib_codec_previous.py"
OLD_SHA = "189b5ab887f47931638cf65aa183239ce077931de0673fc690fcf2c1c86355ca"

def load_previous():
    spec = importlib.util.spec_from_file_location("previous_reversible_joblib_codec", OLD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def zlib3(data):
    c = zlib.compressobj(3, zlib.DEFLATED, zlib.MAX_WBITS, zlib.DEF_MEM_LEVEL, 0)
    return c.compress(data) + c.flush()

class PreviousCodecCompatibilityTests(unittest.TestCase):
    def test_previous_encoded_payload_is_read_exactly_by_current_codec(self):
        self.assertEqual(sha(OLD_PATH), OLD_SHA)
        old = load_previous()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); temp = root / "temp"; temp.mkdir()
            compressor = root / "compressor.py"; compressor.write_text("tiny pinned compressor fixture\n")
            source = root / "source.joblib"; original = zlib3((b"legacy codec fixture\n" * 300) + bytes(range(256)))
            source.write_bytes(original)
            encoded = root / "encoded.xz"
            compressor_sha = sha(compressor)
            with patch.object(old, "SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256", compressor_sha), \
                 patch.object(current, "SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256", compressor_sha):
                manifest = old.encode_file(source, encoded, output_root=root,
                    joblib_compressor_source_path=compressor, max_payload_bytes=1_000_000,
                    max_file_bytes=1_000_000, chunk_bytes=512)
                with current.open_verified(encoded, manifest, temp_root=temp,
                    joblib_compressor_source_path=compressor, max_payload_bytes=1_000_000,
                    max_file_bytes=1_000_000, chunk_bytes=512) as restored:
                    self.assertEqual(restored.read(), original)
                self.assertEqual(manifest["original_sha256"], hashlib.sha256(original).hexdigest())
                self.assertEqual(manifest["original_size_bytes"], len(original))
                self.assertEqual(source.read_bytes(), original)
