import assert from 'node:assert/strict';
import vm from 'node:vm';

class Headers {
    constructor(input) { this.values=new Map(input instanceof Headers ? input.values : Object.entries(input || {}).map(([key,value])=>[key.toLowerCase(),value])); }
    set(key,value) { this.values.set(key.toLowerCase(),value); }
    has(key) { return this.values.has(key.toLowerCase()); }
    get(key) { return this.values.get(key.toLowerCase()); }
}
class Request { constructor(url) { this.url=url; this.method='POST'; this.headers=new Headers(); } }
const response=(status,data={})=>({status,ok:status>=200&&status<300,json:async()=>data,clone:()=>response(status,data)});
const flush=async()=>{ for(let n=0;n<20;n++) await Promise.resolve(); };

function harness(source,serve=async()=>response(200)) {
    const listeners={},windowEvents={},calls=[],timers=[];
    const meta={value:'old-token',getAttribute(){return this.value;},setAttribute(_key,value){this.value=value;}};
    const form=(method,action,existing=false)=>({field:existing?{value:'expired-token'}:null,sent:0,
        getAttribute:key=>({method,action}[key]),querySelector(){return this.field;},appendChild(field){this.field=field;},
        requestSubmit(){const event={target:this,prevented:false,preventDefault(){this.prevented=true;}}; listeners.submit(event); if(!event.prevented) this.sent++;}});
    const forms=[form('POST','/account/change',true),form('POST','/login'),form('GET','/search'),form('POST','https://other.example/submit')];
    const document={hidden:false,querySelector:selector=>selector.includes('lifetime')?{getAttribute:()=>3600}:meta,
        querySelectorAll:()=>forms,createElement:()=>({}),addEventListener:(name,fn)=>{listeners[name]=fn;}};
    const window={location:{href:'https://games.example.test/account',origin:'https://games.example.test'},
        addEventListener:(name,fn)=>{windowEvents[name]=fn;},
        fetch:async(input,options)=>{calls.push({input,options});return serve(input,options,calls.length);}};
    vm.runInNewContext(source,{window,document,URL,Headers,Request,WeakSet,
        setInterval:fn=>{timers.push(fn);return 1;}});
    listeners.DOMContentLoaded();
    return {window,document,listeners,windowEvents,calls,meta,forms,timers};
}

export async function run(source) {
    let h=harness(source);
    assert.equal(h.forms[0].field.value,'old-token');
    assert.equal(h.forms[1].field.value,'old-token');
    assert.equal(h.forms[2].field,null);
    assert.equal(h.forms[3].field,null,'Tokens never enter external forms');
    await h.window.fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"amount":10}'});
    assert.equal(h.calls[0].options.headers.get('X-CSRFToken'),'old-token');
    assert.equal(h.calls[0].options.headers.get('Content-Type'),'application/json');
    await h.window.fetch('/api/me');
    assert.equal(h.calls[1].options.headers,undefined);
    await h.window.fetch('https://other.example/action',{method:'POST'});
    assert.equal(h.calls[2].options.headers,undefined);

    h=harness(source,async(input,_options,count)=>input==='/api/security/csrf-token'
        ?response(200,{csrf_token:'new-token'}):response(count===1?400:200,{code:'csrf_rejected'}));
    const done=await h.window.fetch('/api/pay',{method:'POST',body:'{"amount":10}'});
    assert.equal(done.status,200);
    assert.equal(h.calls.length,3);
    assert.equal(h.calls[2].options.headers.get('X-CSRFToken'),'new-token');
    assert.equal(h.calls[2].options.body,'{"amount":10}');
    assert.equal(h.meta.value,'new-token');
    assert.equal(h.forms[0].field.value,'new-token');

    for(const status of [400,500]) {
        h=harness(source,async()=>response(status,{code:'application_error'}));
        await h.window.fetch('/api/pay',{method:'POST'});
        assert.equal(h.calls.length,1,'Application errors never replay a mutation');
    }
    h=harness(source,async()=>{throw new Error('offline');});
    await assert.rejects(h.window.fetch('/api/pay',{method:'POST'}),/offline/);
    assert.equal(h.calls.length,1,'Network failures never replay a mutation');
    h=harness(source,async input=>input==='/api/security/csrf-token'?response(200,{csrf_token:'new-token'}):response(400,{code:'csrf_rejected'}));
    assert.equal((await h.window.fetch('/api/pay',{method:'POST'})).status,400);
    assert.equal(h.calls.length,3,'CSRF recovery attempts at most one retry');

    let finish;
    h=harness(source,()=>new Promise(resolve=>{finish=resolve;}));
    h.listeners.visibilitychange(); h.listeners.visibilitychange();
    assert.equal(h.calls.length,1,'Returning-tab refreshes are deduplicated');
    const event={target:h.forms[0],submitter:null,prevented:false,preventDefault(){this.prevented=true;}};
    h.listeners.submit(event); h.listeners.submit(event);
    assert.equal(event.prevented,true);
    assert.equal(h.forms[0].sent,0);
    finish(response(200,{csrf_token:'renewed'})); await flush();
    assert.equal(h.forms[0].field.value,'renewed');
    assert.equal(h.forms[0].sent,1,'A waiting native form submits only once');

    h=harness(source,async()=>response(400,{code:'csrf_rejected'}));
    await h.window.fetch('/api/upload',{method:'POST',body:{getReader(){}}});
    assert.equal(h.calls.length,1,'Request streams are not replayed');
    await h.window.fetch(new Request('https://games.example.test/api/action'));
    assert.equal(h.calls.length,2,'Request objects with consumed bodies are not replayed');
    h=harness(source,async()=>response(200,{csrf_token:'after-restore'}));
    h.windowEvents.pageshow({persisted:true}); await flush();
    assert.equal(h.meta.value,'after-restore');
    h.document.hidden=true; h.timers[0]();
    assert.equal(h.calls.length,1,'Hidden tabs skip periodic security-token refresh');
    h.document.hidden=false; h.timers[0](); await flush();
    assert.equal(h.calls.length,2);
    h=harness(source,async input=>input==='/api/security/csrf-token'?response(503):response(400,{code:'csrf_rejected'}));
    assert.equal((await h.window.fetch('/api/pay',{method:'POST'})).status,400);
    assert.equal(h.calls.length,2,'Failed token refresh does not resubmit a mutation');
    return {passed:true,checks:32};
}
