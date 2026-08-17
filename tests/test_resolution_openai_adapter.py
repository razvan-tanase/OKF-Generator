import unittest
from okf_generator.resolution_adjudication import OpenAIResolutionAdjudicator, AdjudicationRequest, ADJUDICATION_SCHEMA
from okf_generator.synthesis_provider import ProviderResult

class FakeProvider:
    def __init__(self): self.request=None
    def generate(self, request):
        self.request=request
        return ProviderResult({'decision':'new','internal_id':'','reason':'distinct'},response_id='r',resolved_model='snap',usage={'output_tokens':3})

class OpenAIAdapterTests(unittest.TestCase):
    def test_reuses_strict_stage06_provider_boundary(self):
        provider=FakeProvider(); adj=OpenAIResolutionAdjudicator(provider)
        result=adj.adjudicate(AdjudicationRequest('c1','model-x','{}'))
        self.assertEqual(provider.request.schema,ADJUDICATION_SCHEMA)
        self.assertEqual(provider.request.schema_name,'okf_stage07_adjudication')
        self.assertEqual(provider.request.model,'model-x')
        self.assertEqual(result.resolved_model,'snap')

if __name__=='__main__': unittest.main()
