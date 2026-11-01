const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const template=fs.readFileSync(require.resolve('../src/panel_template.html'),'utf8');
function functionSource(name,next){return template.slice(template.indexOf(`function ${name}(`),template.indexOf(`function ${next}(`));}
test('zero-revenue products retain their cost and losses',()=>{
  const context={allProducts:[{sku:'FREE',name:'Sample'}]};vm.createContext(context);
  vm.runInContext(functionSource('productMetrics','promotionMetrics'),context);
  const products=context.productMetrics([{sku:'FREE',units:1,gross:0,net:0,margin:-12,after:-12}]);
  assert.equal(products.length,1);assert.equal(products[0].margin,-12);
  assert.equal(products[0].marginPct,null);assert.equal(products[0].afterPct,null);
});
test('variable cost bridge preserves a negative starting margin',()=>{
  const nodes={};
  const context={hasVariable:true,document:{getElementById:id=>nodes[id]||(nodes[id]={})},euro:v=>`EUR ${v}`,pct:String};
  vm.createContext(context);vm.runInContext(functionSource('renderLadder','renderSpotlight'),context);
  context.renderLadder({margin:-20,ship:0,fulfil:5,fees:0,ads:0,after:-25,net:10,afterPerOrder:-25},'Selected view');
  assert.match(nodes.ladder.innerHTML,/EUR -20/);
  assert.match(nodes.ladder.innerHTML,/EUR -25/);
});
test('growth distinguishes missing baseline from genuine flat or falling sales',()=>{
  const context={};vm.createContext(context);vm.runInContext(functionSource('growthRate','sum'),context);
  assert.equal(context.growthRate(100,0),null);
  assert.equal(context.growthRate(0,0),null);
  assert.equal(context.growthRate(100,100),0);
  assert.equal(context.growthRate(0,100),-100);
});
test('undefined free-sample ratios do not create a false margin watch',()=>{
  const nodes={};const context={hasVariable:false,document:{getElementById:id=>nodes[id]||(nodes[id]={})},pct:v=>v==null?'n/a':`${v}%`,euro:String};
  vm.createContext(context);vm.runInContext(functionSource('renderInsight','render'),context);
  context.renderInsight({net:100,margin:50,gross:100},[{name:'Paid',gross:100,margin:50,marginPct:50},{name:'Sample',gross:0,margin:0,marginPct:null}],[],null);
  assert.equal(nodes['insight-title'].textContent,'Largest margin source: Paid');
});
test('negative contribution is explicitly signed rather than clamped in the flow view',()=>{
  const source=fs.readFileSync(require.resolve('../src/publish.py'),'utf8');
  const script=source.split("SANKEY_SCRIPT = r'''<script>")[1].split('</script>')[0];
  const svg={innerHTML:'',setAttribute(){},dispatchEvent(){}};
  const context={window:{},document:{getElementById:()=>svg},Event:class{},esc:String,euro:v=>`EUR ${v}`};
  vm.createContext(context);vm.runInContext(script,context);
  context.window.drawSankey({listed:100,gross:100,net:80,margin:-20,discount:0});
  assert.match(svg.innerHTML,/EUR -20/);assert.match(svg.innerHTML,/-20.0% of list price/);
  assert.match(svg.innerHTML,/Product cost exceeds net revenue/);
});
