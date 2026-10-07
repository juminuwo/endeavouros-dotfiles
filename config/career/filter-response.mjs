// Only completed but malformed model output is correctable. Transport failures,
// cancellation and incomplete responses must escape without another request.
export class FilterOutputError extends Error {}

export function parseJSON(text) {
  try {
    return JSON.parse(text.trim().replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,''));
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
    throw new FilterOutputError('Response is not valid JSON.');
  }
}

export async function validatedResponse(systemPrompt,payload,parse,complete,signal,label) {
  const abort=()=>{if(signal?.aborted)throw new Error('Filter cancelled.');};
  let correction;
  for(let attempt=0;attempt<2;attempt++) {
    abort();
    const context={systemPrompt,messages:[{role:'user',content:[{type:'text',text:JSON.stringify(payload)}],timestamp:Date.now()}]};
    if(correction)context.messages.push({role:'user',content:[{type:'text',text:correction}],timestamp:Date.now()});
    const response=await complete(context,signal);
    abort();
    if(response.stopReason!=='stop')throw new Error(`Agent filter did not finish (${response.stopReason || 'unknown'}).`);
    const text=response.content.filter(c=>c.type==='text').map(c=>c.text).join('\n');
    try {return parse(text);}
    catch(error) {
      if(!(error instanceof FilterOutputError))throw error;
      if(attempt)throw new Error(`${label} invalid after one corrective retry: ${error.message}`);
      correction=`Your previous response was invalid: ${error.message} Return a complete replacement JSON response following the required schema. Use only exact IDs from the supplied jobs; never guess or shorten IDs. No prose outside JSON.`;
    }
  }
}
