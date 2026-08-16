import json
import unittest
from drowned_shared.deletion import delete_channel, delete_game


class FakeClient:
    owner='thedrowned925'; repo='drowned1'; branch='main'
    def __init__(self,catalog):
        self.catalog=catalog; self.releases={}; self.tags=set(); self.files=set(); self.deleted_releases=[]; self.deleted_tags=[]; self.deleted_files=[]; self.catalog_writes=0; self.fail_delete=False
    def raw_content(self,path):
        if path=='catalog.json': return json.dumps(self.catalog).encode()
        return b'{}' if path in self.files else None
    def release_by_tag(self,tag): return self.releases.get(tag)
    def delete_release(self,rid):
        if self.fail_delete: raise RuntimeError('network down')
        for tag,release in list(self.releases.items()):
            if release['id']==rid:
                del self.releases[tag]; self.deleted_releases.append(tag); return True
        return False
    def delete_tag_ref(self,tag):
        if tag not in self.tags: return False
        self.tags.remove(tag); self.deleted_tags.append(tag); return True
    def delete_repo_file(self,path,message):
        if path not in self.files: return False
        self.files.remove(path); self.deleted_files.append(path); return True
    def upsert_text(self,path,text,message):
        if path=='catalog.json':
            self.catalog=json.loads(text); self.catalog_writes+=1


def sample_catalog():
    return {'schema_version':1,'updated_at':None,'games':[{
        'id':'demo','title':'Demo Game','platform':'pc','description':'',
        'artwork':{'hero':'https://raw.githubusercontent.com/thedrowned925/drowned1/main/artwork/pc/demo/hero.png'},
        'channels':{
            'stable':{'version':'1.0.0','tag':'pc-demo-v1.0.0-stable','manifest_path':'manifests/pc/demo/stable/1.0.0.json','manifest_url':'https://raw.githubusercontent.com/thedrowned925/drowned1/main/manifests/pc/demo/stable/1.0.0.json','size':10},
            'beta':{'version':'1.1.0','tag':'pc-demo-v1.1.0-beta','manifest_path':'manifests/pc/demo/beta/1.1.0.json','manifest_url':'https://raw.githubusercontent.com/thedrowned925/drowned1/main/manifests/pc/demo/beta/1.1.0.json','size':12}
        }
    }]}


class DeletionTests(unittest.TestCase):
    def make_client(self):
        c=FakeClient(sample_catalog())
        c.releases={'pc-demo-v1.0.0-stable':{'id':1},'pc-demo-v1.1.0-beta':{'id':2}}
        c.tags=set(c.releases)
        c.files={'manifests/pc/demo/stable/1.0.0.json','manifests/pc/demo/beta/1.1.0.json','artwork/pc/demo/hero.png'}
        return c

    def test_delete_channel_keeps_game_and_artwork(self):
        c=self.make_client(); result=delete_channel(c,'demo','pc','beta',log=lambda _:None)
        game=c.catalog['games'][0]
        self.assertEqual(set(game['channels']),{'stable'})
        self.assertIn('artwork/pc/demo/hero.png',c.files)
        self.assertNotIn('manifests/pc/demo/beta/1.1.0.json',c.files)
        self.assertNotIn('pc-demo-v1.1.0-beta',c.tags)
        self.assertEqual(result['channels_removed'],['beta'])
        self.assertEqual(result['tags_deleted'],1)
        self.assertEqual(c.catalog_writes,1)

    def test_delete_game_removes_releases_tags_metadata_artwork_and_catalog(self):
        c=self.make_client(); result=delete_game(c,'demo','pc',log=lambda _:None)
        self.assertEqual(c.catalog['games'],[])
        self.assertEqual(c.releases,{})
        self.assertEqual(c.tags,set())
        self.assertEqual(c.files,set())
        self.assertEqual(result['releases_deleted'],2)
        self.assertEqual(result['tags_deleted'],2)
        self.assertEqual(c.catalog_writes,1)

    def test_failure_does_not_mutate_catalog(self):
        c=self.make_client(); before=json.dumps(c.catalog,sort_keys=True); c.fail_delete=True
        with self.assertRaises(RuntimeError): delete_game(c,'demo','pc',log=lambda _:None)
        self.assertEqual(json.dumps(c.catalog,sort_keys=True),before)
        self.assertEqual(c.catalog_writes,0)

    def test_retry_treats_missing_release_and_manifest_as_already_deleted(self):
        c=self.make_client(); del c.releases['pc-demo-v1.1.0-beta']; c.files.remove('manifests/pc/demo/beta/1.1.0.json')
        delete_channel(c,'demo','pc','beta',log=lambda _:None)
        self.assertEqual(set(c.catalog['games'][0]['channels']),{'stable'})
        self.assertNotIn('pc-demo-v1.1.0-beta',c.tags)


if __name__=='__main__': unittest.main()
