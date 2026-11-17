"""Draft minimal prospective change for risk counter failures, NOT applied."""
import ast,copy,difflib,hashlib,json,os
from pathlib import Path

p=Path("core/trade_executor.py")
before=p.read_text()
anchor='''        except Exception:
            pass
        return True


    def _resolve_long_intent_price('''
replacement='''        except Exception as exc:
            # Risk position-count uncertainty must not authorize an OPEN.
            try:
                if self.logger:
                    self.logger.error(
                        "[EXEC][OPEN-BLOCK] risk position count unavailable | "
                        "symbol=%s side=%s error=%s",
                        sym_u, side_norm, type(exc).__name__,
                    )
            except Exception:
                pass
            return False
        return True


    def _resolve_long_intent_price('''
assert before.count(anchor)==1,before.count(anchor)
after=before.replace(anchor,replacement)
compile(after,str(p),"exec")
d=''.join(difflib.unified_diff(before.splitlines(keepends=True),
 after.splitlines(keepends=True),
 fromfile='a/core/trade_executor.py',tofile='b/core/trade_executor.py'))
out=Path('research/results/LONG1_STAGE16_UNAPPLIED_RISK_FAILCLOSED_20261117.diff')
out.write_text(d)
def call_from(src):
 tree=ast.parse(src)
 classes=[n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and
          any(getattr(m,'name',None)=='_evaluate_long_execution_risk_gate' for m in n.body)]
 assert len(classes)==1
 node=next(copy.deepcopy(n) for n in classes[0].body
           if getattr(n,'name',None)=='_evaluate_long_execution_risk_gate')
 node.returns=None;node.decorator_list=[]
 for a in node.args.args+node.args.kwonlyargs:a.annotation=None
 m=ast.Module(body=[node],type_ignores=[]);ast.fix_missing_locations(m)
 ns={'os':os}
 exec(compile(m,'<stage16-risk-method>','exec'),ns)
 return ns[node.name]
old=call_from(before)
new=call_from(after)
class Fake:
 logger=None
 max_open_positions=1
 _get_effective_position=lambda self,s:{}
 _count_open_positions_for_side=lambda self,s: (_ for _ in ()).throw(OSError('not available'))
fake=Fake()
args=dict(symbol='NEARUSDT',side='long',price=3.9,interval='3m',extra={})
assert old(fake,**args) is True
assert new(fake,**args) is False
fake._count_open_positions_for_side=lambda s:0
assert old(fake,**args) is True and new(fake,**args) is True
fake._count_open_positions_for_side=lambda s:1
assert old(fake,**args) is False and new(fake,**args) is False
print(json.dumps({'fault_before':'ALLOW','fault_proposed':'BLOCK',
 'normal_open_same':True,'at_position_cap_same':True,
 'production_file_modified':False,'patch_bytes':len(d),
 'source_sha256':hashlib.sha256(before.encode()).hexdigest()},sort_keys=True))
