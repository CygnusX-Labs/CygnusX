import asyncio,json,traceback
import acceptance_common as c
from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
async def main():
    c.budget.STEP='provider_diagnostic'
    r={}
    p=LiteLLMProvider()
    try:
        config=await p._get_embedding_config()
        r['selected_config']={'id':str(config.id),'active':config.is_active,'default':config.is_default,'key_present':bool(config.api_key),'model':config.model}
        v=await p.embeddings('合成验收向量诊断',model=c.get_settings().agent_memory_embedding_model)
        r['dimensions']=len(v)
    except Exception as e:
        r['error_type']=type(e).__name__
        r['frames']=[{'file':f.filename,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(e.__traceback__)]
        r['message_flags']={s:s.lower() in str(e).lower() for s in ['connection','api_key','provider','decrypt','uuid','settings','proxy','not found']}
    c.save('provider-diagnostic.json',r)
    print(json.dumps(r))
asyncio.run(main())
