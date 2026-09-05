const assert = require('node:assert/strict');
const vm = require('node:vm');
const script = require('node:fs').readFileSync(0, 'utf8');

async function scenario({dashboardOk = true, postOk = true} = {}) {
  let submit, replaced = false, focused = false;
  const calls = [], token = {value:'test-token'}, name = {value:'Test account'}, button = {disabled:false}, message = {};
  const feedback = {hidden:true, focus(){focused=true;}, scrollIntoView(){}};
  const summary = {innerHTML:'old estimate'}, refreshLink = {hidden:true};
  const form = {id:'contribution-form',querySelector(selector){return {
    '#apify-token':token,'#apify-name':name,'#contribution-message':message,'button[type="submit"]':button,
  }[selector];}};
  const page = {replaceWith(){replaced=true;}};
  const document = {
    addEventListener(type, handler){assert.equal(type,'submit');submit=handler;},
    querySelector(selector){return {
      '.contribute-page':page,'#contribution-feedback':feedback,
      '#contribution-crawl-summary':summary,'#contribution-refresh-link':refreshLink,
    }[selector];},
  };
  vm.runInNewContext(script, {
    document,
    DOMParser: class {parseFromString(){return {querySelector(){return {};}};}},
    location:{reload(){assert.fail('success must not reload and erase feedback');}},
    fetch:async (url, options) => {
      calls.push({url,options});
      if(url==='/auth/apify-contributions')return {ok:postOk,json:async()=>({
        crawlImpact:{message:'感謝你的貢獻！更新頻率已推估由每 6.7 天變成每 6.1 天一次。'},
        crawlHtml:'new estimate',error:'invalid token',
      })};
      assert.equal(url,'/contribute/');
      assert.equal(feedback.hidden,false,'show impact as soon as POST succeeds');
      assert.equal(summary.innerHTML,'new estimate');
      if(!dashboardOk)throw Error('offline');
      return {ok:true,text:async()=>'<section class="contribute-page"></section>'};
    },
  });
  const pending=submit({target:form,preventDefault(){}});
  await submit({target:form,preventDefault(){}});
  await pending;
  assert.equal(calls.filter(call=>call.options.method==='POST').length,1);
  assert.equal(token.value,'');
  assert.equal(button.disabled,false);
  if(postOk){
    assert.equal(feedback.hidden,false);
    assert.match(feedback.textContent,/6.7 天變成每 6.1 天/);
    assert.equal(summary.innerHTML,'new estimate');
    assert.equal(replaced,dashboardOk);
    assert.equal(refreshLink.hidden,dashboardOk);
    assert.equal(focused,true);
  }else{
    assert.equal(feedback.hidden,true);
    assert.equal(message.textContent,'invalid token');
    assert.equal(summary.innerHTML,'old estimate');
  }
}
(async()=>{await scenario();await scenario({dashboardOk:false});await scenario({postOk:false});})()
  .catch(error=>{console.error(error);process.exitCode=1;});
