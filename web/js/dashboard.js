/**
 * Energy dashboard — real API data only, no simulation.
 * Shows -- when data unavailable.
 */

function updateDashClock(){
  const n=new Date();
  const el=document.getElementById('dashClock'),el2=document.getElementById('dashDate');
  if(el)el.textContent=n.toLocaleTimeString('zh-CN',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
  if(el2)el2.textContent=n.toLocaleDateString('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'long'});
}

function getVal(d,k){return d&&d.data&&d.data[k]?d.data[k].value:null}
function fmt(v,d){
  if(v===null||v===undefined)return '--';
  const n=Number(v);
  if(isNaN(n))return '--';
  // Large number formatting
  const a=Math.abs(n);
  if(a>=10000) return (n/10000).toFixed(1)+'万';
  if(a>=1000) return n.toFixed(0);
  return n.toFixed(d===undefined?1:d);
}
function setText(id,t){const e=document.getElementById(id);if(e)e.textContent=t}

function edgeClass(base,power){
  if(power===null||power===undefined||power===0)return base+' dashed idle';
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
  const R=Math.min(W*.06,H*.09,50);
  const RB=Math.min(W*.065,H*.095,55);
  const RW=Math.min(W*.09,75),RH=Math.min(H*.06,35);

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

  function gridPath(){
    const x=N.grid.x,y1=N.grid.y+R,tx=CX-RW,ty=midY;
    return `M${x},${y1} L${x},${ty} L${tx},${ty}`;
  }
  function pvPath(node){
    const x=node.x,y1=node.y+R,y2=midY-RH;
    const jy=y1+(y2-y1)*.4;
    if(Math.abs(x-CX)<3)return `M${x},${y1} L${x},${y2}`;
    return `M${x},${y1} L${x},${jy} L${CX},${jy} L${CX},${y2}`;
  }
  // 光储系统 ↔ 储能 (bidirectional)
  function storagePath(){
    const tx=CX+RW,ty=midY,x=N.storage.x,y2=N.storage.y+R;
    return `M${tx},${ty} L${x},${ty} L${x},${y2}`;
  }
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

  let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
    <defs>
      <marker id="arrow" markerWidth="14" markerHeight="10" refX="7" refY="5" orient="auto" markerUnits="userSpaceOnUse">
        <polygon points="0 0, 14 5, 0 10" fill="#3b82f6" opacity="0.8"/>
      </marker>
      <marker id="arrow-rev" markerWidth="14" markerHeight="10" refX="7" refY="5" orient="auto" markerUnits="userSpaceOnUse">
        <polygon points="14 0, 0 5, 14 10" fill="#3b82f6" opacity="0.8"/>
      </marker>
    </defs>`;

  edges.forEach(e=>{
    const cls=edgeClass('flow-edge '+e.type,flowPower[e.pk]);
    if(e.bidir){
      svg+=`<path id="${e.id}" d="${e.path}" class="${cls}"/>`;
      svg+=`<path d="${e.path}" class="flow-edge ${e.type} animated reverse" opacity="0.25"/>`;
    }else{
      svg+=`<path id="${e.id}" d="${e.path}" class="${cls}"/>`;
    }
  });

  const fs=Math.max(10,Math.min(R*.55,22));
  Object.entries(N).forEach(([k,n])=>{
    const addrMap={pv1:10,pv2:11,grid:1,storage:6,dc:8,ac:3,office:4};
    const addr=addrMap[k];
    const clickStyle=addr?'cursor:pointer':'';
    svg+=`<g class="flow-node-group"${addr?' data-addr="'+addr+'"':''} style="--node-color:${n.bc};${clickStyle}">`;
    if(n.isRect){
      svg+=`<rect x="${n.x-RW}" y="${n.y-RH}" width="${RW*2}" height="${RH*2}" rx="6" fill="rgba(0,20,60,.9)" stroke="${n.bc}" stroke-width="2"/>`;
      svg+=`<text x="${n.x}" y="${n.y+5}" text-anchor="middle" font-size="${fs*.7}" fill="#00d4ff" font-weight="bold">${n.name}</text>`;
    }else{
      svg+=`<circle cx="${n.x}" cy="${n.y}" r="${n.r}" fill="rgba(0,20,60,.9)" stroke="${n.bc}" stroke-width="2"/>`;
      svg+=`<text x="${n.x}" y="${n.y-n.r*.1}" text-anchor="middle" font-size="${fs}">${n.icon}</text>`;
      svg+=`<text x="${n.x}" y="${n.y+n.r*.45}" text-anchor="middle" font-size="${Math.max(9,fs*.45)}" fill="#fff" font-weight="bold">${n.name}</text>`;
    }
    svg+=`</g>`;
  });

  // Labels
  const lg=Math.max(14,R*.4);
  const lfs=Math.max(7,Math.min(10,R*.22));
  const lsp=lfs+2;
  const labelOff=R*.8;
  // Grid 3 lines + power
  svg+=`<text id="fG1" x="${N.grid.x}" y="${N.grid.y+R+lg}" text-anchor="middle" font-size="${lfs}" fill="${N.grid.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fG2" x="${N.grid.x}" y="${N.grid.y+R+lg+lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.grid.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fG3" x="${N.grid.x}" y="${N.grid.y+R+lg+lsp*2}" text-anchor="middle" font-size="${lfs}" fill="${N.grid.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fGP" x="${N.grid.x}" y="${N.grid.y+R+lg+lsp*3}" text-anchor="middle" font-size="${lfs}" fill="${N.grid.lc}" font-weight="bold">--</text>`;
  // PV1 left: V A + power
  svg+=`<text id="fPv1" x="${N.pv1.x-labelOff}" y="${N.pv1.y+R+lg}" text-anchor="middle" font-size="${lfs}" fill="${N.pv1.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fPv1P" x="${N.pv1.x-labelOff}" y="${N.pv1.y+R+lg+lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.pv1.lc}" font-weight="bold">--</text>`;
  // PV2 right: V A + power
  svg+=`<text id="fPv2" x="${N.pv2.x+labelOff}" y="${N.pv2.y+R+lg}" text-anchor="middle" font-size="${lfs}" fill="${N.pv2.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fPv2P" x="${N.pv2.x+labelOff}" y="${N.pv2.y+R+lg+lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.pv2.lc}" font-weight="bold">--</text>`;
  // Storage: V A + power
  svg+=`<text id="fStor" x="${N.storage.x}" y="${N.storage.y+R+lg}" text-anchor="middle" font-size="${lfs}" fill="${N.storage.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fStorP" x="${N.storage.x}" y="${N.storage.y+R+lg+lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.storage.lc}" font-weight="bold">--</text>`;
  // Bottom
  const blg=Math.max(12,RB*.3);
  svg+=`<text id="fDc8" x="${N.dc.x-labelOff}" y="${N.dc.y-RB-blg-lsp*2}" text-anchor="middle" font-size="${lfs}" fill="${N.dc.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fDc9" x="${N.dc.x-labelOff}" y="${N.dc.y-RB-blg-lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.dc.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fDc" x="${N.dc.x-labelOff}" y="${N.dc.y-RB-blg}" text-anchor="middle" font-size="${lfs}" fill="${N.dc.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fAcA" x="${N.ac.x-labelOff*1.2}" y="${N.ac.y-RB-blg-lsp*3}" text-anchor="middle" font-size="${lfs}" fill="${N.ac.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fAcB" x="${N.ac.x-labelOff*1.2}" y="${N.ac.y-RB-blg-lsp*2}" text-anchor="middle" font-size="${lfs}" fill="${N.ac.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fAcC" x="${N.ac.x-labelOff*1.2}" y="${N.ac.y-RB-blg-lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.ac.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fAc" x="${N.ac.x-labelOff*1.2}" y="${N.ac.y-RB-blg}" text-anchor="middle" font-size="${lfs}" fill="${N.ac.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fOffA" x="${N.office.x}" y="${N.office.y-RB-blg-lsp*3}" text-anchor="middle" font-size="${lfs}" fill="${N.office.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fOffB" x="${N.office.x}" y="${N.office.y-RB-blg-lsp*2}" text-anchor="middle" font-size="${lfs}" fill="${N.office.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fOffC" x="${N.office.x}" y="${N.office.y-RB-blg-lsp}" text-anchor="middle" font-size="${lfs}" fill="${N.office.lc}" font-weight="bold">--</text>`;
  svg+=`<text id="fOff" x="${N.office.x}" y="${N.office.y-RB-blg}" text-anchor="middle" font-size="${lfs}" fill="${N.office.lc}" font-weight="bold">--</text>`;

  svg+='</svg>';
  wrap.innerHTML=svg;

  wrap.querySelectorAll('[data-addr]').forEach(g=>{
    const a=g.getAttribute('data-addr');
    if(a&&a!=='undefined')g.addEventListener('click',()=>location.href='/meter.html?addr='+a);
  });
}

function updateEdgeStyles(){
  [['eGrid','flow-edge grid-line',flowPower.grid],
   ['ePv1','flow-edge solar',flowPower.pv1],
   ['ePv2','flow-edge solar',flowPower.pv2],
   ['eStor','flow-edge storage',flowPower.storage],
   ['eDc','flow-edge charge',flowPower.dc],
   ['eAc','flow-edge charge',flowPower.ac],
   ['eOff','flow-edge office-line',flowPower.office]
  ].forEach(([id,base,p])=>{
    const el=document.getElementById(id);
    if(!el)return;
    el.setAttribute('class',edgeClass(base,p));
    // 箭头跟着流动方向：正向=终点，反向=起点，静止=无
    if(p===null||p===undefined||Math.abs(p)<.1){
      el.removeAttribute('marker-end');
      el.removeAttribute('marker-start');
    }else if(p<0){
      el.setAttribute('marker-start','url(#arrow-rev)');
      el.removeAttribute('marker-end');
    }else{
      el.setAttribute('marker-end','url(#arrow)');
      el.removeAttribute('marker-start');
    }
  });
}

// ---- Data ----
const meterAddrs=[1,2,3,4,5,6,8,9,10,11];
let allMeterData={},hasRealData=false;

function updateFlowLabels(){
  if(!hasRealData) return; // No data = keep showing --

  const gP=getVal(allMeterData[1],'power_total');
  const pv1P=getVal(allMeterData[10],'power');
  const pv2P=getVal(allMeterData[11],'power');
  const sP=getVal(allMeterData[6],'power');
  const dcP8=getVal(allMeterData[8],'power')||0,dcP9=getVal(allMeterData[9],'power')||0;

  flowPower.grid=Math.abs(gP||0);
  flowPower.pv1=Math.abs(pv1P||0);
  flowPower.pv2=Math.abs(pv2P||0);
  flowPower.storage=sP||0;
  flowPower.dc=Math.abs(dcP8)+Math.abs(dcP9);
  flowPower.ac=Math.abs(getVal(allMeterData[3],'power_total')||0);
  flowPower.office=Math.abs(getVal(allMeterData[4],'power_total')||0);
  updateEdgeStyles();

  // Grid 3-phase
  const gVa=getVal(allMeterData[1],'voltage_a');
  const gVb=getVal(allMeterData[1],'voltage_b');
  const gVc=getVal(allMeterData[1],'voltage_c');
  const gIa=getVal(allMeterData[1],'current_a');
  const gIb=getVal(allMeterData[1],'current_b');
  const gIc=getVal(allMeterData[1],'current_c');
  const gPt=getVal(allMeterData[1],'power_total');
  setText('fG1',gVa!==null?fmt(gVa)+'V   '+fmt(gIa)+'A':'--');
  setText('fG2',gVb!==null?fmt(gVb)+'V   '+fmt(gIb)+'A':'--');
  setText('fG3',gVc!==null?fmt(gVc)+'V   '+fmt(gIc)+'A':'--');
  setText('fGP',gPt!==null?fmt(gPt)+'kW':'--');

  // PV
  const pv1V=getVal(allMeterData[10],'voltage'),pv1I=getVal(allMeterData[10],'current');
  const pv2V=getVal(allMeterData[11],'voltage'),pv2I=getVal(allMeterData[11],'current');
  const pv1Pwr=getVal(allMeterData[10],'power');
  const pv2Pwr=getVal(allMeterData[11],'power');
  setText('fPv1',pv1V!==null?fmt(pv1V,0)+'V   '+fmt(Math.abs(pv1I))+'A':'--');
  setText('fPv1P',pv1Pwr!==null?fmt(Math.abs(pv1Pwr))+'kW':'--');
  setText('fPv2',pv2V!==null?fmt(pv2V,0)+'V   '+fmt(Math.abs(pv2I))+'A':'--');
  setText('fPv2P',pv2Pwr!==null?fmt(Math.abs(pv2Pwr))+'kW':'--');

  // Storage — current takes absolute value
  const sV=getVal(allMeterData[6],'voltage'),sI=getVal(allMeterData[6],'current');
  const sPwr=getVal(allMeterData[6],'power');
  setText('fStor',sV!==null?fmt(sV)+'V   '+fmt(Math.abs(sI))+'A':'--');
  setText('fStorP',sPwr!==null?fmt(Math.abs(sPwr))+'kW':'--');

  // DC pile
  const dc8V=getVal(allMeterData[8],'voltage'),dc8I=getVal(allMeterData[8],'current');
  const dc9V=getVal(allMeterData[9],'voltage'),dc9I=getVal(allMeterData[9],'current');
  setText('fDc8',dc8V!==null?'桩1:'+fmt(dc8V)+'V   '+fmt(Math.abs(dc8I))+'A':'--');
  setText('fDc9',dc9V!==null?'桩2:'+fmt(dc9V)+'V   '+fmt(Math.abs(dc9I))+'A':'--');
  setText('fDc','合计:  '+fmt(flowPower.dc)+'kW');

  // AC pile 3-phase
  const acVa=getVal(allMeterData[3],'voltage_a'),acIa=getVal(allMeterData[3],'current_a');
  const acVb=getVal(allMeterData[3],'voltage_b'),acIb=getVal(allMeterData[3],'current_b');
  const acVc=getVal(allMeterData[3],'voltage_c'),acIc=getVal(allMeterData[3],'current_c');
  setText('fAcA',acVa!==null?fmt(acVa)+'V   '+fmt(Math.abs(acIa))+'A':'--');
  setText('fAcB',acVb!==null?fmt(acVb)+'V   '+fmt(Math.abs(acIb))+'A':'--');
  setText('fAcC',acVc!==null?fmt(acVc)+'V   '+fmt(Math.abs(acIc))+'A':'--');
  setText('fAc',fmt(flowPower.ac)+'kW');

  // Office (addr 4, ADL400): 3-phase V/A + kW
  const offVa=getVal(allMeterData[4],'voltage_a'),offIa=getVal(allMeterData[4],'current_a');
  const offVb=getVal(allMeterData[4],'voltage_b'),offIb=getVal(allMeterData[4],'current_b');
  const offVc=getVal(allMeterData[4],'voltage_c'),offIc=getVal(allMeterData[4],'current_c');
  setText('fOffA',offVa!==null?fmt(offVa)+'V   '+fmt(Math.abs(offIa))+'A':'--');
  setText('fOffB',offVb!==null?fmt(offVb)+'V   '+fmt(Math.abs(offIb))+'A':'--');
  setText('fOffC',offVc!==null?fmt(offVc)+'V   '+fmt(Math.abs(offIc))+'A':'--');
  setText('fOff',fmt(flowPower.office)+'kW');

  // Solar hero
  setText('solarPowerBig',fmt(Math.abs(pv1P||0)+Math.abs(pv2P||0)));
  setText('pv1Voltage',pv1V!==null?fmt(pv1V)+'V':'--');
  setText('pv1Current',pv1I!==null?fmt(Math.abs(pv1I))+'A':'--');
  setText('pv2Voltage',pv2V!==null?fmt(pv2V)+'V':'--');
  setText('pv2Current',pv2I!==null?fmt(Math.abs(pv2I))+'A':'--');

  updateEnergyCards();
}

function updateEnergyCards(){
  if(!hasRealData) return;

  // 总电量：从 realtime 接口（所有电表都有）
  const gF=getVal(allMeterData[1],'energy_forward_total');
  setText('gridBuyTotal',fmt(gF,1));

  const lF=getVal(allMeterData[4],'energy_forward_total');
  setText('loadTotalE',fmt(lF,1));

  const d8=getVal(allMeterData[8],'energy_forward_total');
  const d9=getVal(allMeterData[9],'energy_forward_total');
  setText('dc1TotalE',fmt(d8,1));
  setText('dc2TotalE',fmt(d9,1));

  const aF=getVal(allMeterData[3],'energy_forward_total');
  setText('acTotalE',fmt(aF,1));

  setText('officeTotalE',fmt(lF,1));

  const p1R=getVal(allMeterData[10],'energy_reverse_total');
  const p2R=getVal(allMeterData[11],'energy_reverse_total');
  setText('pv1TotalE',fmt(p1R,1));
  setText('pv2TotalE',fmt(p2R,1));

  const bF=getVal(allMeterData[6],'energy_forward_total');
  const bR=getVal(allMeterData[6],'energy_reverse_total');
  setText('batChargeTotal',fmt(bF,1));
  setText('batDischargeTotal',fmt(bR,1));
}

// 月/年电量：只调 yearly API（已包含12个月明细 + 年合计）
// 当月电量 = months[当前月份-1]，年电量 = total
// 只查 DJSF 电表（ADL400 不支持月冻结）
// 当月电量：从 realtime 返回的 current_month 字段取（不用额外请求）
function updateCurrentMonth(){
  if(!hasRealData) return;
  const tasks = [
    {addr:8,  el:'dc1MonthE', field:'forward'},
    {addr:9,  el:'dc2MonthE', field:'forward'},
    {addr:10, el:'pv1MonthE', field:'reverse'},
    {addr:11, el:'pv2MonthE', field:'reverse'},
    {addr:6,  el:'batChargeMonth', field:'forward', el2:'batDischargeMonth', field2:'reverse'},
  ];
  for(const t of tasks){
    const d=allMeterData[t.addr];
    if(!d||!d.current_month) continue;
    const v=t.field==='forward'?d.current_month.energy_forward_kwh:d.current_month.energy_reverse_kwh;
    setText(t.el,fmt(v,1));
    if(t.el2&&t.field2){
      const v2=t.field2==='forward'?d.current_month.energy_forward_kwh:d.current_month.energy_reverse_kwh;
      setText(t.el2,fmt(v2,1));
    }
  }
}

// 年电量：单独调 yearly API（慢，后台加载）
async function pollYearly(){
  const tasks = [
    {addr:8,  yearEl:'dc1YearE', field:'forward'},
    {addr:9,  yearEl:'dc2YearE', field:'forward'},
    {addr:10, yearEl:'pv1YearE', field:'reverse'},
    {addr:11, yearEl:'pv2YearE', field:'reverse'},
    {addr:6,  yearEl:'batChargeYear', field:'forward',
              yearEl2:'batDischargeYear', field2:'reverse'},
  ];
  const results = await Promise.all(tasks.map(async t => {
    try { return {task:t, data:await getMeterYearly(t.addr)}; }
    catch(e) { return {task:t, data:null}; }
  }));
  for (const {task, data} of results) {
    if (!data || !data.months) continue;
    yearlyCache[task.addr] = data;
    // 年电量 = 12个月冻结累加 + 当月实时值
    const curMonth = allMeterData[task.addr] && allMeterData[task.addr].current_month;
    const curFwd = curMonth ? (curMonth.energy_forward_kwh||0) : 0;
    const curRev = curMonth ? (curMonth.energy_reverse_kwh||0) : 0;
    const yVal = (task.field === 'forward' ? data.total_forward_kwh : data.total_reverse_kwh) + (task.field === 'forward' ? curFwd : curRev);
    setText(task.yearEl, fmt(yVal, 1));
    if (task.yearEl2 && task.field2) {
      const yVal2 = (task.field2 === 'forward' ? data.total_forward_kwh : data.total_reverse_kwh) + (task.field2 === 'forward' ? curFwd : curRev);
      setText(task.yearEl2, fmt(yVal2, 1));
    }
  }
}

// 每次 realtime 刷新后，用缓存的12月冻结 + 最新当月值重算年电量
function updateYearWithCurrentMonth(){
  const tasks = [
    {addr:8,  yearEl:'dc1YearE', field:'forward'},
    {addr:9,  yearEl:'dc2YearE', field:'forward'},
    {addr:10, yearEl:'pv1YearE', field:'reverse'},
    {addr:11, yearEl:'pv2YearE', field:'reverse'},
    {addr:6,  yearEl:'batChargeYear', field:'forward',
              yearEl2:'batDischargeYear', field2:'reverse'},
  ];
  for(const t of tasks){
    const yData=yearlyCache[t.addr];
    if(!yData) continue;
    const curMonth=allMeterData[t.addr]&&allMeterData[t.addr].current_month;
    const curFwd=curMonth?(curMonth.energy_forward_kwh||0):0;
    const curRev=curMonth?(curMonth.energy_reverse_kwh||0):0;
    const yVal=(t.field==='forward'?yData.total_forward_kwh:yData.total_reverse_kwh)+(t.field==='forward'?curFwd:curRev);
    setText(t.yearEl,fmt(yVal,1));
    if(t.yearEl2&&t.field2){
      const yVal2=(t.field2==='forward'?yData.total_forward_kwh:yData.total_reverse_kwh)+(t.field2==='forward'?curFwd:curRev);
      setText(t.yearEl2,fmt(yVal2,1));
    }
  }
}

// Cache yearly data for popup
let yearlyCache={};
const meterNames={6:'储能',8:'直流桩1',9:'直流桩2',10:'光伏1',11:'光伏2'};
const monthNames=['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];

function showMonthlyPopup(e,addr,field){
  // Remove existing popup
  const old=document.querySelector('.monthly-popup');
  if(old)old.remove();

  const data=yearlyCache[addr];
  if(!data||!data.months)return;

  const name=meterNames[addr]||'电表'+addr;
  const isReverse=field==='reverse';
  const title=name+(isReverse?' 放电':' 充电')+' 月度明细';

  let total=0;
  let rows='';
  const curMonthIdx=new Date().getMonth(); // 0-based
  data.months.forEach((m,i)=>{
    const v=isReverse?m.energy_reverse_kwh:m.energy_forward_kwh;
    const fv=v!==null&&v!==undefined?Number(v).toFixed(1):'--';
    if(v)total+=v;
    rows+=`<tr><td>${monthNames[i]}</td><td class="val">${fv} kWh</td></tr>`;
  });
  // 当月实时值
  const curMonth=allMeterData[addr]&&allMeterData[addr].current_month;
  const curVal=curMonth?(isReverse?curMonth.energy_reverse_kwh:curMonth.energy_forward_kwh):null;
  const curFv=curVal!==null&&curVal!==undefined?Number(curVal).toFixed(1):'--';
  if(curVal)total+=curVal;
  rows+=`<tr style="color:#00d4ff"><td>${monthNames[curMonthIdx]}(当月)</td><td class="val" style="color:#00d4ff">${curFv} kWh</td></tr>`;

  const popup=document.createElement('div');
  popup.className='monthly-popup';
  popup.innerHTML=`
    <div class="mp-title"><span>${title}</span><span class="mp-close">&times;</span></div>
    <table><tr><th>月份</th><th style="text-align:right">电量</th></tr>${rows}</table>
    <div class="mp-total">年合计: ${total.toFixed(1)} kWh</div>
  `;

  // Position near click
  const x=Math.min(e.clientX+10,window.innerWidth-300);
  const y=Math.min(e.clientY-10,window.innerHeight-400);
  popup.style.left=x+'px';
  popup.style.top=y+'px';

  document.body.appendChild(popup);

  // Close handlers
  popup.querySelector('.mp-close').addEventListener('click',()=>popup.remove());
  setTimeout(()=>{
    const closeOnClick=(ev)=>{
      if(!popup.contains(ev.target)){popup.remove();document.removeEventListener('click',closeOnClick)}
    };
    document.addEventListener('click',closeOnClick);
  },100);
}

// Bind click on year values
function bindYearClicks(){
  document.querySelectorAll('.metric-value.clickable').forEach(el=>{
    el.addEventListener('click',(e)=>{
      const addr=parseInt(el.dataset.addr);
      const field=el.dataset.field||(el.id.includes('pv')?'reverse':'forward');
      if(addr)showMonthlyPopup(e,addr,field);
    });
  });
}

async function pollAllMeters(){
  const results=await Promise.all(meterAddrs.map(async addr=>{
    try{const d=await getMeterRealtime(addr);if(d&&d.data){allMeterData[addr]=d;return true}}catch(e){}
    return false;
  }));
  hasRealData=results.some(r=>r);
  updateFlowLabels();
  updateCurrentMonth();
  updateYearWithCurrentMonth(); // 用缓存的12月冻结 + 最新当月值重算年电量
}

// Timer management
const timers=[];
function addTimer(fn,ms){
  fn(); // Run immediately on enter
  const id=setInterval(fn,ms);
  timers.push(id);
  return id;
}
function clearAllTimers(){
  timers.forEach(id=>clearInterval(id));
  timers.length=0;
}

document.addEventListener('DOMContentLoaded',()=>{
  addTimer(updateDashClock,1000);
  renderFlowDiagram();
  window.addEventListener('resize',()=>{renderFlowDiagram();updateFlowLabels()});
  bindYearClicks();
  addTimer(pollAllMeters,60000);   // 实时+当月：立即读，之后1分钟
  pollYearly();                     // 年数据：只读一次（一个月才变）
});

window.addEventListener('beforeunload',clearAllTimers);
document.addEventListener('visibilitychange',()=>{
  if(document.hidden) clearAllTimers();
  else{
    addTimer(updateDashClock,1000);
    addTimer(pollAllMeters,60000);
  }
});
