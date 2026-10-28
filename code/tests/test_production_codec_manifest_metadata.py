from pathlib import Path
import hashlib,json,sys,unittest
STAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/'source'))
import reversible_joblib_codec as codec
MANIFEST_SHA='33b77c51e9671d9365ebf5b06e08c2c63210e3970be96fc2a1d5d7093a8bc20b'
ARCHIVE_SHA='4d4bf0de8c1befd082f5af49f89df842172ba9400f8a66e80b5ebe0a525c6bf4'
ARCHIVE_BYTES=61114853354
class ProductionCodecManifestMetadataTests(unittest.TestCase):
    def test_existing_54_codec_descriptors_and_zip_metadata_validate_without_payload_reads(self):
        manifest_path=STAGE/'manifests/cold_model_store_manifest.json'
        raw=manifest_path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),MANIFEST_SHA)
        manifest=json.loads(raw)
        members=manifest['members'];encoded=[m for m in members if 'storage_encoding' in m]
        self.assertEqual(len(encoded),54)
        records={r['member']:r for r in manifest['zip_records']}
        import joblib.compressor as compressor
        compressor_path=Path(compressor.__file__)
        self.assertEqual(hashlib.sha256(compressor_path.read_bytes()).hexdigest(),codec.SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256)
        for row in encoded:
            info=records[row['archive_member']]
            desc=row['storage_encoding']
            codec._manifest(desc,compressor_path,codec.DEFAULT_MAX_PAYLOAD_BYTES,codec.DEFAULT_MAX_FILE_BYTES)
            self.assertEqual(desc['original_sha256'],row['sha256'])
            self.assertEqual(desc['original_size_bytes'],row['bytes'])
            self.assertEqual(desc['original_crc32'],row['crc32'])
            self.assertEqual(desc['encoded_size_bytes'],info['file_size'])
            self.assertEqual(desc['encoded_crc32'],info['crc32'])
            self.assertEqual(row['header_offset'],info['header_offset'])
        self.assertEqual(manifest['archive_sha256'],ARCHIVE_SHA)
        self.assertEqual(manifest['archive_bytes'],ARCHIVE_BYTES)
        self.assertGreater(manifest['archive_bytes'],max(r['header_offset']+r['file_size'] for r in manifest['zip_records']))
if __name__=='__main__':unittest.main(verbosity=2)
