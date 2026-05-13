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

  // Outer nodes — unchanged from v1.0.0 layout.
  const N={
    grid:   {x:CX-d1,y:topY,icon:'⚡',name:'电网',bc:'#ff6b6b',lc:'#ffcc44',r:R},
    pv1:    {x:CX-d2,y:topY,icon:'☀️',name:'光伏1',bc:'#ff9500',lc:'#ffdd55',r:R},
    pv2:    {x:CX+d2,y:topY,icon:'☀️',name:'光伏2',bc:'#ff9500',lc:'#ffdd55',r:R},
    storage:{x:CX+d1,y:topY,icon:'🔋',name:'储能',bc:'#00ffff',lc:'#88ffff',r:R},
    office: {x:CX-d3,y:botY,icon:'💻',name:'办公室',bc:'#4ecdc4',lc:'#bbddff',r:RB},
    ac:     {x:CX,y:botY,icon:'🚗',name:'交流充电桩',bc:'#ff9500',lc:'#ffdd55',r:RB},
    dc:     {x:CX+d3,y:botY,icon:'🚗',name:'直流充电桩',bc:'#ff9500',lc:'#ffdd55',r:RB},
  };

  // Center: three same-size converter blocks packed in an L-shape.
  //   ┌─────┐          ┌─────┐
  //   │AC/DC├──┐       │     │
  //   └─────┘  ├═══════│DC/DC│  ← DC/DC vertically centered at midY
  //   ┌─────┐  │       │     │     (between AC/DC top and DC/AC bottom)
  //   │DC/AC├──┘       └─────┘
  //   └─────┘
  // Red BUS busbar: joins AC/DC.right + DC/AC.right (vertical strip at CX),
  // then a horizontal stub to DC/DC.left at midY. PV merge enters from
  // above into the same vertical strip; office+AC merge enters DC/AC.bottom.
  const bW=Math.min(W*.10,82);
  const bH=Math.min(H*.10,60);
  const blockGap=bH*.6;                       // vertical gap between AC/DC & DC/AC
  const leftCX=CX-bW*.75;
  const rightCX=CX+bW*.75;
  const acdcCY=midY-(bH+blockGap)/2;
  const dcacCY=midY+(bH+blockGap)/2;
  const BX={
    acdc:{cx:leftCX,  cy:acdcCY, w:bW, h:bH,
          l:leftCX-bW/2,  t:acdcCY-bH/2, r:leftCX+bW/2,  b:acdcCY+bH/2,
          label:'AC/DC'},
    dcac:{cx:leftCX,  cy:dcacCY, w:bW, h:bH,
          l:leftCX-bW/2,  t:dcacCY-bH/2, r:leftCX+bW/2,  b:dcacCY+bH/2,
          label:'DC/AC'},
    dcdc:{cx:rightCX, cy:midY,   w:bW, h:bH,
          l:rightCX-bW/2, t:midY-bH/2,   r:rightCX+bW/2, b:midY+bH/2,
          label:'DC/DC'},
  };
  // BUS junction lives at the CENTER X of the left column: vertical leg
  // is the line connecting the middle of AC/DC's bottom edge to the
  // middle of DC/AC's top edge (so the |— sits cleanly in the gap, not
  // over the block borders). Horizontal leg branches off at midY,
  // crosses through DC/DC and STOPS at its right edge — DC pile feeds
  // into the BUS by coming up from below to that exact endpoint.
  const busX=BX.acdc.cx;
  // Where PV merge lands on the horizontal BUS — between the left column
  // and DC/DC so the PV merged tail doesn't pass through AC/DC vertically.
  const pvBusX=(BX.acdc.r+BX.dcdc.l)/2;
  // DC pile attaches to the BUS at DC/DC's LEFT edge — i.e., the BUS
  // horizontal stops exactly where it meets DC/DC, and the DC pile feed
  // arrives at that same endpoint from below.
  const busRightEnd=BX.dcdc.l;

  // Path builders — each outer node enters its target block on a specific edge.
  // 电网 → AC/DC LEFT side (line wraps around from upper-left, enters from left)
  function gridPath(){
    const sx=N.grid.x, sy=N.grid.y+R, tx=BX.acdc.l, ty=BX.acdc.cy;
    return `M${sx},${sy} L${sx},${ty} L${tx},${ty}`;
  }
  // 光伏1 + 光伏2 → MERGE → down to BUS (top of vertical strip).
  // Each PV emits an L-shaped path that converges at (CX, mergeY) then runs
  // down the shared segment to (CX, acdcCY). The overlapping shared segment
  // gives the visual "two PVs feeding one bus" effect.
  // Merge level pushed up close to the PV nodes so the horizontal segment
  // sits ABOVE the wrapper top border, not crossing it.
  const pvMergeY=N.pv1.y+R+(BX.acdc.t-bH*.45-(N.pv1.y+R))*.5;
  function pv1Path(){
    return `M${N.pv1.x},${N.pv1.y+R} L${N.pv1.x},${pvMergeY} L${pvBusX},${pvMergeY} L${pvBusX},${midY}`;
  }
  function pv2Path(){
    return `M${N.pv2.x},${N.pv2.y+R} L${N.pv2.x},${pvMergeY} L${pvBusX},${pvMergeY} L${pvBusX},${midY}`;
  }
  // 储能 → DC/DC RIGHT side, upper portion (NOT at midY — that's where
  // the BUS horizontal runs, so we deliberately offset to keep storage's
  // own flow line visually distinct from the BUS bar).
  function storagePath(){
    const sx=N.storage.x, sy=N.storage.y+R;
    const ty=BX.dcdc.cy-BX.dcdc.h*.30;
    return `M${sx},${sy} L${sx},${ty} L${BX.dcdc.r},${ty}`;
  }
  // 直流桩 → up to the BUS endpoint at DC/DC's LEFT edge. Path goes UP
  // from the pile, LEFT under DC/DC (well below DC/DC.b), UP through
  // a column OFFSET slightly to the left of DC/DC.l so it doesn't run
  // along the block's left border, then a short RIGHT into the BUS
  // endpoint. Keeps the line clearly visible against the block edges.
  function dcPath(){
    const sx=N.dc.x, sy=N.dc.y-N.dc.r;
    const jy=BX.dcac.b+(sy-BX.dcac.b)*.45;
    const vx=busRightEnd-Math.max(6,bW*.10);
    return `M${sx},${sy} L${sx},${jy} L${vx},${jy} L${vx},${midY} L${busRightEnd},${midY}`;
  }
  // 办公室 + 交流桩 → MERGE → up to DC/AC BOTTOM
  const acMergeY=BX.dcac.b+(N.ac.y-N.ac.r-BX.dcac.b)*.45;
  function acPath(){
    return `M${N.ac.x},${N.ac.y-N.ac.r} L${N.ac.x},${acMergeY} L${BX.dcac.cx},${acMergeY} L${BX.dcac.cx},${BX.dcac.b}`;
  }
  function officePath(){
    return `M${N.office.x},${N.office.y-N.office.r} L${N.office.x},${acMergeY} L${BX.dcac.cx},${acMergeY} L${BX.dcac.cx},${BX.dcac.b}`;
  }

  const edges=[
    {id:'eGrid',path:gridPath(),type:'grid-line',pk:'grid',bidir:true},
    {id:'ePv1',path:pv1Path(),type:'solar',pk:'pv1'},
    {id:'ePv2',path:pv2Path(),type:'solar',pk:'pv2'},
    {id:'eStor',path:storagePath(),type:'storage',pk:'storage',bidir:true},
    {id:'eDc',path:dcPath(),type:'charge-dc',pk:'dc'},
    {id:'eAc',path:acPath(),type:'charge-ac',pk:'ac'},
    {id:'eOff',path:officePath(),type:'office-line',pk:'office'},
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

  // Outer panel that bundles AC/DC + DC/AC + DC/DC into one visual
  // assembly ("光储系统" enclosure). Drawn FIRST so flow edges, the BUS,
  // and the three inner block rectangles all render on top of it.
  const panPad=Math.max(12,bH*.30);
  const panL=BX.acdc.l-panPad, panT=BX.acdc.t-panPad;
  const panR=BX.dcdc.r+panPad, panB=BX.dcac.b+panPad;
  svg+=`<rect x="${panL}" y="${panT}" width="${panR-panL}" height="${panB-panT}" rx="10" fill="rgba(15,30,80,.55)" stroke="#60a5fa" stroke-width="1.5" opacity="0.85"/>`;

  edges.forEach(e=>{
    const cls=edgeClass('flow-edge '+e.type,flowPower[e.pk]);
    if(e.bidir){
      svg+=`<path id="${e.id}" d="${e.path}" class="${cls}"/>`;
      svg+=`<path d="${e.path}" class="flow-edge ${e.type} animated reverse" opacity="0.25"/>`;
    }else{
      svg+=`<path id="${e.id}" d="${e.path}" class="${cls}"/>`;
    }
  });

  // Three converter blocks — uniform size, dark blue with a forward-slash
  // "/" diagonal hairline. The label reads naturally as e.g. "AC/DC":
  // first part sits in the UPPER-LEFT half-triangle, second part in the
  // LOWER-RIGHT half-triangle, separated by the diagonal.
  Object.values(BX).forEach(b=>{
    const parts=b.label.split('/');
    const fs=Math.max(10,Math.min(b.w*.32,15));
    svg+=`<rect x="${b.l}" y="${b.t}" width="${b.w}" height="${b.h}" rx="4" fill="#1e3a8a" stroke="#3b82f6" stroke-width="2"/>`;
    svg+=`<line x1="${b.l+4}" y1="${b.b-4}" x2="${b.r-4}" y2="${b.t+4}" stroke="#fff" stroke-width="1.5" opacity="0.9"/>`;
    // First label in upper-LEFT triangle (above the "/" diagonal)
    svg+=`<text x="${b.l+b.w*.28}" y="${b.t+b.h*.36}" text-anchor="middle" dominant-baseline="middle" font-size="${fs}" fill="#fff" font-weight="bold">${parts[0]}</text>`;
    // Second label in lower-RIGHT triangle (below the "/" diagonal)
    svg+=`<text x="${b.l+b.w*.72}" y="${b.t+b.h*.74}" text-anchor="middle" dominant-baseline="middle" font-size="${fs}" fill="#fff" font-weight="bold">${parts[1]}</text>`;
  });

  // Red BUS busbar — pure |— shape, drawn ON TOP of the three blocks.
  // Vertical leg connects the MIDDLE of AC/DC's bottom edge to the MIDDLE
  // of DC/AC's top edge (sitting in the gap between them at center X).
  // Horizontal leg branches off at midY, passes through DC/DC interior,
  // and continues out past DC/DC's right side to receive the DC pile feed.
  const busColor='#ef4444', busW=3.5;
  svg+=`<line x1="${busX}" y1="${BX.acdc.b}" x2="${busX}" y2="${BX.dcac.t}" stroke="${busColor}" stroke-width="${busW}" stroke-linecap="round"/>`;
  svg+=`<line x1="${busX}" y1="${midY}" x2="${busRightEnd}" y2="${midY}" stroke="${busColor}" stroke-width="${busW}" stroke-linecap="round"/>`;

  const fs=Math.max(10,Math.min(R*.55,22));
  Object.entries(N).forEach(([k,n])=>{
    const addrMap={pv1:10,pv2:11,grid:1,storage:6,dc:8,ac:3,office:4};
    const addr=addrMap[k];
    const clickStyle=addr?'cursor:pointer':'';
    svg+=`<g class="flow-node-group"${addr?' data-addr="'+addr+'"':''} style="--node-color:${n.bc};${clickStyle}">`;
    svg+=`<circle cx="${n.x}" cy="${n.y}" r="${n.r}" fill="rgba(0,20,60,.9)" stroke="${n.bc}" stroke-width="2"/>`;
    svg+=`<text x="${n.x}" y="${n.y-n.r*.1}" text-anchor="middle" font-size="${fs}">${n.icon}</text>`;
    svg+=`<text x="${n.x}" y="${n.y+n.r*.45}" text-anchor="middle" font-size="${Math.max(9,fs*.45)}" fill="#fff" font-weight="bold">${n.name}</text>`;
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
   ['eDc','flow-edge charge-dc',flowPower.dc],
   ['eAc','flow-edge charge-ac',flowPower.ac],
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

  // Solar hero — current output power + efficiency vs. installed capacity
  const SOLAR_CAPACITY_KW=285.6;
  const solarOutput=Math.abs(pv1P||0)+Math.abs(pv2P||0);
  const solarEl=document.getElementById('solarPowerBig');
  if(solarEl)solarEl.innerHTML=fmt(solarOutput)+'<span class="solar-stat-unit">kW</span>';
  const effEl=document.getElementById('solarEfficiency');
  if(effEl){
    const pct=(solarOutput/SOLAR_CAPACITY_KW)*100;
    effEl.innerHTML=(isFinite(pct)?pct.toFixed(1):'--')+'<span class="solar-stat-unit">%</span>';
  }
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
  const curMonth=allMeterData[addr]&&allMeterData[addr].current_month;
  const curVal=curMonth?(isReverse?curMonth.energy_reverse_kwh:curMonth.energy_forward_kwh):null;

  // Only show this year's months + current month
  data.months.forEach((m,i)=>{
    if(!m.is_this_year && i!==curMonthIdx) return; // skip last year's data
    let v=isReverse?m.energy_reverse_kwh:m.energy_forward_kwh;
    let isCur=false;
    if(i===curMonthIdx&&curVal!==null&&curVal!==undefined){
      v=curVal;
      isCur=true;
    }
    const fv=v!==null&&v!==undefined?Number(v).toFixed(1):'--';
    if(v)total+=v;
    const style=isCur?' style="color:#00d4ff"':'';
    const label=isCur?monthNames[i]+'(当月)':monthNames[i];
    rows+=`<tr${style}><td>${label}</td><td class="val"${style}>${fv} kWh</td></tr>`;
  });

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

async function pollBatterySoc(){
  const fill=document.getElementById('batteryFill');
  const pctEl=document.getElementById('batterySocPct');
  const d=await fetchJSON('/battery/soc');
  if(!d||!d.ok){
    if(fill){fill.style.setProperty('--soc','0%');fill.classList.remove('low','medium');}
    if(pctEl)pctEl.innerHTML='--<span class="battery-unit">%</span>';
    return;
  }
  const pct=d.soc_pct;
  if(fill){
    fill.style.setProperty('--soc',pct+'%');
    fill.classList.remove('low','medium');
    if(pct<20)fill.classList.add('low');
    else if(pct<50)fill.classList.add('medium');
  }
  if(pctEl)pctEl.innerHTML=pct+'<span class="battery-unit">%</span>';
}

document.addEventListener('DOMContentLoaded',()=>{
  addTimer(updateDashClock,1000);
  renderFlowDiagram();
  window.addEventListener('resize',()=>{renderFlowDiagram();updateFlowLabels()});
  bindYearClicks();
  addTimer(pollAllMeters,5000);        // 实时+当月：5秒（后端走缓存）
  addTimer(pollYearly,3600000);        // 年数据：1小时
  addTimer(pollBatterySoc,10000);      // 电池SOC：10秒
});

// Page lives ~20s before <meta refresh> reloads it from scratch — no need
// for visibility/lifecycle gymnastics, no need to clean up on unload.
// Adding pageshow/resume/focus handlers caused fetch storms on focus
// thrash and is what made the JS-driven rotate.js so flaky in 664eee0.
