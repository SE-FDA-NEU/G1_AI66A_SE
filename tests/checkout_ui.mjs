// Run with: node tests/checkout_ui.mjs
// Execute the real page scripts against a small DOM/network test double.
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";

const checkoutSource = await readFile(new URL("../src/web/static/checkout.js", import.meta.url), "utf8");
const confirmationSource = await readFile(new URL("../src/web/static/confirmation.js", import.meta.url), "utf8");
const body = {recipient_name:"Buyer", delivery_address:"123 Main", phone_number:"0912345678"};
function setup(responses, saved = null, script = checkoutSource) {
  const nodes = new Map();
  const element = () => ({hidden:false, disabled:false, textContent:"", children:[],
    handlers:{}, append(child) {this.children.push(child);}, replaceChildren() {this.children=[];},
    addEventListener(name, handler) {this.handlers[name]=handler;}, focus() {}});
  const fields = Object.keys(body).map(name => ({name,value:body[name],disabled:false,focus(){}}));
  for (const field of fields) fields[field.name] = field;
  const form = element(); form.elements=fields; form.reportValidity=()=>true;
  nodes.set("checkout-form",form);
  const storage = new Map(saved ? [["checkout:2",JSON.stringify(saved)]] : []);
  const calls=[], navigations=[];
  const auth = {token:"token"};
  const context = vm.createContext({
    document:{getElementById(id) {if (!nodes.has(id)) nodes.set(id,element()); return nodes.get(id);}, createElement:element},
    localStorage:{getItem:()=>auth.token},
    sessionStorage:{getItem:key=>storage.get(key)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    location:{pathname:"/checkout/confirmation/1",replace:url=>navigations.push(url),assign:url=>navigations.push(url),reload(){navigations.push("reload");}},
    crypto:{randomUUID:()=>"stable-request-key"}, AbortSignal:{timeout:()=>null},
    FormData:class { constructor() {return Object.entries(body)[Symbol.iterator]();} },
    fetch:async(url,options)=> {
      calls.push({url,options});
      const result=responses.shift();
      if (result instanceof Error) throw result;
      assert.ok(result,`Unexpected request: ${url}`);
      return {status:result.status??200,ok:(result.status??200)<400,json:async()=>result.payload};
    }, Intl, console,
  });
  vm.runInContext(script,context);
  return {context,nodes,storage,calls,navigations,auth};
}
const user={payload:{id:2,role:"buyer"}};
const cart={payload:{data:{items:[{name:"Mouse",quantity:1,line_total:100,availability:"available"}],cart_total:100}}};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
let test=setup([user,cart]); await tick();
assert.equal(test.nodes.get("checkout-form").hidden,false);
assert.match(test.nodes.get("summary").children[0].textContent,/Mouse/);
// Save a request before POST, retain it on timeout, and reuse the exact body/key on retry.
vm.runInContext('pending={key:"key",body:'+JSON.stringify(body)+'};sessionStorage.setItem(storageKey,JSON.stringify(pending))',test.context);
// The fixture queue is exhausted: use a fresh fixture with an existing pending request.
test=setup([user,new Error("timeout"),{payload:{data:{id:7}}}],{key:"key",body}); await tick();
await vm.runInContext("submit()",test.context);
assert.ok(test.storage.has("checkout:2")); assert.equal(test.nodes.get("retry").hidden,false);
await vm.runInContext("submit()",test.context);
assert.equal(test.calls[1].options.headers["Idempotency-Key"],"key");
assert.equal(test.calls[1].options.body,test.calls[2].options.body);
assert.equal(test.storage.size,0); assert.deepEqual(test.navigations,["/checkout/confirmation/7"]);
// A definite validation rejection unlocks the form but keeps its values.
test=setup([user,{status:422,payload:{error:{message:"Invalid checkout fields: phone_number."}}}],{key:"key",body}); await tick();
await vm.runInContext("submit()",test.context);
assert.equal(test.nodes.get("checkout-form").elements.phone_number.value,body.phone_number);
assert.equal(test.nodes.get("checkout-form").elements.phone_number.disabled,false);
assert.equal(test.storage.size,0);
// Empty and unavailable carts cannot submit.
for (const items of [[],[{name:"Mouse",quantity:1,line_total:100,availability:"unavailable"}]]) {
  test=setup([user,{payload:{data:{items,cart_total:0}}}]); await tick();
  assert.equal(test.nodes.get("checkout-form").hidden,true);
}
// Receipt retries are GET-only and do not create another order.
const line={product_id:46,product_code:"P-100",product_name:"Mouse",seller_order_id:1,quantity:2,unit_price:100000,line_total:200000};
test=setup([new Error("timeout"),{payload:{data:{id:1,status:"PENDING",total_amount:200000,...body,items:[line]}}}],null,confirmationSource);
await tick(); assert.equal(test.nodes.get("retry").hidden,false);
await vm.runInContext("load()",test.context);
assert.equal(test.calls.length,2);
assert.ok(test.calls.every(call=>call.url==="/api/v1/orders/1" && !call.options.method));
assert.equal(test.nodes.get("status").textContent,"Order placed successfully.");
// Receipt lines name the product and format the purchase price, never "Product #46".
const receiptText=test.nodes.get("receipt").children.map(child=>child.textContent);
assert.ok(receiptText.some(text=>/^Mouse \(P-100\) \u00d7 2 \u00b7 100\.000\s\u20ab each$/.test(text)),receiptText.join(" | "));
assert.ok(receiptText.every(text=>!text.includes("Product #")));
// Another buyer's order, or one that does not exist, explains what to do next.
test=setup([{status:404,payload:{error:{code:"ERR_ORDER_NOT_FOUND",message:"Order not found."}}}],null,confirmationSource);
await tick();
assert.equal(test.nodes.get("status").textContent,"Confirmation unavailable.");
assert.equal(test.nodes.get("error").textContent,"We could not find this order in your account. Check the order link, or continue shopping.");
console.log("Checkout script checks passed: cart states, timeout/replay, validation, receipt retry.");

// An account switch must block both the first POST and a pending-request retry.
for (const isRetry of [false,true]) {
  test=setup(isRetry ? [user] : [user,cart],isRetry ? {key:"key",body} : null);
  await tick();
  const before=test.calls.length;
  test.auth.token="buyer-B-token";
  if (isRetry) await vm.runInContext("submit()",test.context);
  else test.nodes.get("checkout-form").handlers.submit({preventDefault(){}});
  await tick();
  assert.equal(test.calls.length,before,"No POST may use the new account token");
  assert.equal(test.nodes.get("checkout-form").hidden,true);
  assert.match(test.nodes.get("status").textContent,/account.*changed/i);
  if (isRetry) assert.ok(test.storage.has("checkout:2"),"A's pending key must survive");
  else assert.equal(test.storage.size,0,"Do not save a new request under stale context");
  test.nodes.get("retry").handlers.click();
  assert.deepEqual(test.navigations,["reload"]);
}
console.log("Account-switch checks passed for initial submit and retry.");

// US12: the confirmation form shows only selected items at current prices.
const partialCart = {payload:{data:{cart_total:420,selected_total:120,supports_partial_checkout:true,
  items:[{name:"Selected mouse",quantity:1,line_total:120,unit_price:120,price_at_add:100,
    price_changed:true,is_selected:true,availability:"available"},
  {name:"Unselected keyboard",quantity:1,line_total:300,is_selected:false,availability:"unavailable"}]}}};
test=setup([user,partialCart]); await tick();
assert.equal(test.nodes.get("checkout-form").hidden,false);
const selectedSummary=test.nodes.get("summary").children.map(child=>child.textContent).join(" | ");
assert.match(selectedSummary,/Selected mouse/);
assert.ok(!selectedSummary.includes("Unselected keyboard"));
assert.match(selectedSummary,/Price changed:/);
assert.match(selectedSummary,/100/);
assert.match(selectedSummary,/120/);
assert.equal(test.nodes.get("summary").children.at(-1).textContent,
  `Total: ${new Intl.NumberFormat("vi-VN",{style:"currency",currency:"VND"}).format(120)}`);
const noSelection={payload:{data:{cart_total:100,selected_total:0,
  items:[{name:"Mouse",quantity:1,line_total:100,is_selected:false,availability:"available"}]}}};
test=setup([user,noSelection]); await tick();
assert.equal(test.nodes.get("checkout-form").hidden,true);
assert.equal(test.nodes.get("status").textContent,"Select at least one item in your cart.");
console.log("US12 checkout checks passed: selected-only summary, changed price, empty selection.");
