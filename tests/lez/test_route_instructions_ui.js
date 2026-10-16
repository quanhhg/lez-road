// Offline logic tests using small DOM doubles; this is not a browser render test.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");

function node(dataset = {}) {
  const classes = new Set();
  return {
    dataset, events: {}, textContent: "", hidden: false, attrs: {},
    classList: { toggle(k,on) { on ? classes.add(k) : classes.delete(k); }, contains(k) { return classes.has(k); } },
    addEventListener(k,fn) { this.events[k] = fn; },
    setAttribute(k,v) { this.attrs[k] = v; },
    getBoundingClientRect() { return {left:0,top:0,width:1000,height:620}; },
    setPointerCapture() {}, scrollIntoView() {}, appendChild() {},
  };
}
function scripts(text) {
  return [...text.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x=>x[1]);
}
const project = path.resolve(__dirname,"../..");
const template = fs.readFileSync(path.join(project,"scripts/lez/route_instructions_template.html"),"utf8");
const rows = [1,2,3].map(i=>{
  const r=node({step:String(i)});
  r.querySelector = ()=>({textContent:"Chỉ dẫn "+i});
  return r;
});
const markers = [1,2,3].map(i=>node({step:String(i)}));
const overlays = [1,2,3].map(i=>node({step:String(i)}));
const svg=node();
svg.querySelector = selector=>markers.find(m=>selector.includes('"'+m.dataset.step+'"'));
const controls=Object.fromEntries(["current","step-label","previous","next","print","reset"].map(id=>[id,node()]));
const document = {
  querySelector(s) { assert.equal(s,"svg");return svg; },
  querySelectorAll(s) {
    if(s==="tbody tr[data-step]")return rows;
    if(s==="[data-step]")return [...rows,...markers,...overlays];
    if(s===".map-step")return markers;
    throw Error("Unexpected selector: "+s);
  },
  getElementById(id) { assert.ok(controls[id]);return controls[id]; },
};
let printed=0;
vm.runInNewContext(scripts(template).join("\n"),{document,window:{print(){printed++;}}});
assert.equal(controls.current.textContent,"Chỉ dẫn 1");
controls.next.events.click();assert.equal(controls.current.textContent,"Chỉ dẫn 2");
assert.ok(rows[1].classList.contains("selected"));
markers[2].events.keydown({key:"Enter",preventDefault(){}});
assert.equal(controls["step-label"].textContent,"Bước 3 / 3");
controls.previous.events.click();assert.equal(controls.current.textContent,"Chỉ dẫn 2");
rows[0].events.click();assert.equal(controls.current.textContent,"Chỉ dẫn 1");
svg.events.wheel({deltaY:-1,clientX:500,clientY:310,preventDefault(){}});
assert.ok(Number(svg.attrs.viewBox.split(" ")[2])<1000);
controls.reset.events.click();assert.equal(svg.attrs.viewBox,"0 0 1000 620");
controls.print.events.click();assert.equal(printed,1);

const index = process.argv[2] || path.join(project,"maps/route_instructions/index.html");
if(fs.existsSync(index)) {
  const text=fs.readFileSync(index,"utf8");
  const cards=[...text.matchAll(/<article data-zone="([^"]+)"/g)].map(m=>node({zone:m[1]}));
  const filters=["all","A","B","C"].map(filter=>node({filter}));
  const doc={
    querySelectorAll(s) {
      if(s==="[data-filter]")return filters;
      if(s==="article")return cards;
      throw Error("Unexpected selector: "+s);
    },
  };
  vm.runInNewContext(scripts(text).join("\n"),{document:doc});
  assert.equal(cards.length,30);
  filters[1].events.click();assert.equal(cards.filter(x=>!x.hidden).length,10);
  filters[2].events.click();assert.equal(cards.filter(x=>!x.hidden).length,8);
  filters[3].events.click();assert.equal(cards.filter(x=>!x.hidden).length,12);
  filters[0].events.click();assert.equal(cards.filter(x=>!x.hidden).length,30);
}
console.log("T2 UI logic passed: chọn bước, chuyển bước, zoom/reset, in và lọc vùng khi có trang xuất.");
