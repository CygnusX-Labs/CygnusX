import asyncio,json
import acceptance_common as c
from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider

async def main():
    c.budget.STEP='production_extraction_route_diagnostic_synthetic_prompt'
    provider=LiteLLMProvider();config=await provider._get_config()
    r={'synthetic_prompt_only':True,'configured_model':c.get_settings().memory_extraction_model,'selected_provider':config.name,'provider_model':config.model,'production_config_modified':False}
    try:
        response=await provider.chat([{'role':'user','content':'这是合成验收诊断。仅返回 JSON 空数组 []。'}],model=c.get_settings().memory_extraction_model,temperature=0)
        r.update(status='request_succeeded',choice_present=bool(response.get('choices')))
    except Exception as exc:
        r.update(status='request_failed',error_type=type(exc).__name__,http_status=getattr(exc,'status_code',None),model_rejection_message=any(s in str(exc).lower() for s in ['model not exist','model does not exist','invalid model','model_not_found','model is not available','model name']))
    c.save('production-extraction-route.json',r)
    print(json.dumps(r))
asyncio.run(main())
