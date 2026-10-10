import unittest
from pathlib import Path
from meddb import KB
from meddb.rdf import export, BASE, iri
from meddb.terminology import verify_mappings

try:
    from rdflib import Graph, Namespace, URIRef, Literal
    from pyshacl import validate
    HAS_RDF = True
except ImportError:
    HAS_RDF = False

class TerminologyTests(unittest.TestCase):
    def test_mapping_verifier_rejects_wrong_label_and_obsolete(self):
        obo={'version':'test','terms':{'HP:1':{'label':'Fever','obsolete':False}}}
        proposal={'target':'HP:1','target_label':'Fever','relation':'exact'}
        self.assertTrue(verify_mappings(obo,[proposal])[0]['identifier_verified'])
        proposal['target_label']='Vomiting'
        with self.assertRaises(ValueError): verify_mappings(obo,[proposal])
        proposal['target_label']='Fever';obo['terms']['HP:1']['obsolete']=True
        with self.assertRaises(ValueError): verify_mappings(obo,[proposal])
    def test_search_by_standard_code(self):
        self.assertEqual(KB().search("HP:0001945")[0]["id"],"nova:fever")
    def test_draft_mappings_not_exported_by_default(self):
        kb=KB(version="meddb-2026.10.10.3")
        self.assertNotIn('a nova:Mapping',export(kb))
        self.assertEqual(export(kb,True).count('a nova:Mapping'),14)

@unittest.skipUnless(HAS_RDF,'Install requirements-ontology.txt for RDF validation tests')
class SHACLTests(unittest.TestCase):
    def setUp(self):
        self.kb=KB(version="meddb-2026.10.10.3");self.graph=Graph().parse(data=export(self.kb,True),format='turtle')
        root=Path(__file__).resolve().parents[1]
        self.shapes=Graph().parse(root/'ontology/shapes.ttl',format='turtle')
        self.ontology=Graph().parse(root/'ontology/core.ttl',format='turtle')
        self.ns=Namespace(BASE)
        self.claim=URIRef(iri('assertion:001')[1:-1])
    def conforms(self):
        return validate(self.graph,shacl_graph=self.shapes,ont_graph=self.ontology,inference='none',meta_shacl=True)[0]
    def test_full_snapshot_conforms(self): self.assertTrue(self.conforms())
    def test_missing_evidence_rejected(self):
        self.graph.remove((self.claim,self.ns.source,None))
        self.assertFalse(self.conforms())
    def test_wrong_endpoint_rejected(self):
        self.graph.set((self.claim,self.ns.object,URIRef(iri('nova:gallstones')[1:-1])))
        self.assertFalse(self.conforms())
    def test_reviewed_without_reviewer_rejected(self):
        self.graph.set((self.claim,self.ns.reviewStatus,Literal('reviewed')))
        self.assertFalse(self.conforms())
