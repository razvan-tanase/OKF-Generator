from __future__ import annotations
import io, json, unittest, urllib.error
from okf_generator.synthesis_provider import OpenAIResponsesProvider, ProviderRequest
from okf_generator.synthesis_schema import CANDIDATE_SCHEMA, SYSTEM_INSTRUCTIONS
from okf_generator.synthesis_errors import SynthesisError

class FakeHTTPResponse:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def read(self): return json.dumps(self.data).encode()

class ProviderTests(unittest.TestCase):
    def request(self):
        return ProviderRequest('b0001','gpt-test',SYSTEM_INSTRUCTIONS,'{}','okf_stage06_candidates',CANDIDATE_SCHEMA,1000)
    def test_request_uses_store_false_and_strict_schema(self):
        seen={}
        payload={'status':'completed','id':'resp_1','model':'gpt-test-snapshot','usage':{'input_tokens':1},'output':[{'type':'message','content':[{'type':'output_text','text':'{"summaries":[],"concepts":[],"claims":[],"relations":[]}'}]}]}
        def opener(req,timeout):
            seen['body']=json.loads(req.data); seen['auth']=req.headers.get('Authorization'); seen['timeout']=timeout
            return FakeHTTPResponse(payload)
        p=OpenAIResponsesProvider(api_key='secret',timeout=12,opener=opener)
        r=p.generate(self.request())
        self.assertFalse(seen['body']['store']); self.assertTrue(seen['body']['text']['format']['strict'])
        self.assertEqual(seen['body']['text']['format']['type'],'json_schema'); self.assertEqual(seen['auth'],'Bearer secret')
        self.assertEqual(r.response_id,'resp_1'); self.assertEqual(r.resolved_model,'gpt-test-snapshot')
    def test_missing_key_fails(self):
        p=OpenAIResponsesProvider(api_key=None,opener=lambda *a,**k: None); p.api_key=None
        with self.assertRaisesRegex(SynthesisError,'OPENAI_API_KEY'): p.generate(self.request())
    def test_incomplete_response_fails(self):
        p=OpenAIResponsesProvider(api_key='x',opener=lambda *a,**k: FakeHTTPResponse({'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'},'output':[]}))
        with self.assertRaisesRegex(SynthesisError,'did not complete'): p.generate(self.request())
    def test_refusal_fails(self):
        data={'status':'completed','output':[{'content':[{'type':'refusal','refusal':'no'}]}]}
        p=OpenAIResponsesProvider(api_key='x',opener=lambda *a,**k: FakeHTTPResponse(data))
        with self.assertRaisesRegex(SynthesisError,'refused'): p.generate(self.request())
    def test_multiple_output_text_items_fail(self):
        data={'status':'completed','output':[{'content':[{'type':'output_text','text':'{}'},{'type':'output_text','text':'{}'}]}]}
        p=OpenAIResponsesProvider(api_key='x',opener=lambda *a,**k: FakeHTTPResponse(data))
        with self.assertRaisesRegex(SynthesisError,'exactly one'): p.generate(self.request())
    def test_invalid_structured_json_fails(self):
        data={'status':'completed','output':[{'content':[{'type':'output_text','text':'not json'}]}]}
        p=OpenAIResponsesProvider(api_key='x',opener=lambda *a,**k: FakeHTTPResponse(data))
        with self.assertRaisesRegex(SynthesisError,'not valid JSON'): p.generate(self.request())

if __name__=='__main__': unittest.main()
