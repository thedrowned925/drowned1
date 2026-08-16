import hashlib
import tempfile
import unittest
from pathlib import Path
from drowned_shared.chunking import ChunkBuilder
from drowned_shared.validation import validate_manifest, parse_catalog
from drowned_shared.errors import ManifestError

class CoreTests(unittest.TestCase):
    def test_chunk_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); src=base/'src'; chunks=base/'chunks'; out=base/'out'; src.mkdir(); out.mkdir()
            data={'a.txt':b'hello'*101,'sub/b.bin':bytes(range(251))*9}
            for name,blob in data.items():
                p=src/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(blob)
            b=ChunkBuilder(src,chunk_size=333); gen=b.build(chunks); built=[]
            while True:
                try: built.append(next(gen))
                except StopIteration as stop: result=stop.value; break
            manifest={'schema_version':1,'game':{},'release':{'owner':'x','repo':'y','tag':'z'},'chunk_size':333,'total_size':result['total_size'],'files':result['files'],'chunks':[x.meta for x in built]}
            validate_manifest(manifest)
            for f in result['files']:
                p=out/f['path']; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b'\0'*f['size'])
            for item in built:
                blob=item.path.read_bytes(); self.assertEqual(hashlib.sha256(blob).hexdigest(),item.meta['sha256'])
                for s in item.meta['segments']:
                    p=out/s['file']
                    with p.open('r+b') as fp:
                        fp.seek(s['file_offset']); fp.write(blob[s['chunk_offset']:s['chunk_offset']+s['length']])
            for name,blob in data.items(): self.assertEqual((out/name).read_bytes(),blob)

    def test_path_traversal_rejected(self):
        m={'schema_version':1,'game':{},'release':{'owner':'x','repo':'y','tag':'z'},'chunk_size':1,'total_size':1,'files':[{'path':'../evil.exe','size':1,'sha256':'0'*64}],'chunks':[]}
        with self.assertRaises(ManifestError): validate_manifest(m)

    def test_overlap_rejected(self):
        m={'schema_version':1,'game':{},'release':{'owner':'x','repo':'y','tag':'z'},'chunk_size':2,'total_size':2,'files':[{'path':'a.bin','size':2,'sha256':'0'*64}],'chunks':[{'name':'c','size':2,'sha256':'0'*64,'segments':[{'file':'a.bin','file_offset':0,'chunk_offset':0,'length':2},{'file':'a.bin','file_offset':1,'chunk_offset':0,'length':1}]}]}
        with self.assertRaises(ManifestError): validate_manifest(m)

    def test_catalog_parser(self):
        self.assertEqual(parse_catalog({'schema_version':1,'games':[]})['games'],[])

if __name__=='__main__': unittest.main()
