// Execute the production address-book script with controlled network and account changes.
import assert from "node:assert/strict";
import vm from "node:vm";
import {setup,tick} from "./checkout_ui.mjs";
const user={payload:{id:2,role:"buyer"}};
const empty={payload:{data:{items:[],selected_total:0}}};
const cart={payload:{data:{items:[{name:"Mouse",quantity:1,line_total:100,is_selected:true,availability:"available"}],selected_total:100}}};
const a={id:1,version:1,recipient_name:"Buyer",phone_number:"0912345678",province:"Hà Nội",district:"Đống Đa",ward:"Láng",detailed_address:"<script>street</script>",is_default:true};
const b={...a,id:2,is_default:false};
const list=rows=>({payload:{data:rows}});
let test=setup([user,empty],null,undefined,[list([b,a])]);await tick();
assert.equal(test.nodes.get("address-book").hidden,false,"Address management works with an empty cart");
assert.equal(test.nodes.get("checkout-form").hidden,true);
assert.equal(test.nodes.get("address-choice").value,"1","Choose default before first ID");
assert.match(test.nodes.get("address-list").children[1].children[0].textContent,/<script>street<\/script>/);
assert.equal(test.nodes.get("manual-delivery").hidden,true);
// No default: use smallest ID even when a response is unsorted.
test=setup([user,cart],null,undefined,[list([b,{...a,is_default:false}])]);await tick();
assert.equal(test.nodes.get("address-choice").value,"1");
// Manual mode and saved mode send exclusive, whitelisted body shapes.
test.nodes.get("address-choice").value="";
test.nodes.get("address-choice").handlers.change();
assert.equal(test.nodes.get("manual-delivery").hidden,false);
assert.equal(test.nodes.get("checkout-form").elements.phone_number.required,true);
// Save form validation retains input and places focus beside backend field errors.
test=setup([user,empty],null,undefined,[list([]),{status:422,payload:{error:{code:"ERR_VALIDATION",message:"Please correct the highlighted fields.",fields:{phone_number:["Phone must contain 7 to 15 digits"]}}}}]);await tick();
test.nodes.get("add-address").handlers.click();
const fields=test.nodes.get("address-form").elements;
for(const name of ["recipient_name","phone_number","province","district","ward","detailed_address"])fields[name].value=a[name];
await test.nodes.get("address-form").handlers.submit({preventDefault(){}});
assert.equal(fields.phone_number["aria-invalid"],"true");
assert.equal(fields.phone_number.focused,true);
assert.equal(fields.province.value,a.province);
assert.equal(test.nodes.get("address-form").hidden,false);
assert.match(test.nodes.get("address-phone_number-error").textContent,/7 to 15/);
// Successful create, edit with version, default and delete/cancel including a bodyless 204.
test=setup([user,empty],null,undefined,[list([]),{status:201,payload:{data:a}},list([a]),{payload:{data:{...a,version:2}}},list([{...a,version:2}]),{status:204},list([])]);await tick();
test.nodes.get("add-address").handlers.click();
for(const name of ["recipient_name","phone_number","province","district","ward","detailed_address"])test.nodes.get("address-form").elements[name].value=a[name];
await test.nodes.get("address-form").handlers.submit({preventDefault(){}});
assert.equal(test.nodes.get("address-list").children.length,1);
assert.equal(test.nodes.get("address-status").textContent,"Address added.");
assert.equal(test.nodes.get("address-choice").focused,true);
let card=test.nodes.get("address-list").children[0];
assert.match(card.children[1]["aria-label"],/Edit address for Buyer at <script>street<\/script>/);
card.children[1].handlers.click();
assert.equal(test.nodes.get("address-form").elements.recipient_name.value,a.recipient_name);
test.nodes.get("cancel-address").handlers.click();
assert.equal(card.children[1].focused,true,"Cancel edit returns to that address's Edit button");
card.children[1].handlers.click();
await test.nodes.get("address-form").handlers.submit({preventDefault(){}});
const put=test.calls.find(call=>call.options.method==="PUT");
assert.equal(JSON.parse(put.options.body).version,1);
card=test.nodes.get("address-list").children[0];
assert.equal(card.children[1].focused,true,"Save restores focus after cards are replaced");
assert.equal(test.nodes.get("address-status").textContent,"Address updated.");
card.children[2].handlers.click();
assert.equal(test.nodes.get("address-delete").hidden,false);
assert.match(test.nodes.get("delete-address-summary").textContent,/<script>street<\/script>/);
assert.ok(test.nodes.get("delete-address-summary").textContent.includes(a.phone_number));
assert.equal(test.nodes.get("cancel-delete").focused,true,"Confirmation focuses the safe action");
test.nodes.get("cancel-delete").handlers.click();
assert.ok(!test.calls.some(call=>call.options.method==="DELETE"));
assert.equal(card.children[2].focused,true,"Cancel delete returns to its triggering address");
assert.equal(test.nodes.get("delete-address-summary").textContent,"");
card.children[2].handlers.click();
await test.nodes.get("confirm-delete").handlers.click();
assert.equal(test.nodes.get("address-list").children.length,0);
assert.equal(test.nodes.get("address-delete").hidden,true);
assert.equal(test.nodes.get("address-status").textContent,"Address deleted.");
assert.equal(test.nodes.get("address-choice").focused,true);
// A failed deletion keeps the card and confirmation available for retry.
test=setup([user,empty],null,undefined,[list([a]),{status:500,payload:{error:{message:"Database unavailable"}}}]);await tick();
test.nodes.get("address-list").children[0].children[2].handlers.click();
await test.nodes.get("confirm-delete").handlers.click();
assert.equal(test.nodes.get("address-list").children.length,1);
assert.equal(test.nodes.get("address-delete").hidden,false);
assert.ok(test.nodes.get("delete-address-summary").textContent.includes(a.phone_number));
assert.equal(test.nodes.get("address-status").focused,true,"A failed action focuses visible feedback");
// Saved-address submit preserves body/key on timeout, even after source deletion/reload.
const pending={key:"frozen",body:{address_id:1,address_version:1}};
test=setup([user,new Error("timeout"),{payload:{data:{id:7}}}],pending);await tick();
await vm.runInContext("submit()",test.context);
assert.equal(test.calls.filter(c=>c.url.startsWith("/api/v1/addresses")).length,0);
assert.equal(test.storage.get("checkout:2"),JSON.stringify(pending));
await vm.runInContext("submit()",test.context);
assert.equal(test.calls[1].options.body,test.calls[2].options.body);
assert.equal(test.calls[1].options.headers["Idempotency-Key"],"frozen");
// Stale version requires explicit selection review; it must not silently checkout a fresh version.
test=setup([user,{status:409,payload:{error:{code:"ERR_ADDRESS_CHANGED",message:"Address changed"}}}],pending,undefined,[list([{...a,version:2}])]);await tick();
await vm.runInContext("submit()",test.context);
assert.equal(test.storage.size,0);
assert.equal(vm.runInContext("reviewRequired",test.context),true);
assert.match(test.nodes.get("error").textContent,/Review/);
test.nodes.get("address-choice").handlers.change();
assert.equal(vm.runInContext("reviewRequired",test.context),false);
// A real submit selects the saved address; the pending state freezes the selection/mutations.
test=setup([user,cart,new Error("timeout")],null,undefined,[list([a])]);await tick();
test.nodes.get("checkout-form").handlers.submit({preventDefault(){}});await tick();
const post=test.calls.find(c=>c.options.method==="POST");
assert.deepEqual(JSON.parse(post.options.body),pending.body);
assert.equal(test.nodes.get("address-choice").disabled,true);
const before=test.calls.length;
test.nodes.get("add-address").handlers.click();
assert.equal(test.calls.length,before);
assert.equal(test.nodes.get("address-form").hidden,true);
// Account changes block CRUD and discard late responses before rendering them.
test=setup([user,empty],null,undefined,[list([a])]);await tick();
test.auth.token="new-buyer";
test.nodes.get("add-address").handlers.click();
assert.equal(test.nodes.get("address-book").hidden,true);
assert.equal(test.nodes.get("address-list").children.length,0);
console.log("US13 address checks passed: selection, CRUD, errors/focus, 204, pending retry, stale review, account isolation.");

// Default is a versioned PATCH; choosing it does not submit an order.
test=setup([user,empty],null,undefined,[list([a,b]),{payload:{data:{...b,is_default:true,version:2}}},list([{...b,is_default:true,version:2},{...a,is_default:false,version:2}])]);await tick();
test.nodes.get("address-list").children[1].children[3].handlers.click();await tick();
const patch=test.calls.find(c=>c.options.method==="PATCH");
assert.equal(patch.url,"/api/v1/addresses/2/default");
assert.deepEqual(JSON.parse(patch.options.body),{version:1});
assert.equal(test.nodes.get("address-list").children[0].children[0].textContent.includes("Default"),true);
assert.equal(test.nodes.get("address-status").textContent,"Default address updated.");
assert.equal(test.nodes.get("address-choice").focused,true);

// While a default change is pending, announce progress and refuse duplicate actions.
let finishDefault;
const savingDefault=new Promise(done=>{finishDefault=done;});
test=setup([user,empty],null,undefined,[list([a,b]),savingDefault,
  list([{...a,is_default:false},{...b,is_default:true,version:2}])]);await tick();
const defaultButton=test.nodes.get("address-list").children[1].children[3];
defaultButton.handlers.click();await tick();
assert.equal(test.nodes.get("address-status").textContent,"Saving address changes...");
assert.equal(defaultButton.disabled,true);
const callsWhileSaving=test.calls.length;
defaultButton.handlers.click();
assert.equal(test.calls.length,callsWhileSaving);
finishDefault({payload:{data:{...b,is_default:true,version:2}}});await tick();
assert.equal(test.nodes.get("address-status").textContent,"Default address updated.");
// Manual submit is a whitelist, regardless of saved-address/form controls elsewhere.
test=setup([user,cart,new Error("timeout")],null,undefined,[list([a])]);await tick();
test.nodes.get("address-choice").value="";test.nodes.get("address-choice").handlers.change();
test.nodes.get("checkout-form").handlers.submit({preventDefault(){}});await tick();
assert.deepEqual(Object.keys(JSON.parse(test.calls.find(c=>c.options.method==="POST").options.body)).sort(),["delivery_address","phone_number","recipient_name"]);
// A late response from the previous account cannot render addresses.
let resolve;
const late=new Promise(done=>{resolve=done;});
test=setup([user,empty],null,undefined,[late]);await tick();
test.auth.token="buyer-B";resolve(list([a]));await tick();
assert.equal(test.nodes.get("address-book").hidden,true);
assert.equal(test.nodes.get("address-list").children.length,0);
console.log("US13 extra checks passed: default PATCH, manual whitelist, frozen selector, late response isolation.");
// Address refresh can fail after a definite checkout rejection without losing the review gate.
test=setup([user,{status:409,payload:{error:{code:"ERR_ADDRESS_CHANGED",message:"Address changed"}}}],pending,undefined,[new Error("Address service timeout")]);await tick();
await vm.runInContext("submit()",test.context);
assert.equal(vm.runInContext("reviewRequired",test.context),true);
assert.equal(test.nodes.get("retry").hidden,false);
assert.match(test.nodes.get("error").textContent,/Reload addresses/);
// The actual Retry button makes exactly one replay; it must not reinitialize auth too.
test=setup([user,new Error("timeout"),{payload:{data:{id:9}}}],pending);await tick();
await test.nodes.get("retry").handlers.click();
assert.equal(test.calls.length,2);
await test.nodes.get("retry").handlers.click();
assert.equal(test.calls.length,3);
assert.equal(test.calls[2].url,"/api/v1/orders");
assert.deepEqual(test.navigations,["/checkout/confirmation/9"]);
