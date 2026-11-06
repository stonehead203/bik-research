import * as T from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';

const world = document.querySelector('#world');
const status = document.querySelector('#scene-status');
let renderer;
try {
  renderer = new T.WebGLRenderer({ antialias: true });
} catch {
  status.textContent = '이 브라우저에서 3D를 열 수 없습니다. 시세와 기도는 아래에서 이용할 수 있습니다.';
  throw new Error('WebGL unavailable');
}
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.65));
renderer.setClearColor(0x83bde4);
world.prepend(renderer.domElement);

const scene = new T.Scene();
scene.fog = new T.FogExp2(0xb4d4df, .0085);
const camera = new T.PerspectiveCamera(49, 1, .12, 235);
scene.add(new T.HemisphereLight(0xe5f4ff, 0x918364, 1.8));
const moonlight = new T.DirectionalLight(0xffedd2, 2.1);
moonlight.position.set(-8, 15, 7);
scene.add(moonlight);
const rim = new T.DirectionalLight(0xb4d8ff, .52);
rim.position.set(7, 4, 12);
scene.add(rim);
const skyGeometry = new T.SphereGeometry(198,32,20);
const skyMaterial = new T.ShaderMaterial({
  side:T.BackSide, depthWrite:false,
  uniforms:{
    horizon:{value:new T.Color(0xc5e5f2)},
    blue:{value:new T.Color(0x328fd1)},
    sunDirection:{value:new T.Vector3(-.6,.59,.4).normalize()}
  },
  vertexShader:`
    varying vec3 direction;
    void main(){ direction=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }
  `,
  fragmentShader:`
    uniform vec3 horizon;
    uniform vec3 blue;
    uniform vec3 sunDirection;
    varying vec3 direction;
    void main(){
      vec3 ray=normalize(direction);
      float altitude=smoothstep(-0.08,0.55,ray.y);
      float glow=pow(max(dot(ray,sunDirection),0.0),18.0)*0.22;
      gl_FragColor=vec4(mix(horizon,blue,altitude)+vec3(glow),1.0);
      #include <colorspace_fragment>
    }
  `
});
const skyMesh=new T.Mesh(skyGeometry,skyMaterial);
skyMesh.renderOrder=-10;
scene.add(skyMesh);

const stone = new T.MeshStandardMaterial({ color: 0x817661, roughness: .9 });
const trim = new T.MeshStandardMaterial({ color: 0xb5a68a, metalness: .22, roughness: .55 });
const jade = new T.MeshStandardMaterial({ color: 0x2d6151 });
const gold = new T.MeshBasicMaterial({ color: 0xffd394 });
const dark = new T.MeshStandardMaterial({ color: 0x292d2e });
function mesh(geometry, material, x, y, z, parent = scene) {
  const object = new T.Mesh(geometry, material);
  object.position.set(x, y, z);
  parent.add(object);
  return object;
}
function box(w, h, d, material, x, y, z, parent) {
  return mesh(new T.BoxGeometry(w, h, d), material, x, y, z, parent);
}
function disc(top, bottom, height, sides, material, x, y, z, parent) {
  return mesh(new T.CylinderGeometry(top, bottom, height, sides), material, x, y, z, parent);
}

const material = color => new T.MeshStandardMaterial({ color, roughness: .88 });
function grain(wooden) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 256;
  const context = canvas.getContext('2d');
  context.fillStyle = '#ddd3c6';
  context.fillRect(0,0,256,256);
  let value = wooden ? 197 : 31;
  const noise = () => {
    value = (1664525 * value + 1013904223) >>> 0;
    return value / 4294967296;
  };
  for (let i=0;i<5200;i++) {
    context.fillStyle = noise() > .5 ? 'rgba(75,40,17,.08)' : 'rgba(255,245,217,.12)';
    context.fillRect(noise()*256,noise()*256,wooden ? 1+noise()*3 : 1+noise()*7,wooden ? 9+noise()*50 : 1+noise()*5);
  }
  if (wooden) {
    for (let i=0;i<42;i++) {
      const x=noise()*256;
      context.strokeStyle='rgba(68,34,12,.14)';
      context.beginPath();
      context.moveTo(x,0);
      context.bezierCurveTo(x+5,80,x-7,170,x,256);
      context.stroke();
    }
  }
  const texture=new T.CanvasTexture(canvas);
  texture.colorSpace=T.SRGBColorSpace;
  texture.anisotropy=Math.min(renderer.capabilities.getMaxAnisotropy(),8);
  return texture;
}
const woodGrain=grain(true), stoneGrain=grain(false);
const earth = material(0xaca080);
const wood = material(0x693a2a);
const red = material(0x944838);
const cream = material(0xd6bf8b);
const roofMat = material(0x303c3b);
roofMat.side = T.DoubleSide;
const tileMat = material(0x45524e);
wood.map = woodGrain;
red.map = woodGrain;
stone.map = stoneGrain;
earth.map = stoneGrain;
const ground = box(72, .2, 91, earth, 0, -.115, 2);
box(151, .4, 157, material(0x75915a), 0, -.58, -8);
const road = [0xa89980, 0xa0937d, 0xb8a88b].map(color => new T.MeshStandardMaterial({color,map:stoneGrain,roughness:.9}));
let seed = 413;
function random() {
  seed = (1664525 * seed + 1013904223) >>> 0;
  return seed / 4294967296;
}
for (let row = 0; row < 25; row++) {
  for (let col = -3; col <= 3; col++) {
    const tile = box(.94 + random() * .06, .065, .87, road[(row + col + 3) % 3], col * 1.04 + (row % 2 ? .12 : 0), .015, 13.12 + row * 1.08);
    tile.rotation.y = (random() - .5) * .055;
  }
}
const mountainLayers = [
  { radius:158, height:33, base:0x608c70, phase:1.1 },
  { radius:133, height:27, base:0x4c8052, phase:2.4 },
  { radius:110, height:21, base:0x336844, phase:3.7 }
];
for (const {radius,height,base,phase} of mountainLayers) {
  const points=[], colors=[], indices=[];
  const segments=112;
  for (let i=0;i<=segments;i++) {
    const angle=i/segments*Math.PI*2;
    const peak=height*(.61+.22*Math.sin(angle*4+phase)+.14*Math.sin(angle*9-phase)+.055*Math.cos(angle*17));
    for(let ring=0;ring<4;ring++) {
      const r=radius-(3-ring)*8+(2-ring)*2.3*Math.sin(angle*5+phase);
      const profile=[-6,peak*.32-1,peak*.72,peak][ring];
      points.push(Math.sin(angle)*r,profile,Math.cos(angle)*r-11);
      const hue=new T.Color(base).multiplyScalar(.76+ring*.09+random()*.1);
      colors.push(hue.r,hue.g,hue.b);
      if(i<segments && ring<3) {
        const a=i*4+ring;
        indices.push(a,a+1,a+4,a+1,a+5,a+4);
      }
    }
  }
  const geometry=new T.BufferGeometry();
  geometry.setAttribute('position',new T.Float32BufferAttribute(points,3));
  geometry.setAttribute('color',new T.Float32BufferAttribute(colors,3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  mesh(geometry,new T.MeshStandardMaterial({vertexColors:true,roughness:1,side:T.DoubleSide}),0,0,0);
}
const cloudCanvas=document.createElement('canvas');
cloudCanvas.width=512; cloudCanvas.height=192;
const cloudContext=cloudCanvas.getContext('2d');
for(const [x,y,r] of [[90,112,58],[156,104,73],[238,80,79],[320,103,66],[399,114,59]]) {
  const gradient=cloudContext.createRadialGradient(x,y,r*.14,x,y,r);
  gradient.addColorStop(0,'rgba(255,255,255,.83)');
  gradient.addColorStop(.5,'rgba(255,255,255,.56)');
  gradient.addColorStop(1,'rgba(255,255,255,0)');
  cloudContext.fillStyle=gradient; cloudContext.fillRect(x-r,y-r,r*2,r*2);
}
const cloudTexture=new T.CanvasTexture(cloudCanvas);
cloudTexture.colorSpace=T.SRGBColorSpace;
const cloudMaterial=new T.SpriteMaterial({map:cloudTexture,transparent:true,depthWrite:false,fog:false,opacity:.84});
for(const [x,y,z,width] of [[-41,28,-103,41],[19,32,-110,34],[58,23,-87,27],[-81,27,-57,30],[70,28,42,39],[-59,29,72,36]]) {
  const cloud=new T.Sprite(cloudMaterial);
  cloud.position.set(x,y,z); cloud.scale.set(width,width*.34,1);
  scene.add(cloud);
}
const courtyard={left:-31.9,right:31.9,back:-32.1,front:42.1};
for(const z of [-33,43]) {
  box(66,.58,.65,stone,0,.25,z);
  box(66,.12,.88,trim,0,.59,z);
  for(let x=-32;x<=32;x+=4) box(.65,.9,.96,stone,x,.43,z);
}
for (const x of [-33,33]) {
  box(.65,.56,76,stone,x,.25,5);
  box(.83,.11,76,trim,x,.57,5);
  for(let z=-32;z<=42;z+=4) box(1,.86,.68,stone,x,.45,z);
}
for (const side of [-1,1]) {
  for (let row=0;row<12;row++) {
    const x=side*(5.4+row*1.18), z=25.4+Math.sin(row*.15)*2.3;
    box(1.06,.07,.88,road[row%3],x,.014,z).rotation.y=(random()-.5)*.13;
  }
  for (const z of [24,35]) {
    const x=side*16.5;
    box(3.15,.18,.57,wood,x,.63,z);
    for(const dx of [-1.07,1.07]) box(.26,.68,.62,stone,x+dx,.31,z);
  }
}

const leafShape = new T.Shape();
const leafOutline = [[0,-1],[.1,-.49],[.54,-.53],[.4,-.21],[.89,-.11],[.47,.1],[.63,.51],[.22,.39],[0,1],[-.22,.39],[-.63,.51],[-.47,.1],[-.89,-.11],[-.4,-.21],[-.54,-.53],[-.1,-.49]];
leafOutline.forEach(([x,y],i) => i ? leafShape.lineTo(x,y) : leafShape.moveTo(x,y));
leafShape.closePath();
const leafGeometry = new T.ShapeGeometry(leafShape);
const leavesMaterial = new T.MeshStandardMaterial({color:0xffffff,side:T.DoubleSide,roughness:.76});
const foliage = new T.InstancedMesh(leafGeometry, leavesMaterial, 24192);
const pose = new T.Object3D();
const leafColors = [0x942d24, 0xb44727, 0xc2672c, 0xde8a37, 0xeda645, 0xad5130].map(color => new T.Color(color));
let leafIndex = 0;
function branch(x, y, z, toX, toY, toZ, bottom, top) {
  const from = new T.Vector3(x, y, z);
  const to = new T.Vector3(toX, toY, toZ);
  const direction = to.clone().sub(from);
  const mid = from.addScaledVector(direction, .5);
  const limb = disc(top, bottom, direction.length(), 7, wood, mid.x, mid.y, mid.z);
  limb.quaternion.setFromUnitVectors(T.Object3D.DEFAULT_UP, direction.normalize());
}
function maple(x, z, height) {
  const lean = (random() - .5) * .62;
  branch(x, 0, z, x + lean, height * .83, z, .27, .075);
  for (let b = 0; b < 6; b++) {
    const a = b * 2.4, r = .85 + random() * .94;
    const px = x + lean + Math.cos(a) * r, pz = z + Math.sin(a) * r;
    const py = height * (.71 + random() * .35);
    branch(x + lean * .7, height * .53, z, px, py, pz, .094, .021);
    for (let j = 0; j < 252; j++) {
      const angle = random() * Math.PI * 2, distance = Math.sqrt(random()) * 1.24;
      pose.position.set(px + Math.cos(angle) * distance, py + (random() - .45) * 1.24, pz + Math.sin(angle) * distance);
      pose.rotation.set(random(), random() * 6, random());
      const size = .09 + random() * .16;
      pose.scale.set(size * 1.12, size, size);
      pose.updateMatrix();
      foliage.setMatrixAt(leafIndex, pose.matrix);
      foliage.setColorAt(leafIndex++, leafColors[Math.floor(random() * leafColors.length)]);
    }
  }
}
for (const [x, z, h] of [[-16,14,7.9],[16,14,8],[-11,20,7],[11,20,7.2],[-12,30,7.2],[17,33,7.3],[-17,-18,8],[17,-18,8.3],[-9,-25,7.6],[9,-25,7.3],[-23,10,8],[23,10,8.4],[-24,32,8.2],[24,32,7.9],[-21,-26,8],[21,-26,8.1]]) maple(x,z,h);
scene.add(foliage);

const leafGround = new T.InstancedMesh(leafGeometry, leavesMaterial, 1240);
const groundLeaves=[];
for (let i = 0; i < leafGround.count; i++) {
  const x = (random() - .5) * (i<400 ? 11 : 51), z = 12 + random() * 31;
  pose.position.set(x, .063, z);
  pose.rotation.set(-Math.PI / 2, 0, random() * 6.28);
  pose.scale.setScalar(.035 + random() * .085);
  pose.updateMatrix();
  groundLeaves.push({x,z,angle:pose.rotation.z,size:pose.scale.x});
  leafGround.setMatrixAt(i, pose.matrix);
  leafGround.setColorAt(i, leafColors[i % leafColors.length]);
}
scene.add(leafGround);
for (const x of [-4.75, 4.75]) {
  for (const z of [15.2,21.7,28.6,35.7]) {
    box(.72, .18, .72, stone, x, .1, z);
    disc(.19, .26, .48, 8, stone, x, .42, z);
    box(.43, .42, .43, gold, x, .84, z);
    for (const dx of [-.23,.23]) for (const dz of [-.23,.23]) box(.07,.49,.07,wood,x+dx,.84,z+dz);
    disc(0, .49, .28, 4, stone, x, 1.22, z).rotation.y = Math.PI / 4;
  }
}

const exerciseSpot={x:12.8,z:25.7};
const exerciseSteel=new T.MeshStandardMaterial({color:0x414a48,roughness:.42,metalness:.48});
for(const offset of [-1.55,1.55]) {
  box(.71,.16,.71,stone,exerciseSpot.x+offset,.07,exerciseSpot.z);
  disc(.087,.087,2.94,14,exerciseSteel,exerciseSpot.x+offset,1.49,exerciseSpot.z);
  disc(.11,.11,.095,14,jade,exerciseSpot.x+offset,2.97,exerciseSpot.z);
}
const pullBar=disc(.058,.058,3.25,14,exerciseSteel,exerciseSpot.x,2.78,exerciseSpot.z);
pullBar.rotation.z=Math.PI/2;
box(4.1,.04,3.6,material(0x8d795b),exerciseSpot.x,.008,exerciseSpot.z);
const beforeHall = new Set(scene.children);
const front = -3.1, rear = -9.5, hallZ = (front + rear) / 2;
box(13.2, .35, 7.4, stone, 0, .16, hallZ);
box(12.7, .14, 7.1, trim, 0, .39, hallZ);
const hallFloor = box(12.2, .17, 6.8, wood, 0, .52, hallZ);
const steps=[];
for (let i=0;i<3;i++) steps.push(box(4.4,.13+.13*i,.55,road[i],0,.06+i*.065,front+(1.03-i*.45)*2.1/4.95));
for (const z of [-4.8,-6.4,-8.0]) {
  for(const side of [-1,1]) {
    const x=side*5.72;
    disc(.36,.41,.21,10,trim,x,.66,z);
    disc(.23,.27,4.08,12,red,x,2.78,z);
    box(.62,.22,.38,jade,x,4.93,z);
    const lantern=mesh(new T.SphereGeometry(.23,14,10),gold,side*4.75,4.32,z);
    lantern.scale.z=.57;
  }
  box(11.5,.23,.13,wood,0,4.91,z);
}
for (const z of [front,rear]) {
  for (const x of [-5.85,-3.45,3.45,5.85]) {
    disc(.35,.42,.21,8,trim,x,.66,z);
    disc(.22,.29,4.1,10,red,x,2.8,z);
    disc(.3,.3,.11,10,cream,x,4.78,z);
    box(.74,.24,.68,jade,x,5.01,z);
  }
  box(12.45,.32,.55,red,0,4.9,z);
  box(12.53,.12,.61,cream,0,5.11,z);
  box(12.65,.29,.62,jade,0,5.3,z);
  for (let x = -5.95; x <= 5.96; x += .43) {
    box(.34,.21,.12, x % .86 > .4 ? gold : red,x,5.27,z+.34);
    box(.17,.15,.8,wood,x,5.53,z);
  }
}
box(11.7,4.16,.24,wood,0,2.64,rear);
for (const side of [-1,1]) {
  box(.17,4.15,6.35,wood,side*5.85,2.66,hallZ);
  for (let i=0;i<17;i++) box(.1,2.4,.06,jade,side*5.73,2.7,rear+.27+i*.36);
  for (let i=0;i<7;i++) box(.1,.045,6.16,trim,side*5.72,1.55+i*.37,hallZ);
}
for (let x=-5.7;x<5.8;x+=.44) box(.048,.075,6.3,trim,x,.627,hallZ);

function roofPoint(u, v, side) {
  const x = u * (4.9 + 2.05 * v);
  const y = 7.68 - 2.78 * v + .83 * v * v + .54 * Math.pow(Math.abs(u), 5) * v * v;
  const z = hallZ + side * (v * 4.15 - .22 * Math.pow(Math.abs(u), 3) * v);
  return new T.Vector3(x,y,z);
}
function ridge(points, radius, mat) {
  mesh(new T.TubeGeometry(new T.CatmullRomCurve3(points), Math.max(8, points.length * 2), radius, 5, false),mat,0,0,0);
}
for (const side of [-1,1]) {
  const verts = [], ids = [], cols = 48, rows = 14;
  for (let j=0;j<=rows;j++) for(let i=0;i<=cols;i++) verts.push(...roofPoint(i/cols*2-1,j/rows,side).toArray());
  for (let j=0;j<rows;j++) for(let i=0;i<cols;i++) {
    const a=j*(cols+1)+i;
    ids.push(a,a+1,a+cols+1,a+1,a+cols+2,a+cols+1);
  }
  const roof = new T.BufferGeometry();
  roof.setAttribute('position', new T.Float32BufferAttribute(verts,3));
  roof.setIndex(ids);
  roof.computeVertexNormals();
  mesh(roof,roofMat,0,0,0);
  for (let i=0;i<=cols;i++) {
    const points=Array.from({length:9},(_,j)=>roofPoint(i/cols*2-1,j/8,side));
    ridge(points,.043,tileMat);
    const edge=points.at(-1);
    const cap=disc(.082,.082,.13,8,tileMat,edge.x,edge.y-.025,edge.z);
    cap.rotation.x=Math.PI/2;
  }
  ridge(Array.from({length:21},(_,i)=>roofPoint(i/10-1,1,side)),.125,roofMat);
  for (const end of [-1,1]) ridge(Array.from({length:11},(_,i)=>roofPoint(end,i/10,side)),.115,roofMat);
}
for(const end of [-1,1]) {
  const face=new T.BufferGeometry();
  const verts=[];
  for(let i=0;i<14;i++) {
    const a=roofPoint(end,i/14,1),b=roofPoint(end,(i+1)/14,1);
    const c=roofPoint(end,i/14,-1),d=roofPoint(end,(i+1)/14,-1);
    verts.push(...a,...b,...c,...b,...d,...c);
  }
  face.setAttribute('position',new T.Float32BufferAttribute(verts,3));
  face.computeVertexNormals();
  mesh(face,roofMat,0,0,0);
}
ridge([new T.Vector3(-5.25,7.91,hallZ),new T.Vector3(-4.65,7.73,hallZ),new T.Vector3(0,7.68,hallZ),new T.Vector3(4.65,7.73,hallZ),new T.Vector3(5.25,7.91,hallZ)],.14,roofMat);

const plaque = document.createElement('canvas');
plaque.width = 512;
plaque.height = 148;
const ink = plaque.getContext('2d');
ink.fillStyle='#233d36'; ink.fillRect(0,0,512,148);
ink.lineWidth=8; ink.strokeStyle='#c5a571'; ink.strokeRect(9,9,494,130);
ink.textAlign='center'; ink.textBaseline='middle'; ink.fillStyle='#f8db9c';
ink.font='bold 77px Batang, serif'; ink.fillText('호 두 법 당',256,77);
const sign=new T.CanvasTexture(plaque);
sign.colorSpace=T.SRGBColorSpace;
box(3.66,1.08,.16,wood,0,4.75,front+.43);
mesh(new T.PlaneGeometry(3.44,1),new T.MeshBasicMaterial({map:sign}),0,4.75,front+.53);
for (const x of [-4.73,-2.61,2.61,4.73]) {
  box(.025,.55,.025,wood,x,4.7,front+.21);
  const lantern=mesh(new T.SphereGeometry(.25,12,8),gold,x,4.22,front+.21);
  lantern.scale.y=.81;
  disc(.085,.085,.13,8,red,x,3.99,front+.21);
  disc(.12,.12,.07,8,red,x,4.43,front+.21);
}
const interior = new T.PointLight(0xffb269, 38, 11, 2);
interior.position.set(0,4,-4.6);
scene.add(interior);
const beforeChart = new Set(scene.children);
const chartZ = -7.66;
box(7.63,.35,1.15,red,0,.83,chartZ);
box(7.5,.12,1.24,cream,0,1.065,chartZ);
box(7.25,3.08,.25,wood,0,2.56,chartZ);
box(7.1,2.98,.28,cream,0,2.56,chartZ+.03);
for(const x of [-4.2,4.2]) {
  disc(.16,.21,.44,8,gold,x,1.02,chartZ);
  disc(.21,.28,.3,8,red,x,.65,chartZ);
}
const board = document.createElement('canvas');
board.width = 768;
board.height = 396;
const ctx = board.getContext('2d');
const texture = new T.CanvasTexture(board);
texture.colorSpace = T.SRGBColorSpace;
mesh(new T.PlaneGeometry(6.88, 2.81), new T.MeshBasicMaterial({ map: texture }), 0, 2.56, chartZ + .19);
function drawBoard(data) {
  ctx.fillStyle = '#10292b';
  ctx.fillRect(0, 0, 768, 396);
  ctx.strokeStyle = '#34514e';
  ctx.lineWidth = 2;
  ctx.strokeRect(15, 15, 738, 366);
  ctx.fillStyle = '#a7e9cc';
  ctx.font = '22px monospace';
  ctx.fillText('01  /  BTC · USD', 45, 65);
  ctx.fillStyle = '#fff2d3';
  ctx.font = 'bold 60px monospace';
  ctx.fillText(data?.priceText ?? '—', 45, 145);
  ctx.strokeStyle = '#3b5a57';
  for (let y = 186; y <= 324; y += 46) {
    ctx.beginPath();
    ctx.moveTo(45, y);
    ctx.lineTo(723, y);
    ctx.stroke();
  }
  if (data?.series?.length) {
    const low = Math.min(...data.series), high = Math.max(...data.series);
    ctx.beginPath();
    data.series.forEach((price, index) => {
      const x = 45 + 678 * index / (data.series.length - 1);
      const y = 324 - 137 * (price - low) / (high - low || 1);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#9ce9ca';
    ctx.lineWidth = 4;
    ctx.stroke();
  }
  ctx.fillStyle = '#9fbcb5';
  ctx.font = '17px monospace';
  ctx.fillText(data?.label ?? 'WAITING FOR QUOTE', 45, 359);
  texture.needsUpdate = true;
}
drawBoard(window.moonQuote);
window.addEventListener('moon:quote', event => drawBoard(event.detail));

const hall = new T.Group();
for (const child of [...scene.children]) if (!beforeHall.has(child)) hall.add(child);
hall.scale.set(2.07,2.06,4.95);
hall.position.z = 25.625;
for(const object of hall.children) {
  if(!beforeChart.has(object)) {
    object.position.z=(object.position.z*2.1-1.45-hall.position.z)/hall.scale.z;
    object.scale.z*=2.1/4.95;
  }
}
for(const step of steps) step.scale.z*=2.1/4.95;
scene.add(hall);
hall.updateMatrixWorld(true);
const floorLevel = 1.246;
const threshold = 10.85;
const rug = new T.MeshStandardMaterial({color:0x752c2a,map:woodGrain,roughness:.97});
const cushionCloth = [0xb15743,0xa34d3a,0xb9794e].map(color => new T.MeshStandardMaterial({color,roughness:.94}));
const seam = new T.MeshStandardMaterial({color:0xc29968,roughness:.89});
const cushionShape = new T.Shape();
cushionShape.moveTo(-.5,-.6); cushionShape.lineTo(.5,-.6);
cushionShape.quadraticCurveTo(.6,-.6,.6,-.5);
cushionShape.lineTo(.6,.5); cushionShape.quadraticCurveTo(.6,.6,.5,.6);
cushionShape.lineTo(-.5,.6); cushionShape.quadraticCurveTo(-.6,.6,-.6,.5);
cushionShape.lineTo(-.6,-.5); cushionShape.quadraticCurveTo(-.6,-.6,-.5,-.6);
const cushionGeometry = new T.ExtrudeGeometry(cushionShape,{depth:.08,bevelEnabled:true,bevelSize:.09,bevelThickness:.065,bevelSegments:3,steps:1,curveSegments:5});
const mats = [];
for (let row=0;row<12;row++) {
  for (let col=-3;col<=3;col++) {
    const x=col*2.52,z=9.05-row*2.08;
    box(1.64,.023,1.64,rug,x,floorLevel+.008,z);
    for(const side of [-1,1]) box(1.49,.012,.024,seam,x,floorLevel+.024,z+side*.74);
    const cushion=mesh(cushionGeometry,cushionCloth[(row+col+3)%3],x,floorLevel+.105,z);
    cushion.rotation.x=-Math.PI/2;
    mats.push({x,z});
  }
}
function heightAt(x,z) {
  if (Math.abs(x)>12.4 || z < -21.7) return 0;
  return T.MathUtils.smoothstep(-z,-threshold-1.65,-threshold) * floorLevel;
}

function avatar(color) {
  const root = new T.Group();
  const body = new T.Group();
  const coat = new T.MeshStandardMaterial({ color });
  const skin = new T.MeshStandardMaterial({ color: 0xe1aa85 });
  const boots = new T.MeshStandardMaterial({ color: 0x24343b });
  scene.add(root);
  root.add(body);
  disc(.34, .52, .82, 16, coat, 0, .61, 0, body);
  const belt = disc(.39,.41,.11,16,trim,0,.76,0,body);
  belt.material = new T.MeshStandardMaterial({color:0x9a4635});
  const shoulder = mesh(new T.SphereGeometry(.39,18,12),coat,0,.89,0,body);
  shoulder.scale.y=.55;
  const faceGroup=new T.Group();
  body.add(faceGroup);
  const head = mesh(new T.SphereGeometry(.342,24,16), skin, 0, 1.28, -.015, faceGroup);
  head.scale.set(1,1.03,.93);
  const face = new T.MeshBasicMaterial({ color:0x352923 });
  const blush = new T.MeshStandardMaterial({ color:0xd58d73 });
  for (const side of [-1,1]) {
    const ear = mesh(new T.SphereGeometry(.08,12,8),skin,side*.319,1.26,-.018,faceGroup);
    ear.scale.y=1.24;
    const eye=mesh(new T.SphereGeometry(.038,12,8),face,side*.114,1.313,-.297,faceGroup);
    eye.scale.set(.81,1.23,.54);
    mesh(new T.SphereGeometry(.01,8,6),new T.MeshBasicMaterial({color:0xfdf6e7}),side*.114-.009,1.329,-.316,faceGroup);
    const cheek=mesh(new T.SphereGeometry(.049,10,8),blush,side*.174,1.228,-.274,faceGroup);
    cheek.scale.set(1,.58,.27);
  }
  const nose=mesh(new T.SphereGeometry(.047,12,8),skin,0,1.258,-.326,faceGroup);
  nose.scale.y=.81;
  const smile=new T.CatmullRomCurve3([new T.Vector3(-.045,1.19,-.306),new T.Vector3(0,1.174,-.318),new T.Vector3(.045,1.19,-.306)]);
  mesh(new T.TubeGeometry(smile,10,.009,6,false),face,0,0,0,faceGroup);
  const sash = box(.125,.59,.042,cream,-.04,.75,-.37,body);
  sash.rotation.z=-.57;
  const leftArm = new T.Group(), rightArm = new T.Group();
  for (const [arm,side] of [[leftArm,-1],[rightArm,1]]) {
    body.add(arm); arm.position.set(.36*side,.9,-.01);
    const sleeve=mesh(new T.SphereGeometry(.16,14,10),coat,0,-.19,0,arm);
    sleeve.scale.y=1.55;
    mesh(new T.SphereGeometry(.093,12,8),skin,0,-.36,-.02,arm);
  }
  const left = box(.215, .17, .31, boots, -.19, .11, -.06, body);
  const right = box(.215, .17, .31, boots, .19, .11, -.06, body);
  const halo = mesh(new T.TorusGeometry(.62, .035, 6, 40), gold, 0, .065, 0, root);
  halo.rotation.x = Math.PI / 2;
  halo.visible = false;
  const rig=new T.Group();
  rig.visible=false;
  root.add(rig);
  const limbs=[-1,1].map(side=>({
    side,
    upper:disc(.114,.144,1,12,coat,0,0,0,rig),
    fore:disc(.09,.117,1,12,coat,0,0,0,rig),
    hand:mesh(new T.SphereGeometry(.096,14,10),skin,0,0,0,rig),
    thigh:disc(.09,.13,1,12,coat,0,0,0,rig),
    shoe:box(.215,.17,.31,boots,0,0,0,rig)
  }));
  const broom=new T.Group();
  broom.visible=false;
  root.add(broom);
  const handle=disc(.031,.036,1,10,wood,0,0,0,broom);
  const straw=material(0xc49451);
  const brush=disc(.08,.20,.32,10,straw,0,0,0,broom);
  brush.scale.z=.56;
  return { root, body, faceGroup, left, right, leftArm, rightArm, halo, rig, limbs, broom, handle, brush, bow: 0, seated: false };
}
const player = avatar(0xb65f3d);
let jumpOffset=0, jumpVelocity=0;
const speechLayer=document.querySelector('#speech');
function clearSpeech(actor) {
  actor.speech?.element.remove();
  actor.speech=null;
}
function speech(actor,message,duration=5000) {
  if(typeof message!=='string' || !message.trim()) return;
  clearSpeech(actor);
  const element=document.createElement('span');
  element.className='speech-bubble';
  element.textContent=message.trim().slice(0,100);
  speechLayer.append(element);
  actor.speech={element,until:performance.now()+duration};
}
const speechPoint=new T.Vector3();
function labelAvatar(actor,nickname) {
  if(!nickname || actor.nickname===nickname) return;
  actor.nickname=nickname;
  if(!actor.nameTag) {
    actor.nameTag=document.createElement('span');
    actor.nameTag.className='avatar-name';
    document.querySelector('#names').append(actor.nameTag);
  }
  actor.nameTag.textContent=nickname;
}
function positionLabel(actor) {
  if(!actor.nameTag) return;
  speechPoint.copy(actor.root.position);
  speechPoint.y+=actor.seated ? 1.18 : 1.63;
  speechPoint.project(camera);
  actor.nameTag.hidden=Math.abs(speechPoint.z)>=1 || Math.abs(speechPoint.x)>1 || Math.abs(speechPoint.y)>1;
  actor.nameTag.style.left=(speechPoint.x*.5+.5)*100+'%';
  actor.nameTag.style.top=(.5-speechPoint.y*.5)*100+'%';
}
function positionSpeech(actor,now) {
  if(!actor.speech) return;
  if(now>=actor.speech.until) return clearSpeech(actor);
  speechPoint.copy(actor.root.position);
  speechPoint.y+=actor.seated ? 1.45 : 1.9;
  speechPoint.project(camera);
  actor.speech.element.hidden=speechPoint.z>=1 || speechPoint.z<=-1 || Math.abs(speechPoint.x)>1 || Math.abs(speechPoint.y)>1;
  actor.speech.element.style.left=(speechPoint.x*.5+.5)*100+'%';
  actor.speech.element.style.top=(.5-speechPoint.y*.5)*100+'%';
}
player.root.rotation.y = Math.PI + .23;
player.root.position.set((Math.random() - .5) * 2.6, 0, 29.0 + Math.random() * .65);
const target = player.root.position.clone();
const ring = mesh(new T.RingGeometry(.18, .24, 26), new T.MeshBasicMaterial({ color: 0xb7f8da, side: T.DoubleSide }), 0, .05, 0);
ring.rotation.x = -Math.PI / 2;
ring.visible = false;

const id = crypto.randomUUID?.() ?? Math.random().toString(36).slice(2);
const peers = new Map();
const channel = window.hoduRoom;
function send(kind,message) {
  channel?.postMessage({kind,id,x:player.root.position.x,z:player.root.position.z,yaw:player.root.rotation.y,
    seated:player.seated,jump:jumpOffset,exercise:player.exercise?.type ?? null,message});
}
window.addEventListener('hodu:speech',event => {
  speech(player,event.detail);
  send('speech',event.detail);
});
function presence() {
  document.querySelector('#presence').textContent = '● ' + (peers.size + 1) + '명';
}
function removePeer(peerId) {
  const peer = peers.get(peerId);
  if (!peer) return;
  clearSpeech(peer);
  peer.nameTag?.remove();
  for(const puff of peer.vapor ?? []) puff.material.dispose();
  scene.remove(peer.root);
  peer.root.traverse(child => {
    if (child.isMesh) {
      child.geometry.dispose();
      if (![trim, gold, jade].includes(child.material)) child.material.dispose();
    }
  });
  peers.delete(peerId);
  presence();
}
if (channel) {
  channel.onmessage = ({ data }) => {
    if (!data || data.id === id) return;
    if (data.kind === 'leave') return removePeer(data.id);
    if (![data.x, data.z, data.yaw].every(Number.isFinite)) return;
    if (!peers.has(data.id)) {
      const peer = avatar(0x86c8b8);
      peer.root.position.set(data.x, heightAt(data.x,data.z), data.z);
      peer.target = peer.root.position.clone();
      peers.set(data.id, peer);
      presence();
    }
    const peer = peers.get(data.id);
    peer.lastSeen = performance.now();
    labelAvatar(peer,data.nickname);
    const jump=Number.isFinite(data.jump) ? Math.max(0,Math.min(data.jump,3)) : 0;
    peer.target.set(data.x,heightAt(data.x,data.z)+jump,data.z);
    peer.seated = data.seated === true;
    peer.root.rotation.y = data.yaw;
    if (data.kind === 'pray') peer.bow = performance.now();
    if (data.kind === 'speech') speech(peer,data.message,5000-(data.age || 0));
    if (data.exercise === 'pull' || data.exercise === 'push' || data.exercise === 'sweep') {
      if (peer.exercise?.type!==data.exercise) peer.exercise={type:data.exercise,start:performance.now()};
    } else peer.exercise=null;
    if (data.kind === 'hello') send('position');
  };
  channel.onsnapshot = (active,nickname) => {
    for (const peerId of peers.keys()) if (!active.has(peerId)) removePeer(peerId);
    labelAvatar(player,nickname);
  };
  channel.onstatus = message => {
    const status=document.querySelector('#room-status');
    status.textContent=message;
    status.hidden=!message;
  };
  window.addEventListener('pagehide', event => { if (!event.persisted) send('leave'); });
  send('hello');
  setInterval(() => send('position'), 4000);
  window.addEventListener('pageshow', () => send('hello'));
}

const seatButton = document.querySelector('#seat');
let nearbyMat = null;
function updateSeat() {
  const p=player.root.position;
  nearbyMat = mats.find(mat => Math.hypot(p.x-mat.x,p.z-mat.z)<.91) ?? null;
  seatButton.hidden = !nearbyMat && !player.seated;
  const label=player.seated ? '일어나기' : '방석에 앉기';
  if(seatButton.textContent!==label) seatButton.textContent=label;

}
function sitOrStand() {
  if (player.bow || player.exercise || jumpOffset>0) return;
  cancelRepeat();
  if (player.seated) player.seated=false;
  else if (nearbyMat) {
    player.seated=true;
    player.root.position.set(nearbyMat.x,floorLevel,nearbyMat.z);
    player.root.rotation.y=0;
  } else return;
  target.copy(player.root.position);
  world.focus({preventScroll:true});
  updateSeat();
  send('position');
}
seatButton.addEventListener('click',sitOrStand);
updateSeat();

const pullButton=document.querySelector('#pull');
const pushButton=document.querySelector('#push');
const sweepButton=document.querySelector('#sweep');
const repeatButton=document.querySelector('#repeat');
let continuous=false, lastActivity=null, nextPrayer=0;
function drawRepeat() {
  repeatButton.hidden=!lastActivity;
  repeatButton.textContent=continuous ? '멈추기' : '계속하기';
  repeatButton.setAttribute('aria-pressed',String(continuous));
}
function cancelRepeat() {
  if (!lastActivity) return;
  lastActivity=null;
  continuous=false;
  drawRepeat();
}
repeatButton.addEventListener('click',()=>{
  if (!lastActivity) return;
  if (continuous) {
    continuous=false;
    stopExercise();
  } else {
    continuous=true;
    if ((lastActivity==='pull' || lastActivity==='push') && !player.exercise) startExercise(lastActivity);
    if (lastActivity==='up' || lastActivity==='down') nextPrayer=performance.now();
  }
  drawRepeat();
  world.focus({preventScroll:true});
});
function nearBar() {
  return Math.hypot(player.root.position.x-exerciseSpot.x,player.root.position.z-exerciseSpot.z)<3;
}
function updateExerciseButtons() {
  pullButton.hidden=!nearBar() && player.exercise?.type!=='pull';
  pushButton.hidden=player.root.position.z<threshold && Math.abs(player.root.position.x)<12.4;
  pullButton.disabled=Boolean(player.exercise) || jumpOffset>0;
  pushButton.disabled=pullButton.disabled;
  const sweeping=player.exercise?.type==='sweep';
  sweepButton.hidden=pushButton.hidden && !sweeping;
  sweepButton.disabled=!sweeping && pushButton.disabled;
  const sweepLabel=sweeping ? '낙엽 쓸기 끄기' : '낙엽 쓸기';
  if(sweepButton.textContent!==sweepLabel) {
    sweepButton.textContent=sweepLabel;
    sweepButton.setAttribute('aria-pressed',String(sweeping));
  }
}
function stopExercise() {
  if (!player.exercise) return;
  player.exercise=null;
  send('position');
}
function startExercise(type) {
  if (player.exercise || player.bow || jumpOffset>0 || (type==='pull' && !nearBar())) return;
  player.seated=false;
  if (type==='pull') {
    player.root.position.set(exerciseSpot.x,0,exerciseSpot.z+.16);
    player.root.rotation.y=0;
  }
  target.copy(player.root.position);
  player.exercise={type,start:performance.now()};
  if(type==='sweep') cancelRepeat();
  else lastActivity=type;
  drawRepeat();
  world.focus({preventScroll:true});
  send('position');
}
pullButton.addEventListener('click',()=>startExercise('pull'));
pushButton.addEventListener('click',()=>startExercise('push'));
sweepButton.addEventListener('click',()=>{
  if(player.exercise?.type==='sweep') stopExercise();
  else startExercise('sweep');
  world.focus({preventScroll:true});
});
updateExerciseButtons();

window.addEventListener('moon:pray', ({detail}) => {
  stopExercise();
  lastActivity=detail;
  nextPrayer=performance.now()+1280;
  drawRepeat();
  player.bow = performance.now();
  if (!player.seated) player.root.rotation.y = Math.atan2(player.root.position.x, player.root.position.z + 17.1);
  target.copy(player.root.position);
  world.focus({ preventScroll: true });
  send('pray');
});

let yaw = .10, elevation = .225, distance = 25.1;
let cameraDistance = distance, exerciseView = 0;
const pointer = new Map();
let moved = false;
const canvas = renderer.domElement;
canvas.addEventListener('pointerdown', event => {
  if (event.button !== 0) return;
  if (!pointer.size) moved = false;
  else moved = true;
  pointer.set(event.pointerId, [event.clientX, event.clientY]);
  canvas.setPointerCapture(event.pointerId);
});
const clamp = T.MathUtils.clamp;
canvas.addEventListener('pointermove', event => {
  const previous = pointer.get(event.pointerId);
  if (!previous) return;
  const dx = event.clientX - previous[0], dy = event.clientY - previous[1];
  if (!moved && Math.hypot(dx, dy) < 5) return;
  moved = true;
  if (pointer.size === 2) {
    const other = [...pointer].find(([key]) => key !== event.pointerId)[1];
    distance = clamp(distance - (Math.hypot(event.clientX - other[0], event.clientY - other[1]) - Math.hypot(previous[0] - other[0], previous[1] - other[1])) * .035, 9, 37);
  } else {
    yaw -= dx * .008;
    elevation = clamp(elevation + dy * .006, .08, .77);
  }
  pointer.set(event.pointerId, [event.clientX, event.clientY]);
});
const ray = new T.Raycaster();
function setTarget(point) {
  const x=clamp(point.x,courtyard.left,courtyard.right);
  const z=clamp(point.z,courtyard.back,courtyard.front);
  target.set(x,0,z);
}
function canWalk(x,z) {
  if (x<courtyard.left || x>courtyard.right || z<courtyard.back || z>courtyard.front) return false;
  const side=Math.abs(x);
  if (z<10.15 && z>-21.9 && side>11.65 && side<12.95) return false;
  if (z<-16.15 && z>-22.1 && side<=12.95) return false;
  return true;
}
function standForMovement() {
  if (!player.seated) return;
  player.seated=false;
  target.copy(player.root.position);
  updateSeat();
  send('position');
}
canvas.addEventListener('pointerup', event => {
  if (!pointer.delete(event.pointerId) || moved || player.bow) return;
  const rect = canvas.getBoundingClientRect();
  ray.setFromCamera(new T.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, 1 - (event.clientY - rect.top) / rect.height * 2), camera);
  const hit = ray.intersectObjects([ground,hallFloor])[0];
  if (hit) {
    standForMovement();
    cancelRepeat();
    if(player.exercise?.type!=='sweep') stopExercise();
    setTarget(hit.point);
    ring.position.set(target.x, heightAt(target.x,target.z)+.044, target.z);
    ring.visible = true;
  }
});
canvas.addEventListener('pointercancel', event => pointer.delete(event.pointerId));
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  distance = clamp(distance + event.deltaY * .015, 8, 26);
}, { passive: false });
const keys = new Set();
const directions = { arrowup: [0, -1], w: [0, -1], arrowdown: [0, 1], s: [0, 1], arrowleft: [-1, 0], a: [-1, 0], arrowright: [1, 0], d: [1, 0] };
window.addEventListener('keydown', event => {
  if (event.ctrlKey || event.metaKey || event.altKey || document.querySelector('dialog[open]')) return;
  if (event.target instanceof HTMLElement && event.target.matches('input, textarea, select, [contenteditable]')) return;
  const key = event.key.toLowerCase();
  if (event.code==='Space') {
    event.preventDefault();
    if (!event.repeat && !player.bow && jumpOffset===0 && jumpVelocity===0) {
      standForMovement();
      cancelRepeat();
      stopExercise();
      jumpVelocity=7.1;
    }
    return;
  }
  if (key === 'e' && !event.repeat) {
    event.preventDefault();
    sitOrStand();
  }
  if (directions[key]) {
    event.preventDefault();
    keys.add(key);
    cancelRepeat();
    if (!player.bow) {
      standForMovement();
      if(player.exercise?.type!=='sweep') stopExercise();
    }
  }
});
window.addEventListener('keyup', event => keys.delete(event.key.toLowerCase()));
window.addEventListener('blur', () => keys.clear());

const focus = new T.Vector3();
let previousFrame = performance.now(), lastSend = 0;
const vaporCanvas=document.createElement('canvas');
vaporCanvas.width=vaporCanvas.height=64;
const vaporInk=vaporCanvas.getContext('2d');
const vaporGradient=vaporInk.createRadialGradient(32,32,2,32,32,31);
vaporGradient.addColorStop(0,'rgba(255,255,250,.92)');
vaporGradient.addColorStop(.42,'rgba(255,255,250,.49)');
vaporGradient.addColorStop(1,'rgba(255,255,250,0)');
vaporInk.fillStyle=vaporGradient;
vaporInk.fillRect(0,0,64,64);
const vaporTexture=new T.CanvasTexture(vaporCanvas);
vaporTexture.colorSpace=T.SRGBColorSpace;
const vaporOrigin=new T.Vector3();
function animateVapor(actor,now) {
  const elapsed=actor.exercise ? now-actor.exercise.start : 0;
  if(elapsed<8000 || actor.exercise?.type==='sweep') {
    for(const puff of actor.vapor ?? []) puff.visible=false;
    return;
  }
  if(!actor.vapor) {
    actor.vapor=Array.from({length:5},()=>{
      const puff=new T.Sprite(new T.SpriteMaterial({map:vaporTexture,transparent:true,depthWrite:false}));
      actor.root.add(puff);
      return puff;
    });
  }
  actor.body.updateMatrix();
  vaporOrigin.set(0,1.58,actor.faceGroup.position.z-.02).applyMatrix4(actor.body.matrix);
  const intensity=Math.min(1,(elapsed-8000)/1600);
  for(const [i,puff] of actor.vapor.entries()) {
    const phase=((elapsed-8000)/1550+i/actor.vapor.length)%1;
    puff.visible=true;
    puff.position.copy(vaporOrigin);
    puff.position.x+=Math.sin(i*2.8+phase*3)*(.05+phase*.22);
    puff.position.y+=.16+phase*.91;
    puff.position.z+=Math.cos(i*2.1)*phase*.19;
    puff.scale.set(.19+phase*.52,.26+phase*.49,1);
    puff.material.opacity=Math.sin(phase*Math.PI)*.57*intensity;
  }
}
const segmentDirection=new T.Vector3();
function connectSegment(segment,from,to) {
  segmentDirection.subVectors(to,from);
  segment.position.copy(from).addScaledVector(segmentDirection,.5);
  segment.scale.y=Math.max(.01,segmentDirection.length());
  segment.quaternion.setFromUnitVectors(T.Object3D.DEFAULT_UP,segmentDirection.normalize());
}
const shoulderPoint=new T.Vector3(), handPoint=new T.Vector3(), elbowPoint=new T.Vector3();
const anklePoint=new T.Vector3(), hipPoint=new T.Vector3(), armAxis=new T.Vector3(), bendAxis=new T.Vector3();
const broomTip=new T.Vector3(), broomTop=new T.Vector3(), brushTop=new T.Vector3(), leafTipWorld=new T.Vector3();
function moveLeaves(actor,tip,dt) {
  leafTipWorld.copy(tip);
  actor.root.localToWorld(leafTipWorld);
  let dirty=false;
  for (let i=0;i<groundLeaves.length;i++) {
    const leaf=groundLeaves[i];
    const dx=leaf.x-leafTipWorld.x,dz=leaf.z-leafTipWorld.z;
    const distance=Math.hypot(dx,dz);
    if(distance>1.18) continue;
    const force=dt*(1.18-distance)*3.3;
    leaf.x+=dx/(distance || 1)*force;
    leaf.z+=dz/(distance || 1)*force;
    leaf.angle+=dt*2;
    pose.position.set(leaf.x,.063,leaf.z);
    pose.rotation.set(-Math.PI/2,0,leaf.angle);
    pose.scale.setScalar(leaf.size);
    pose.updateMatrix();
    leafGround.setMatrixAt(i,pose.matrix);
    dirty=true;
  }
  if(dirty) leafGround.instanceMatrix.needsUpdate=true;
}
function animateExercise(actor,now,dt) {
  const exercise=actor.exercise;
  actor.rig.visible=Boolean(exercise);
  actor.leftArm.visible=actor.rightArm.visible=!exercise;
  const push=exercise?.type==='push';
  const sweep=exercise?.type==='sweep';
  actor.broom.visible=sweep;
  actor.faceGroup.position.z=0;
  actor.left.visible=actor.right.visible=!push;
  if(!exercise) return;
  const t=(now-exercise.start)/1000;
  const cycle=(1-Math.cos(t*Math.PI*2/1.18))*.5;
  const rep=T.MathUtils.smoothstep(cycle,0,1);
  if(push) {
    actor.body.rotation.x=-Math.PI/2+.11-rep*.18;
    actor.body.position.y=.54-rep*.19;
  } else if(sweep) {
    const stroke=Math.sin(t*Math.PI*2/1.12);
    actor.body.rotation.x=-.12;
    actor.body.rotation.y=stroke*.19;
    broomTip.set(stroke*1.09,.08,-.92-.14*rep);
    broomTop.set(stroke*.21,1.21,-.36);
    brushTop.copy(broomTip).lerp(broomTop,.24);
    connectSegment(actor.handle,broomTip,broomTop);
    connectSegment(actor.brush,broomTip,brushTop);
    if(actor===player) moveLeaves(actor,broomTip,dt);
  } else {
    actor.body.rotation.x=.018+rep*.028;
    actor.body.position.y=1.02+rep*.72;
    actor.faceGroup.position.z=.38*T.MathUtils.smoothstep(rep,.06,.46);
    actor.left.position.z=.06+rep*.13;
    actor.right.position.z=.06+rep*.13;
  }
  actor.body.updateMatrix();
  for(const {side,upper,fore,hand,thigh,shoe} of actor.limbs) {
    shoulderPoint.set(side*.34,.88,-.025).applyMatrix4(actor.body.matrix);
    if(push) handPoint.set(side*.43,.088,-.94);
    else if(sweep) handPoint.copy(broomTip).lerp(broomTop,side<0 ? .58 : .85);
    else handPoint.set(side*.45,2.78,-.16);
    armAxis.subVectors(handPoint,shoulderPoint);
    const reach=armAxis.length();
    armAxis.normalize();
    bendAxis.set(side*(push ? .82 : .86),-.38,push ? .72 : .4);
    bendAxis.addScaledVector(armAxis,-bendAxis.dot(armAxis)).normalize();
    const armLength=push ? .43 : .51;
    const bend=Math.sqrt(Math.max(.006,armLength*armLength-reach*reach*.25));
    elbowPoint.copy(shoulderPoint).lerp(handPoint,.5).addScaledVector(bendAxis,bend);
    connectSegment(upper,shoulderPoint,elbowPoint);
    connectSegment(fore,elbowPoint,handPoint);
    hand.position.copy(handPoint);
    hand.scale.set(1,push ? .69 : 1,1);
    thigh.visible=shoe.visible=push;
    if(push) {
      hipPoint.set(side*.17,.24,.04).applyMatrix4(actor.body.matrix);
      anklePoint.set(side*.18,.10,.27);
      connectSegment(thigh,hipPoint,anklePoint);
      shoe.position.copy(anklePoint);
    }
  }
}
function animateAvatar(actor, now, walking, dt) {
  const bowTime = actor.bow ? (now - actor.bow) / 1050 : 1;
  const pulse = bowTime < 1 ? Math.sin(bowTime * Math.PI) : 0;
  if (bowTime >= 1) actor.bow = 0;
  actor.halo.visible = pulse > 0;
  actor.halo.scale.setScalar(1 + pulse * .45);
  actor.body.rotation.x = -pulse * (actor.seated ? .85 : 1.05);
  actor.body.rotation.y=0;
  const swing = walking ? Math.sin(now / 100) * .35 : 0;
  actor.leftArm.rotation.set(pulse * 1.9 + swing, 0, pulse * .81);
  actor.rightArm.rotation.set(pulse * 1.9 - swing, 0, -pulse * .81);
  actor.body.scale.y = actor.seated ? .75 : 1;
  actor.body.position.y = actor.seated ? .06 - pulse * .09 : walking ? Math.abs(Math.sin(now / 95)) * .075 : -pulse * .18;
  actor.left.position.z = walking ? Math.sin(now / 95) * .18 : -.02;
  actor.right.position.z = walking ? -Math.sin(now / 95) * .18 : -.02;
  animateExercise(actor,now,dt);
  animateVapor(actor,now);
}
function resize() {
  camera.aspect = world.clientWidth / Math.max(1, world.clientHeight);
  camera.updateProjectionMatrix();
  renderer.setSize(world.clientWidth, world.clientHeight);
}
new ResizeObserver(resize).observe(world);
resize();

const heading = new T.Vector3();
renderer.setAnimationLoop(now => {
  const dt = Math.min(.07, (now - previousFrame) / 1000);
  previousFrame = now;
  if (player.exercise && player.exercise.type!=='sweep' && !continuous && now-player.exercise.start>=3540) stopExercise();
  if (continuous && (lastActivity==='up' || lastActivity==='down') && !player.bow && now>=nextPrayer) {
    const button=document.getElementById(lastActivity);
    if (!button.disabled) {
      nextPrayer=now+1280;
      button.click();
    }
  }
  if (keys.size && !player.bow) {
    standForMovement();
    if(player.exercise?.type!=='sweep') stopExercise();
    heading.set(0, 0, 0);
    for (const key of keys) {
      heading.x += directions[key][0];
      heading.z += directions[key][1];
    }
    heading.normalize().applyAxisAngle(T.Object3D.DEFAULT_UP, yaw).multiplyScalar(5.4 * dt).add(player.root.position);
    setTarget(heading);
  }
  heading.subVectors(target, player.root.position);
  heading.y = 0;
  const remaining = heading.length();
  if (remaining > .001 && !player.bow && !player.seated) {
    player.root.rotation.y = Math.atan2(-heading.x, -heading.z);
    const ratio=Math.min(1,5.4*dt/remaining);
    const p=player.root.position;
    const nextX=p.x+heading.x*ratio, nextZ=p.z+heading.z*ratio;
    const oldX=p.x, oldZ=p.z;
    if(canWalk(nextX,p.z)) p.x=nextX;
    if(canWalk(p.x,nextZ)) p.z=nextZ;
    if(p.x===oldX && p.z===oldZ) target.copy(p);
  } else ring.visible = false;
  const airborne=jumpVelocity!==0 || jumpOffset>0;
  if(airborne) {
    jumpOffset+=jumpVelocity*dt;
    jumpVelocity-=19*dt;
    if(jumpOffset<=0) {
      jumpOffset=0;
      jumpVelocity=0;
      send('position');
    }
  }
  player.root.position.y=heightAt(player.root.position.x,player.root.position.z)+jumpOffset;
  if(player.exercise?.type==='sweep' && player.root.position.z<threshold && Math.abs(player.root.position.x)<12.4) stopExercise();
  updateSeat();
  updateExerciseButtons();
  animateAvatar(player, now, remaining > .012 && !player.bow && !player.seated,dt);
  for (const [peerId, peer] of peers) {
    if (now - peer.lastSeen > 12000) {
      removePeer(peerId);
      continue;
    }
    const walking = peer.root.position.distanceTo(peer.target) > .025;
    peer.root.position.lerp(peer.target, Math.min(1, dt * 5));
    animateAvatar(peer, now, walking && !peer.bow,dt);
  }
  if ((remaining > .012 || airborne) && now - lastSend > 95) {
    send('position');
    lastSend = now;
  }
  const portrait = camera.aspect < .88;
  const p=player.root.position;
  const inside = Math.abs(p.x)<12.25 ? T.MathUtils.smoothstep(14-p.z,0,5.7) : 0;
  const indoorDistance=6.5+(distance-25.1)*.24;
  const viewDistance = T.MathUtils.lerp(distance*(portrait ? 1.14 : 1),indoorDistance,inside);
  exerciseView=T.MathUtils.lerp(exerciseView,player.exercise && player.exercise.type!=='sweep' ? 1 : 0,Math.min(1,dt*8));
  cameraDistance=T.MathUtils.lerp(cameraDistance,T.MathUtils.lerp(viewDistance,portrait ? 8.8 : 7.1,exerciseView),Math.min(1,dt*8));
  focus.set(
    T.MathUtils.lerp(p.x*(.73+inside*.22),p.x,exerciseView),
    T.MathUtils.lerp(T.MathUtils.lerp(4.7,3.25,inside),player.exercise?.type==='pull' ? 1.6 : .66,exerciseView),
    p.z-T.MathUtils.lerp(T.MathUtils.lerp(8.4,3.85,inside),.35,exerciseView)
  );
  const viewYaw=yaw+exerciseView*.96;
  const viewElevation=T.MathUtils.lerp(elevation,.33,exerciseView);
  camera.position.set(
    focus.x + Math.sin(viewYaw) * Math.cos(viewElevation) * cameraDistance,
    focus.y + Math.sin(viewElevation) * cameraDistance,
    focus.z + Math.cos(viewYaw) * Math.cos(viewElevation) * cameraDistance
  );
  camera.lookAt(focus);
  renderer.render(scene, camera);
  positionLabel(player);
  positionSpeech(player,now);
  for(const peer of peers.values()) {
    positionLabel(peer);
    positionSpeech(peer,now);
  }
});
status.hidden = true;
