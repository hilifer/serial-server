/**
 * Energy dashboard — correct flow directions, square center, V/A/kW on all nodes.
 * Real API data with simulated fallback.
 */

function updateDashClock(){
  const n=new Date();
  const el=document.getElementById('dashClock'),el2=document.getElementById('dashDate');
  if(el)el.textContent=n.toLocaleTimeString('zh-CN',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
  if(el2)el2.textContent=n.toLocaleDateString('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'long'});
}

function getVal(d,k){return d&&d.data&&d.data[k]?d.data[k].value:null}
function fmt(v,d){return v===null||v===undefined?'--':Number(v).toFixed(d===undefined?1:d)}
function setText(id,t){const e=document.getElementById(id);if(e)e.textContent=t}

// Simulated data
const sim={grid:{v:380,i:10,p:47.8},solar:{v:720,i:92,p:66},storage:{v:52,i:-158,p:-25.6},charging:{p:93.4},office:{p:30}};
function rnd(){return Math.floor(Math.random()*100)}
function updateSim(){
  sim.grid.p=+(47+(rnd()-50)*.1).toFixed(1);sim.solar.p=+(60+rnd()*.3).toFixed(1);
  sim.storage.p=+(sim.storage.i>0?25:-25+(rnd()-50)*.2).toFixed(1);
  sim.charging.p=+(90+rnd()*.05).toFixed(1);sim.office.p=+(25+rnd()*.1).toFixed(1);
}

function edgeClass(base,power){
  if(power===null||power===undefined)return base+' dashed idle';
  const a=Math.abs(power);
  if(a<.1)return base+' dashed idle';
  let c=base+' animated';
  if(power<0)c+=' reverse';
  if(a>50)c+=' fast';else if(a<5)c+=' slow';
  return c;
}

let flowPower={grid:0,pv1:0,pv2:0,storage:0,dc:0,ac:0,office:0};

function renderFlowDiagram(){
  const wrap=document.getElementById('flowDiagram');if(!wrap)return;
  const W=wrap.clientWidth||800,H=wrap.clientHeight||500,CX=W/2;

  const topY=H*.15,midY=H*.47,botY=H*.83;
  const d1=W*.30,d2=W*.12,d3=W*.26;
  const R=Math.min(W*.06,H*.09,50);  // responsive radius
  const RB=Math.min(W*.065,H*.095,55);
  const RW=Math.min(W*.09,75),RH=Math.min(H*.06,35); // center SQUARE rect

  const N={
    grid:   {x:CX-d1,y:topY,icon:'⚡',name:'电网',bc:'#ff6b6b',lc:'#ffcc44',r:R},
    pv1:    {x:CX-d2,y:topY,icon:'☀️',name:'光伏1',bc:'#ff9500',lc:'#ffdd55',r:R},
    pv2:    {x:CX+d2,y:topY,icon:'☀️',name:'光伏2',bc:'#ff9500',lc:'#ffdd55',r:R},
    storage:{x:CX+d1,y:topY,icon:'🔋',name:'储能',bc:'#00ffff',lc:'#88ffff',r:R},
    center: {x:CX,y:midY,name:'光储系统',bc:'#3b82f6',isRect:true},
    dc:     {x:CX-d3,y:botY,icon:'🚗',name:'直流充电桩',bc:'#ff9500',lc:'#ffdd55',r:RB},
    ac:     {x:CX,y:botY,icon:'🚗',name:'交流充电桩',bc:'#ff9500',lc:'#ffdd55',r:RB},
    office: {x:CX+d3,y:botY,icon:'💻',name:'办公室',bc:'#4ecdc4',lc:'#bbddff',r:RB},
  };

  // --- Paths ---
  // 电网 → 光储系统 (left side): down then right
  function gridPath(){
    const x=N.grid.x,y1=N.grid.y+R,tx=CX-RW,ty=midY;
    return `M${x},${y1} L${x},${ty} L${tx},${ty}`;
  }
  // 光伏1/2 → 光储系统 (top): down, merge, into top
  function pvPath(node){
    const x=node.x,y1=node.y+R,y2=midY-RH;
    const jy=y1+(y2-y1)*.4;
    if(Math.abs(x-CX)<3)return `M${x},${y1} L${x},${y2}`;
    return `M${x},${y1} L${x},${jy} L${CX},${jy} L${CX},${y2}`;
  }
  // 光储系统 ↔ 储能 (right side, bidirectional): right then up
  function storagePath(){
    const tx=CX+RW,ty=midY,x=N.storage.x,y2=N.storage.y+R;
    return `M${tx},${ty} L${x},${ty} L${x},${y2}`;
  }
  // 光储系统 → bottom nodes: down, junction, split
  function botPath(node){
    const x=node.x,y1=midY+RH,y2=node.y-node.r;
    const jy=y1+(y2-y1)*.45;
    if(Math.abs(x-CX)<3)return `M${CX},${y1} L${x},${y2}`;
    return `M${CX},${y1} L${CX},${jy} L${x},${jy} L${x},${y2}`;
  }

  const edges=[
    {id:'eGrid',path:gridPath(),type:'grid-line',pk:'grid',bidir:true},
    {id:'ePv1',path:pvPath(N.pv1),type:'solar',pk:'pv1'},
    {id:'ePv2',path:pvPath(N.pv2),type:'solar',pk:'pv2'},
    {id:'eStor',path:storagePath(),type:'storage',pk:'storage',bidir:true},
    {id:'eDc',path:botPath(N.dc),type:'charge',pk:'dc'},
    {id:'eAc',path:botPath(N.ac),type:'charge',pk:'ac'},
    {id:'eOff',path:botPath(N.office),type:'office-line',pk:'office'},
  ];

  let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">`;

  // Edges
  edges.forEach(e=>{
    const cls=edgeClass('flow-edge '+e.type,flowPower[e.pk]);
    svg+=`<path id="${e.id}" d="${e.path}" class="${cls}"/>`;
    // Bidirectional edges: faint reverse overlay
    if(e.bidir) svg+=`<path d="${e.path}" class="flow-edge ${e.type} animated reverse" opacity="0.25"/>`;
  });
  // Nodes
  const fs=Math.max(10,Math.min(R*.55,22)); // icon font size
  Object.entries(N).forEach(([k,n])=>{
    const addrMap={pv1:10,pv2:11,grid:1,storage:6,dc:8,ac:3,office:4};
    const addr=addrMap[k];
    const clickStyle=addr?'cursor:pointer':'';
    svg+=`<g class="flow-node-group"${addr?' data-addr="'+addr+'"':''} style="--node-color:${n.bc};${clickStyle}">`;
    if(n.isRect){
      // SQUARE center node
      svg+=`<rect x="${n.x-RW}" y="${n.y-RH}" width="${RW*2}" height="${RH*2}" rx="6" fill="rgba(0,20,60,.9)" stroke="${n.bc}" stroke-width="2"/>`;
      svg+=`<text x="${n.x}" y="${n.y+5}" text-anchor="middle" font-size="${fs*.7}" fill="#00d4ff" font-weight="bold">${n.name}</text>`;
    }else{
      svg+=`<circle cx="${n.x}" cy="${n.y}" r="${n.r}" fill="rgba(0,20,60,.9)" stroke="${n.bc}" stroke-width="2"/>`;
      svg+=`<text x="${n.x}" y="${n.y-n.r*.1}" text-anchor="middle" font-size="${fs}">${n.icon}</text>`;
      svg+=`<text x="${n.x}" y="${n.y+n.r*.45}" text-anchor="middle" font-size="${Math.max(9,fs*.45)}" fill="#fff" font-weight="bold">${n.name}</text>`;
    }
    svg+=`</g>`;
  });

  // Power labels — centered but offset slightly to avoid vertical lines
  const lg=Math.max(14,R*.4);
  const lfs=Math.max(7,Math.min(10,R*.22));
  const lsp=lfs+2;
  const labelOff=R*.8; // horizontal offset to dodge vertical lines
  // 电网: 3 lines (no vertical line below, stays centered)
  svg+=`<text id="fG1" x="${N.grid.x}" y="${N.grid.y+R+lg}" text-anchor="middle" font-size="${lfs}" fill="${N.grid.lc}" font-weight="bold"></text>`;
  svg+=`<text id="fG2" x="${N.grid.x}" y="${N.grid.y+R+lg+lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.grid.lc}" font-weight="bold"></text>`;
  svg+=`<text id="fG3" x="${N.grid.x}" y="${N.grid.y+R+lg+lsp*2}" text-anchor="middle" font-size="${lfs}" fill="${N.grid.lc}" font-weight="bold"></text>`;
  // PV1: offset LEFT to dodge its vertical line going right to center
  svg+=`<text id="fPv1" x="${N.pv1.x-labelOff}" y="${N.pv1.y+R+lg}" text-anchor="middle" font-size="${lfs}" fill="${N.pv1.lc}" font-weight="bold"></text>`;
  // PV2: offset RIGHT to dodge its vertical line going left to center
  svg+=`<text id="fPv2" x="${N.pv2.x+labelOff}" y="${N.pv2.y+R+lg}" text-anchor="middle" font-size="${lfs}" fill="${N.pv2.lc}" font-weight="bold"></text>`;
  // Storage: stays centered (horizontal line goes left, label is below)
  svg+=`<text id="fStor" x="${N.storage.x}" y="${N.storage.y+R+lg}" text-anchor="middle" font-size="${lfs}" fill="${N.storage.lc}" font-weight="bold"></text>`;
  // Bottom nodes: offset LEFT to dodge vertical center line
  const blg=Math.max(12,RB*.3);
  // 直流充电桩: offset left (line comes from center-right)
  svg+=`<text id="fDc8" x="${N.dc.x-labelOff}" y="${N.dc.y-RB-blg-lsp*2}" text-anchor="middle" font-size="${lfs}" fill="${N.dc.lc}" font-weight="bold"></text>`;
  svg+=`<text id="fDc9" x="${N.dc.x-labelOff}" y="${N.dc.y-RB-blg-lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.dc.lc}" font-weight="bold"></text>`;
  svg+=`<text id="fDc" x="${N.dc.x-labelOff}" y="${N.dc.y-RB-blg}" text-anchor="middle" font-size="${lfs}" fill="${N.dc.lc}" font-weight="bold"></text>`;
  // 交流充电桩: offset left (center vertical line goes straight down through it)
  svg+=`<text id="fAcA" x="${N.ac.x-labelOff*1.2}" y="${N.ac.y-RB-blg-lsp*3}" text-anchor="middle" font-size="${lfs}" fill="${N.ac.lc}" font-weight="bold"></text>`;
  svg+=`<text id="fAcB" x="${N.ac.x-labelOff*1.2}" y="${N.ac.y-RB-blg-lsp*2}" text-anchor="middle" font-size="${lfs}" fill="${N.ac.lc}" font-weight="bold"></text>`;
  svg+=`<text id="fAcC" x="${N.ac.x-labelOff*1.2}" y="${N.ac.y-RB-blg-lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.ac.lc}" font-weight="bold"></text>`;
  svg+=`<text id="fAc" x="${N.ac.x-labelOff*1.2}" y="${N.ac.y-RB-blg}" text-anchor="middle" font-size="${lfs}" fill="${N.ac.lc}" font-weight="bold"></text>`;
  // 办公室: stays centered (line comes from left, label is centered)
  svg+=`<text id="fOffVA" x="${N.office.x}" y="${N.office.y-RB-blg-lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.office.lc}" font-weight="bold"></text>`;
  svg+=`<text id="fOff" x="${N.office.x}" y="${N.office.y-RB-blg}" text-anchor="middle" font-size="${lfs}" fill="${N.office.lc}" font-weight="bold"></text>`;

  svg+='</svg>';
  wrap.innerHTML=svg;

  // Click handlers
  wrap.querySelectorAll('[data-addr]').forEach(g=>{
    const a=g.getAttribute('data-addr');
    if(a&&a!=='undefined'&&a!=='')g.addEventListener('click',()=>location.href='/meter.html?addr='+a);
  });
}

function updateEdgeStyles(){
  [['eGrid','flow-edge dashed grid-line',flowPower.grid],
   ['ePv1','flow-edge solar',flowPower.pv1],
   ['ePv2','flow-edge solar',flowPower.pv2],
   ['eStor','flow-edge storage',flowPower.storage],
   ['eDc','flow-edge charge',flowPower.dc],
   ['eAc','flow-edge charge',flowPower.ac],
   ['eOff','flow-edge office-line',flowPower.office]
  ].forEach(([id,base,p])=>{
    const el=document.getElementById(id);
    if(el)el.setAttribute('class',edgeClass(base,p));
  });
}

// ---- Data ----
const meterAddrs=[1,2,3,4,5,6,8,9,10,11];
let allMeterData={},hasRealData=false;

function updateFlowLabels(){
  const real=hasRealData;
  let gP,pv1P,pv2P,sP;

  if(real){
    gP=getVal(allMeterData[1],'power_total');
    pv1P=getVal(allMeterData[10],'power');pv2P=getVal(allMeterData[11],'power');
    sP=getVal(allMeterData[6],'power'); // addr 6 = 电池柜
    const dcP8=getVal(allMeterData[8],'power')||0,dcP9=getVal(allMeterData[9],'power')||0;
    flowPower.dc=Math.abs(dcP8)+Math.abs(dcP9);
    flowPower.ac=Math.abs(getVal(allMeterData[3],'power_total')||0);
    flowPower.office=Math.abs(getVal(allMeterData[4],'power_total')||0);
  }else{
    updateSim();
    gP=sim.grid.p;pv1P=sim.solar.p;pv2P=sim.solar.p;sP=sim.storage.p;
    flowPower.dc=sim.charging.p;flowPower.ac=sim.charging.p;flowPower.office=sim.office.p;
  }
  flowPower.grid=Math.abs(gP||0);flowPower.pv1=Math.abs(pv1P||0);flowPower.pv2=Math.abs(pv2P||0);
  flowPower.storage=sP;
  updateEdgeStyles();

  // Flow labels — correct fields
  const gVa=real?getVal(allMeterData[1],'voltage_a'):sim.grid.v;
  const gVb=real?getVal(allMeterData[1],'voltage_b'):sim.grid.v;
  const gVc=real?getVal(allMeterData[1],'voltage_c'):sim.grid.v;
  const gIa=real?getVal(allMeterData[1],'current_a'):sim.grid.i;
  const gIb=real?getVal(allMeterData[1],'current_b'):sim.grid.i;
  const gIc=real?getVal(allMeterData[1],'current_c'):sim.grid.i;
  // Wide spacing between V and A values so they don't overlap lines
  setText('fG1',fmt(gVa)+'V   '+fmt(gIa)+'A');
  setText('fG2',fmt(gVb)+'V   '+fmt(gIb)+'A');
  setText('fG3',fmt(gVc)+'V   '+fmt(gIc)+'A');

  const pv1V=real?getVal(allMeterData[10],'voltage'):sim.solar.v;
  const pv1I=real?getVal(allMeterData[10],'current'):sim.solar.i;
  const pv2V=real?getVal(allMeterData[11],'voltage'):sim.solar.v;
  const pv2I=real?getVal(allMeterData[11],'current'):sim.solar.i;
  setText('fPv1',fmt(pv1V,0)+'V   '+fmt(Math.abs(pv1I))+'A');
  setText('fPv2',fmt(pv2V,0)+'V   '+fmt(Math.abs(pv2I))+'A');

  const sV=real?getVal(allMeterData[6],'voltage'):sim.storage.v;
  const sI=real?getVal(allMeterData[6],'current'):sim.storage.i;
  setText('fStor',fmt(sV)+'V   '+fmt(sI)+'A');

  // 直流充电桩 (addr 8+9): each shows V/A, combined kW
  const dc8V=real?getVal(allMeterData[8],'voltage'):sim.storage.v;
  const dc8I=real?getVal(allMeterData[8],'current'):0;
  const dc9V=real?getVal(allMeterData[9],'voltage'):sim.storage.v;
  const dc9I=real?getVal(allMeterData[9],'current'):0;
  setText('fDc8','桩1:'+fmt(dc8V)+'V   '+fmt(Math.abs(dc8I))+'A');
  setText('fDc9','桩2:'+fmt(dc9V)+'V   '+fmt(Math.abs(dc9I))+'A');
  setText('fDc','合计:  '+fmt(flowPower.dc)+'kW');

  // 交流充电桩 (addr 3, ADL400): 3-phase V/A + kW
  const acVa=real?getVal(allMeterData[3],'voltage_a'):sim.grid.v;
  const acVb=real?getVal(allMeterData[3],'voltage_b'):sim.grid.v;
  const acVc=real?getVal(allMeterData[3],'voltage_c'):sim.grid.v;
  const acIa=real?getVal(allMeterData[3],'current_a'):0;
  const acIb=real?getVal(allMeterData[3],'current_b'):0;
  const acIc=real?getVal(allMeterData[3],'current_c'):0;
  setText('fAcA',fmt(acVa)+'V '+fmt(Math.abs(acIa))+'A');
  setText('fAcB',fmt(acVb)+'V '+fmt(Math.abs(acIb))+'A');
  setText('fAcC',fmt(acVc)+'V '+fmt(Math.abs(acIc))+'A');
  setText('fAc',flowPower.ac?fmt(flowPower.ac)+'kW':'--kW');

  // 办公室 (addr 4): V/A + kW
  const offV=real?getVal(allMeterData[4],'voltage_a'):sim.grid.v;
  const offI=real?getVal(allMeterData[4],'current_a'):0;
  setText('fOffVA',fmt(offV)+'V '+fmt(Math.abs(offI))+'A');
  setText('fOff',flowPower.office?fmt(flowPower.office)+'kW':'--kW');

  // Right panel
  setText('solarPowerBig',fmt(Math.abs(pv1P||0)+Math.abs(pv2P||0)));
  setText('pv1Voltage',fmt(pv1V)+'V');setText('pv1Current',fmt(Math.abs(pv1I||0))+'A');
  setText('pv2Voltage',fmt(pv2V)+'V');setText('pv2Current',fmt(Math.abs(pv2I||0))+'A');

  updateEnergyCards(real);
}

function updateEnergyCards(real){
  if(real){
    const gF=getVal(allMeterData[1],'energy_forward_total'),gR=getVal(allMeterData[1],'energy_reverse_total');
    setText('gridBuyTotal',fmt(gF,1));
    setText('gridSellTotal',fmt(gR,1));
    const lF=getVal(allMeterData[4],'energy_forward_total'),lC=getVal(allMeterData[4],'energy_combined_total');
    setText('loadMonthE',fmt(lF,1));setText('loadYearE',fmt(lF,1));setText('loadTotalE',fmt(lC||lF,1));
    setText('officeMonthE',fmt(lF,1));setText('officeYearE',fmt(lF,1));setText('officeTotalE',fmt(lC||lF,1));
    const d8=getVal(allMeterData[8],'energy_forward_total')||0;
    const d9=getVal(allMeterData[9],'energy_forward_total')||0;
    setText('dc1MonthE',fmt(d8,1));setText('dc1YearE',fmt(d8,1));setText('dc1TotalE',fmt(d8,1));
    setText('dc2MonthE',fmt(d9,1));setText('dc2YearE',fmt(d9,1));setText('dc2TotalE',fmt(d9,1));
    const aF=getVal(allMeterData[3],'energy_forward_total'),aC=getVal(allMeterData[3],'energy_combined_total');
    setText('acMonthE',fmt(aF,1));setText('acYearE',fmt(aF,1));setText('acTotalE',fmt(aC||aF,1));
    const p1R=getVal(allMeterData[10],'energy_reverse_total'),p2R=getVal(allMeterData[11],'energy_reverse_total');
    setText('pv1MonthE',fmt(p1R,1));setText('pv1YearE',fmt(p1R,1));setText('pv1TotalE',fmt(p1R,1));
    setText('pv2MonthE',fmt(p2R,1));setText('pv2YearE',fmt(p2R,1));setText('pv2TotalE',fmt(p2R,1));
    const bF=getVal(allMeterData[6],'energy_forward_total'),bR=getVal(allMeterData[6],'energy_reverse_total');
    setText('batChargeMonth',fmt(bF,1));setText('batChargeYear',fmt(bF,1));setText('batChargeTotal',fmt(bF,1));
    setText('batDischargeMonth',fmt(bR,1));setText('batDischargeYear',fmt(bR,1));setText('batDischargeTotal',fmt(bR,1));
  }else{
    const v=fmt(sim.grid.p,1),n=fmt(sim.grid.p*8,1);
    ['gridBuyTotal','gridSellTotal','loadMonthE','dc1MonthE','dc2MonthE','acMonthE','officeMonthE','pv1MonthE','pv2MonthE','batChargeMonth','batDischargeMonth'].forEach(id=>setText(id,v));
    ['loadYearE','dc1YearE','dc2YearE','acYearE','officeYearE','pv1YearE','pv2YearE','batChargeYear','batDischargeYear'].forEach(id=>setText(id,n));
    ['loadTotalE','dc1TotalE','dc2TotalE','acTotalE','officeTotalE','pv1TotalE','pv2TotalE','batChargeTotal','batDischargeTotal'].forEach(id=>setText(id,n));
  }
}

async function pollAllMeters(){
  const results=await Promise.all(meterAddrs.map(async addr=>{
    try{const d=await getMeterRealtime(addr);if(d&&d.data){allMeterData[addr]=d;return true}}catch(e){}
    return false;
  }));
  hasRealData=results.some(r=>r);
  updateFlowLabels();
}

document.addEventListener('DOMContentLoaded',()=>{
  updateDashClock();setInterval(updateDashClock,1000);
  renderFlowDiagram();
  window.addEventListener('resize',()=>{renderFlowDiagram();updateFlowLabels()});
  startPolling(pollAllMeters,60000); // 1分钟读一次电表
  setInterval(()=>{if(!hasRealData)updateFlowLabels()},2000);
  setTimeout(updateFlowLabels,300);
});
