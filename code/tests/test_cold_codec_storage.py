import hashlib, pathlib, tempfile, unittest, zipfile, zlib, os
from unittest.mock import patch
import sys

STAGE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/'source'))
import reversible_joblib_codec as codec
import cold_codec_storage as storage

def sha(data): return hashlib.sha256(data).hexdigest()
def z3(raw):
    c=zlib.compressobj(3,zlib.DEFLATED,zlib.MAX_WBITS,zlib.DEF_MEM_LEVEL,0)
    return c.compress(raw)+c.flush()

class ColdCodecStorageTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.td.name)
        self.temp=self.root/'tmp';self.temp.mkdir()
        self.raw=(b'cold-store tiny byte fixture; no model payload\n'*300)+bytes(range(256))
        self.original=z3(self.raw)
        self.source=self.root/'source.joblib';self.source.write_bytes(self.original)
        self.compressor=self.root/'compressor.py';self.compressor.write_text('pinned compressor fixture')
        self.patch=patch.object(codec,'SUPPORTED_JOBLIB_COMPRESSOR_SOURCE_SHA256',sha(self.compressor.read_bytes()))
        self.patch.start();self.addCleanup(self.patch.stop)
        self.archive=self.root/'fixture.zip'
        self.payload,self.row=storage.encode_entry_payload(self.source,
            archive_member='runtime_20261025/cold_models/e3/rep_1/pipeline.joblib.'+sha(self.original)+'.zipmember',
            temp_root=self.temp,joblib_compressor_source_path=self.compressor,
            max_payload_bytes=1_000_000,max_file_bytes=1_000_000,chunk_bytes=512)
        with zipfile.ZipFile(self.archive,'w',compression=zipfile.ZIP_STORED) as z:
            self.write_record=storage.append_encoded_payload(z,self.payload,self.row,chunk_bytes=1024)
        with zipfile.ZipFile(self.archive) as z:
            info=z.getinfo(self.row['archive_member'])
            self.row['header_offset']=info.header_offset
            self.info=info
        self.addCleanup(self.td.cleanup)
    def open(self,row=None,**kw):
        return storage.open_logical_member(self.archive,row or self.row,temp_root=self.temp,
            joblib_compressor_source_path=self.compressor,max_payload_bytes=1_000_000,
            max_file_bytes=1_000_000,chunk_bytes=512,**kw)
    def test_writer_reports_physical_identity_and_header(self):
        self.assertEqual(self.write_record['archive_member'],self.row['archive_member'])
        self.assertEqual(self.write_record['header_offset'],self.info.header_offset)
        self.assertEqual(self.write_record['payload_sha256'],self.row['storage_encoding']['encoded_sha256'])
        self.assertEqual(self.write_record['payload_size'],self.info.file_size)
        self.assertEqual(self.write_record['payload_crc32'],self.info.CRC)
    def test_writer_rejects_wrong_payload_before_archive_append(self):
        bad=self.root/'bad.xz';bad.write_bytes(b'wrong bytes')
        target=self.root/'writer-fail.zip'
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as z:
            with self.assertRaises(storage.StorageFormatError):
                storage.append_encoded_payload(z,bad,self.row)
            self.assertEqual(z.namelist(),[])
    def test_codec_roundtrip_returns_exact_original_bytes(self):
        with self.open() as f: self.assertEqual(f.read(),self.original)
        self.assertEqual(self.source.read_bytes(),self.original)
    def test_logical_and_physical_identities_are_separate(self):
        s=storage.logical_stat(self.row,member_info=self.info)
        self.assertEqual(s['sha256'],sha(self.original));self.assertEqual(s['size'],len(self.original))
        self.assertEqual(s['payload_sha256'],sha(self.payload.read_bytes()))
        self.assertEqual(s['payload_size'],self.payload.stat().st_size)
        self.assertNotEqual(s['size'],s['payload_size'])
    def test_legacy_raw_entry_remains_byte_identical(self):
        rawzip=self.root/'legacy.zip';name='runtime_20261025/cold_models/legacy.zipmember'
        with zipfile.ZipFile(rawzip,'w',compression=zipfile.ZIP_STORED) as z:z.writestr(name,self.original)
        with zipfile.ZipFile(rawzip) as z: i=z.getinfo(name)
        row={'archive_member':name,'sha256':sha(self.original),'bytes':len(self.original),
             'crc32':i.CRC,'header_offset':i.header_offset}
        with storage.open_logical_member(rawzip,row,temp_root=self.temp,
              joblib_compressor_source_path=self.compressor) as f:self.assertEqual(f.read(),self.original)
        self.assertEqual(storage.logical_stat(row,member_info=i)['storage_format'],'raw-v1')
    def test_legacy_crc_mismatch_rejected(self):
        row=dict(self.row);row.pop('storage_encoding')
        row.update({'sha256':sha(self.original),'bytes':len(self.original),'crc32':self.info.CRC^1})
        with self.assertRaises(storage.StorageFormatError):
            with self.open(row):pass
    def test_legacy_wrong_logical_sha_rejected(self):
        rawzip=self.root/'legacy2.zip';name='legacy.bin'
        with zipfile.ZipFile(rawzip,'w',compression=zipfile.ZIP_STORED) as z:z.writestr(name,self.original)
        with zipfile.ZipFile(rawzip) as z:i=z.getinfo(name)
        row={'archive_member':name,'sha256':'0'*64,'bytes':len(self.original),'crc32':i.CRC,'header_offset':i.header_offset}
        with self.assertRaises(storage.StorageFormatError):
            with storage.open_logical_member(rawzip,row,temp_root=self.temp,
                  joblib_compressor_source_path=self.compressor):pass
    def test_unknown_codec_rejected(self):
        row=dict(self.row);row['storage_encoding']=dict(row['storage_encoding'],codec_version='future/99')
        with self.assertRaises(codec.UnsupportedCodec):
            with self.open(row):pass
    def test_missing_or_extra_descriptor_field_rejected(self):
        row=dict(self.row);d=dict(row['storage_encoding']);d.pop('zlib_params');row['storage_encoding']=d
        with self.assertRaises(storage.StorageFormatError):
            with self.open(row):pass
        row=dict(self.row);row['storage_encoding']=dict(row['storage_encoding'],surprise=True)
        with self.assertRaises(storage.StorageFormatError):
            with self.open(row):pass
    def test_logical_hash_size_and_crc_mismatches_rejected(self):
        for change in ({'sha256':'0'*64},{'bytes':len(self.original)+1},{'crc32':self.row['crc32']^1}):
            with self.subTest(change=change),self.assertRaises(storage.StorageFormatError):
                with self.open(dict(self.row,**change)):pass
    def test_encoded_hash_and_size_tampering_rejected(self):
        d=dict(self.row['storage_encoding'])
        for change in ({'encoded_sha256':'0'*64},{'encoded_size_bytes':d['encoded_size_bytes']+1}):
            row=dict(self.row);row['storage_encoding']=dict(d,**change)
            with self.subTest(change=change),self.assertRaises(storage.StorageFormatError):
                with self.open(row):pass
    def test_encoded_crc_and_zip_header_mismatch_rejected(self):
        row=dict(self.row);row['storage_encoding']=dict(row['storage_encoding'],encoded_crc32=self.info.CRC^1)
        with self.assertRaises(storage.StorageFormatError):
            with self.open(row):pass
        row=dict(self.row,header_offset=self.row['header_offset']+1)
        with self.assertRaises(storage.StorageFormatError):
            with self.open(row):pass
    def test_deflated_zip_member_rejected(self):
        name=self.row['archive_member'];bad=self.root/'deflated.zip'
        with zipfile.ZipFile(bad,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr(name,self.payload.read_bytes())
        with zipfile.ZipFile(bad) as z:i=z.getinfo(name)
        row=dict(self.row,header_offset=i.header_offset)
        with self.assertRaises(storage.StorageFormatError):
            with storage.open_logical_member(bad,row,temp_root=self.temp,
                    joblib_compressor_source_path=self.compressor,max_payload_bytes=1_000_000,
                    max_file_bytes=1_000_000):pass
    def test_corrupt_encoded_payload_hash_rejected(self):
        row=dict(self.row);row['storage_encoding']=dict(row['storage_encoding'],encoded_sha256='0'*64)
        with self.assertRaises(storage.StorageFormatError):
            with self.open(row):pass
    def test_truncated_xz_with_consistent_outer_crc_is_rejected(self):
        bad=self.root/'truncated.zip';payload=self.payload.read_bytes()[:-8]
        name=self.row['archive_member']
        with zipfile.ZipFile(bad,'w',compression=zipfile.ZIP_STORED) as z:z.writestr(name,payload)
        with zipfile.ZipFile(bad) as z:i=z.getinfo(name)
        d=dict(self.row['storage_encoding'],encoded_sha256=sha(payload),
               encoded_size_bytes=len(payload),encoded_crc32=i.CRC)
        row=dict(self.row,storage_encoding=d,header_offset=i.header_offset)
        with self.assertRaises(codec.CodecError):
            with storage.open_logical_member(bad,row,temp_root=self.temp,
                  joblib_compressor_source_path=self.compressor,max_payload_bytes=1_000_000,
                  max_file_bytes=1_000_000,chunk_bytes=512):pass
    def test_unsupported_runtime_fails_closed(self):
        with patch.object(codec,'SUPPORTED_ZLIB_RUNTIME_VERSION','unsupported'):
            with self.assertRaises(codec.UnsupportedCodec):
                with self.open():pass
    def test_encoded_descriptor_disagrees_with_logical_row_rejected(self):
        row=dict(self.row);row['storage_encoding']=dict(row['storage_encoding'])
        row['storage_encoding']['original_sha256']='f'*64
        with self.assertRaises(storage.StorageFormatError):
            with self.open(row):pass
    def test_invalid_member_path_rejected(self):
        row=dict(self.row,archive_member='../escape')
        with self.assertRaises(storage.StorageFormatError):
            with self.open(row):pass
    def test_source_is_unchanged_and_writer_has_no_unexpected_files(self):
        self.assertEqual(self.source.read_bytes(),self.original)
        names={p.name for p in self.temp.iterdir()}
        self.assertEqual(names,{self.payload.name})
    def test_archive_mutation_during_read_is_detected(self):
        with self.assertRaises(storage.StorageFormatError):
            with self.open() as f:
                self.assertEqual(f.read(),self.original)
                with self.archive.open('ab') as out:out.write(b'changed')
    def test_codec_metadata_does_not_change_legacy_row_interpretation(self):
        row={'archive_member':self.row['archive_member'],'sha256':sha(self.original),
             'bytes':len(self.original),'crc32':self.info.CRC,'header_offset':self.info.header_offset}
        with zipfile.ZipFile(self.archive) as z:
            # This member is XZ, so declaring it legacy raw must fail rather than silently decode it.
            pass
        with self.assertRaises(storage.StorageFormatError):
            with self.open(row):pass

if __name__=='__main__':unittest.main()

