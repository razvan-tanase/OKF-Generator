from __future__ import annotations
import hashlib, json
from pathlib import Path
from okf_generator.synthesis_provider import ProviderResult

SOURCE_ID='paper'
SNAPSHOT_ID='sha256-'+'a'*64
RULESET='builtin-v1'
EXTRACT='builtin-v1'
NORMALIZE='builtin-v1'


def norm_dir(root: Path) -> Path:
    return root/SOURCE_ID/SNAPSHOT_ID/RULESET/EXTRACT/NORMALIZE


def make_unit(i: int, text: str='alpha', *, anchor: str|None=None):
    source_uri=f'okf-source:{SOURCE_ID}'
    version=f'{source_uri}@{SNAPSHOT_ID}'
    anchor=anchor or f'{version}#a{i:04d}'
    return {
        'unit_id':f'u{i:06d}','anchor_id':f'a{i:04d}','source_uri':source_uri,
        'source_version_uri':version,'anchor_uri':anchor,'source_path':f'p{i}.txt','kind':'text-document',
        'text':text,'data':{},'native_locator':{'path':f'p{i}.txt'},'metadata':{},'diagnostics':[],
        'content_sha256':hashlib.sha256(text.encode()).hexdigest(),
    }


def write_normalized(root: Path, units, *, diagnostic_count=0):
    d=norm_dir(root); d.mkdir(parents=True,exist_ok=True)
    units_text=''.join(json.dumps(u,sort_keys=True,separators=(',',':'))+'\n' for u in units)
    (d/'units.jsonl').write_text(units_text)
    source_uri=f'okf-source:{SOURCE_ID}'; version=f'{source_uri}@{SNAPSHOT_ID}'
    manifest={
        'schema_version':'0.1','stage':'05-normalize','profile':NORMALIZE,'source_id':SOURCE_ID,'snapshot_id':SNAPSHOT_ID,
        'classification_ruleset':RULESET,'extraction_profile':EXTRACT,'extraction_manifest_sha256':'1'*64,
        'extraction_units_sha256':'2'*64,'source_uri':source_uri,'source_version_uri':version,'anchor_basis':'native-locator-v1',
        'text_normalization':'unicode-nfc+lf-v1','units_path':'units.jsonl','units_sha256':hashlib.sha256(units_text.encode()).hexdigest(),
        'unit_count':len(units),'diagnostic_count':diagnostic_count,'diagnostics':[],
    }
    (d/'normalization.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return manifest

class FakeProvider:
    name='fixture'
    def __init__(self, outputs, mutate=None): self.outputs=list(outputs); self.calls=[]; self.mutate=mutate
    def generate(self, request):
        self.calls.append(request)
        if self.mutate: self.mutate(len(self.calls))
        output=self.outputs[len(self.calls)-1]
        return ProviderResult(output=output,response_id=f'resp-{len(self.calls)}',resolved_model=request.model,usage={'input_tokens':10,'output_tokens':5})

def output_for(anchor, *, concepts=True):
    return {
        'summaries':[{'text':'Summary','evidence_anchors':[anchor]}],
        'concepts':([{'name':'Alpha','description':'An alpha concept','evidence_anchors':[anchor]}] if concepts else []),
        'claims':[{'statement':'Alpha exists','evidence_anchors':[anchor]}],
        'relations':[],
    }
