"""Offline checks for boundary reconstruction, research rules, source caching and limits."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'scripts'))
from lez.admin_boundaries import stitch_rings, relation_rings, normalized_name
from lez.boundary_proposals import resolve_names, validate_rules
from lez.common import atomic_json, file_hash
from lez.legal_sources import archive_sources


class BoundaryRulesTests(unittest.TestCase):
    def test_unordered_and_reversed_ways_join_by_ids(self):
        self.assertEqual(stitch_rings({10:[1,2],20:[3,2],30:[3,1]}),[[1,2,3,1]])

    def test_multiple_closed_rings_are_preserved(self):
        self.assertEqual(len(stitch_rings({1:[1,2,3,1],2:[4,5,6,4]})),2)

    def test_open_or_branching_edges_are_rejected(self):
        for ways in ({1:[1,2],2:[2,3]}, {1:[1,2],2:[2,3],3:[3,1],4:[2,4]}):
            with self.assertRaisesRegex(ValueError,'Open or ambiguous'):
                stitch_rings(ways)

    def test_missing_member_and_unknown_role_are_not_ignored(self):
        rel={'members':[{'type':'way','ref':1,'role':'outer'}]}
        with self.assertRaisesRegex(ValueError,'Missing boundary way'):
            relation_rings(rel,{}, {})
        rel['members'][0]['role']=''
        with self.assertRaisesRegex(ValueError,'Unsupported boundary member'):
            relation_rings(rel,{1:{'nodes':[1,2,3,1]}}, {1:{},2:{},3:{}})

    def test_inner_members_preserved_and_centres_ignored(self):
        rel={'members':[{'type':'way','ref':1,'role':'outer'},{'type':'way','ref':2,'role':'inner'},
                        {'type':'node','ref':9,'role':'admin_centre'}]}
        rings=relation_rings(rel,{1:{'nodes':[1,2,3,1]},2:{'nodes':[4,5,6,4]}},{i:{} for i in range(1,7)})
        self.assertEqual(len(rings['outer']),1);self.assertEqual(len(rings['inner']),1)

    def test_unicode_names_resolve_to_unique_ids(self):
        self.assertEqual(normalized_name('Phường Văn Miếu – Quốc Tử Giám'),'Văn Miếu - Quốc Tử Giám')
        inventory=[{'name':'Phường Cửa Nam','osm_relation_id':'1'}]
        self.assertEqual(resolve_names(['Cửa Nam'],inventory)[0]['osm_relation_id'],'1')
        with self.assertRaisesRegex(ValueError,'not found'):
            resolve_names(['Cửa Bắc'],inventory)
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            resolve_names(['Cửa Nam'],inventory*2)

    def test_default_draft_cannot_be_activated_implicitly(self):
        rules=json.loads((Path(__file__).resolve().parents[2]/'config/boundary_automation.json').read_text())
        self.assertEqual(len(validate_rules(rules)),15)
        rules['automatic_activation']=True
        with self.assertRaisesRegex(ValueError,'must not activate'):
            validate_rules(rules)

    def test_duplicate_or_mixed_domain_assignments_fail(self):
        rules=json.loads((Path(__file__).resolve().parents[2]/'config/boundary_automation.json').read_text())
        rules['strata'][-1]['names'].append('Hoàn Kiếm')
        with self.assertRaisesRegex(ValueError,'outside'):
            validate_rules(rules)


class SourceArchiveTests(unittest.TestCase):
    def fixture(self, folder):
        root=Path(folder);(root/'config').mkdir();(root/'data/raw/legal').mkdir(parents=True)
        atomic_json(root/'config/legal_pdf_sources.json',{'sources':[{'source_id':'fixture','url':'https://example.test/source.pdf',
                                                                     'fallback_urls':['https://example.test/mirror.pdf']}]})
        return root

    def test_valid_cache_sends_no_request(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.fixture(folder)
            p=root/'data/raw/legal/fixture.pdf';p.write_bytes(b'%PDF-fixture')
            atomic_json(p.with_suffix('.manifest.json'),{'status':'captured','requested_url':'https://example.test/source.pdf','sha256':file_hash(p)})
            with patch('requests.Session.get',side_effect=AssertionError('cache must not send HTTP')):
                self.assertEqual(archive_sources(root)[0]['status'],'captured')

    def test_html_error_falls_back_and_records_failures(self):
        class Response:
            status_code=200;headers={};url='https://example.test/mirror.pdf'
            def __init__(self,raw):self.raw=raw
            def raise_for_status(self):pass
            def iter_content(self,size):yield self.raw
            def close(self):pass
        with tempfile.TemporaryDirectory() as folder:
            root=self.fixture(folder)
            with patch('requests.Session.get',side_effect=[Response(b'<html>error</html>'),Response(b'<html>error</html>'),Response(b'%PDF-fixture')]) as get, patch('lez.legal_sources.time.sleep'):
                result=archive_sources(root)[0]
            self.assertEqual(result['status'],'captured');self.assertEqual(get.call_count,3)
            self.assertEqual(len(result['attempts']),3)
            self.assertEqual(result['retrieved_url'],'https://example.test/mirror.pdf')
            self.assertNotIn('error',result)

    def test_long_429_wait_is_deferred_without_switching_mirror(self):
        class Response:
            status_code=429;headers={'Retry-After':'120'}
            def close(self):pass
        with tempfile.TemporaryDirectory() as folder:
            root=self.fixture(folder)
            with patch('requests.Session.get',return_value=Response()) as get, patch('lez.legal_sources.time.sleep'):
                result=archive_sources(root)[0]
            self.assertEqual(result['status'],'fetch_failed');self.assertEqual(get.call_count,1)
            self.assertIn('later run',result['error'])


if __name__ == '__main__':unittest.main(verbosity=2)
