# Build rca_cable.geojson from Marine Cadastre corridor centerlines (skeleton_raw.json) + OOI node positions.
import json, math
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import linemerge, split, substring, transform
from pyproj import Transformer, Geod
PROJ="+proj=aea +lat_1=43 +lat_2=47 +lat_0=45 +lon_0=-127 +datum=NAD83 +units=m"
fwd=Transformer.from_crs("EPSG:4326",PROJ,always_xy=True).transform
inv=Transformer.from_crs(PROJ,"EPSG:4326",always_xy=True).transform
geod=Geod(ellps="WGS84")
sk=json.load(open('skeleton_raw.json'))
def dm(d,m): return -(abs(d)+m/60) if d<0 else d+m/60
def box_center(pts): return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))

MC_URL="https://marinecadastre.gov/downloads/data/mc/SubmarineCable.zip"
MC_SRC="NOAA/BOEM Marine Cadastre 'Submarine Cable Areas' (SubmarineCable.gpkg, OBJECTID %s 'RSN Backbone Cable'); centerline derived from the ~61 m (200 ft) right-of-way corridor polygon by Voronoi medial axis"
FLY="https://oceanobservatories.org/for-mariners/"

def parts(oid):
    return [LineString(p['coordinates']) for p in sk[str(oid)]]
def near(ls, lon, lat, tol=1e-4):
    return Point(ls.coords[0]).distance(Point(lon,lat))<tol or Point(ls.coords[-1]).distance(Point(lon,lat))<tol
def pick(oid, a, b):
    """part whose endpoints are a and b (lon,lat, 4 dp)"""
    for p in parts(oid):
        A,B=Point(p.coords[0]),Point(p.coords[-1]); tol=2e-4
        if A.distance(Point(a))<tol and B.distance(Point(b))<tol: return p
        if B.distance(Point(a))<tol and A.distance(Point(b))<tol: return LineString(list(p.coords)[::-1])
    raise KeyError((oid,a,b))
def chain(*ls):
    coords=[]
    for l in ls:
        c=list(l.coords)
        if coords and Point(coords[-1]).distance(Point(c[0]))>2e-4: raise ValueError('gap')
        coords+= c if not coords else c[1:]
    return LineString(coords)
def km(ls): return geod.geometry_length(ls)/1000
def cut_at(ls, lon, lat):
    """split line at the point on it closest to (lon,lat) (in projected metres)"""
    lp=transform(fwd, ls); d=lp.project(transform(fwd, Point(lon,lat)))
    a=transform(inv, substring(lp,0,d)); b=transform(inv, substring(lp,d,lp.length))
    off=transform(fwd,Point(lon,lat)).distance(lp.interpolate(d))
    return a,b,off

feats=[]
def addline(name, geom, source, url, acc, **kw):
    g=LineString([(round(x,6),round(y,6)) for x,y in geom.coords])
    props=dict(name=name, source=source, source_url=url, accuracy=acc, length_km=round(km(g),2)); props.update(kw)
    feats.append({"type":"Feature","properties":props,"geometry":{"type":"LineString","coordinates":[list(c) for c in g.coords]}})
def addpt(name, lon, lat, source, url, acc, **kw):
    props=dict(name=name, source=source, source_url=url, accuracy=acc); props.update(kw)
    feats.append({"type":"Feature","properties":props,"geometry":{"type":"Point","coordinates":[round(lon,6),round(lat,6)]}})

# ---------- node / point positions ----------
LAND=(-123.9695,45.2018)   # common landfall of both MC corridors
PN1A_J=(-125.4006,44.5057); PN1A_LEAF=(-125.3982,44.5096)
PN1B_J=(-125.1493,44.4784)
kce_pn1b=box_center([(dm(-125,9.47),dm(44,29.29)),(dm(-125,8.33),dm(44,29.29)),(dm(-125,8.34),dm(44,28.48)),(dm(-125,9.47),dm(44,28.48))])
kce_pn1c=Polygon([(dm(-124,58.22),dm(44,22.38)),(dm(-124,57.21),dm(44,23.07)),(dm(-124,56.06),dm(44,22.20)),(dm(-124,56.68),dm(44,21.59)),(dm(-124,57.60),dm(44,21.37)),(dm(-124,58.32),dm(44,21.47))]).centroid.coords[0]
kce_pn1d=box_center([(dm(-124,27.77),dm(44,41.73)),(dm(-124,27.07),dm(44,41.73)),(dm(-124,27.07),dm(44,41.23)),(dm(-124,27.77),dm(44,41.23))])
vaa_pn5a=box_center([(dm(-127,18.15),dm(45,46.34)),(dm(-127,15.27),dm(45,46.34)),(dm(-127,15.26),dm(45,44.34)),(dm(-127,18.14),dm(45,44.33))])
vaa_pn3b=box_center([(dm(-129,59.63),dm(45,57.48)),(dm(-129,56.77),dm(45,57.48)),(dm(-129,56.70),dm(45,55.47)),(dm(-129,59.63),dm(45,55.47))])
MJ03A=(-129.736708,45.820189)   # OOI asset-management RS03AXBS-MJ03A (proxy for PN3A)
print('KCE PN1B',kce_pn1b,'KCE PN1C',kce_pn1c,'KCE PN1D',kce_pn1d,'VAA PN5A',vaa_pn5a,'VAA PN3B',vaa_pn3b)

# ---------- SOUTH line (OBJECTID 506) ----------
s_shore_pn1a=chain(pick(506,LAND,PN1A_J), pick(506,PN1A_J,PN1A_LEAF))
addline("South backbone: Pacific City landfall -> PN1A (Slope Base)", s_shore_pn1a, MC_SRC%506, MC_URL, "charted", line="south",
        note="Last ~0.46 km is a short stub from the corridor junction to the corridor terminus taken as PN1A.")
s_pn1a_pn1b=chain(pick(506,PN1A_J,(-125.3318,44.4421)), pick(506,(-125.3318,44.4421),(-125.3307,44.4424)), pick(506,(-125.3307,44.4424),PN1B_J))
addline("South backbone: PN1A (Slope Base) -> PN1B (Southern Hydrate Ridge)", s_pn1a_pn1b, MC_SRC%506, MC_URL, "charted", line="south")
addline("Extension: PN1B -> Southern Hydrate Ridge summit (LJ01B/MJ01B)", pick(506,PN1B_J,(-125.1481,44.5691)), MC_SRC%506, MC_URL, "charted", line="south",
        note="Corridor terminus coincides with RS01SUM1-LJ01B / RS01SUM2-MJ01B asset-management positions (<0.2 km).")
rest=pick(506,PN1B_J,(-124.3057,44.6375))
coszo_pn1c=(dm(-124,57.72),dm(44,21.82))
a,rest2,off_c=cut_at(rest,*coszo_pn1c); b,c,off_d=cut_at(rest2,*kce_pn1d)
print('PN1C offset from line m',round(off_c),'PN1D offset m',round(off_d))
for nm,pt in [('LV01C',(-124.954078,44.369296)),('COSZO PN01C',(dm(-124,57.72),dm(44,21.82))),('COSZO PN01D',(dm(-124,27.42),dm(44,41.48))),('COSZO PN01B',(dm(-125,8.90),dm(44,28.89))),('MJ01A',(-125.405235,44.509883))]:
    L=s_pn1a_pn1b if nm=='MJ01A' else rest
    print(nm, round(transform(fwd,L).distance(transform(fwd,Point(pt)))),'m from line')
addline("South backbone: PN1B -> PN1C (Oregon Offshore)", a, MC_SRC%506, MC_URL, "charted", line="south",
        note="Split at the point on the corridor centerline closest to the COSZO PN01C ROV site (%.0f m off-line)."%off_c)
addline("South backbone: PN1C (Oregon Offshore) -> PN1D (Oregon Shelf)", b, MC_SRC%506, MC_URL, "charted", line="south",
        note="Split at the point closest to the KCE-PN1D safety box centre (%.0f m off-line)."%off_d)
addline("Extension: PN1D -> Oregon Shelf MJ01C (80 m)", c, MC_SRC%506, MC_URL, "charted", line="south",
        note="Corridor terminus coincides with CE02SHBP-MJ01C asset-management position.")
unk=chain(pick(506,(-125.4614,44.454),(-125.3318,44.4421)))
addline("Unidentified RSN segment west of PN1A->PN1B leg (dead-end stub)", unk, MC_SRC%506, MC_URL, "charted", line="south",
        note="Present in the Marine Cadastre RSN corridor but role not documented (possibly spare/abandoned cable end, repair bight, or original lay). Not a confirmed live path.")
addline("Unidentified short stub near PN1A->PN1B junction", pick(506,(-125.3279,44.4442),(-125.3307,44.4424)), MC_SRC%506, MC_URL, "charted", line="south",
        note="0.3 km stub; could be skeleton artefact of the corridor polygon or a short cable bight.")

# ---------- NORTH line (OBJECTID 508) ----------
J5=(-127.1758,45.7902); J5W=(-127.2765,45.7754)
n1=pick(508,LAND,J5)
# two parallel ~9 km paths between J5 and J5W
loop=[p for p in parts(508) if near(p,*J5) and near(p,*J5W)]
loop=sorted(loop,key=lambda l:l.length,reverse=True)
def orient(l,start):
    return l if Point(l.coords[0]).distance(Point(start))<1e-4 else LineString(list(l.coords)[::-1])
la=orient(loop[0],J5); lb=orient(loop[1],J5)
addline("North backbone: Pacific City landfall -> PN5A area (east junction)", n1, MC_SRC%508, MC_URL, "charted", line="north")
addline("North backbone near PN5A: path A", la, MC_SRC%508, MC_URL, "charted", line="north",
        note="Corridor contains two roughly parallel cables between the east junction and the PN5A spur (in/out lay to the node or a repair re-lay); which is live is not documented.")
addline("North backbone near PN5A: path B", lb, MC_SRC%508, MC_URL, "charted", line="north", note="See path A.")
# spur to PN5A from the tiny junction cluster
sp=[p for p in parts(508) if near(p,-127.2784,45.7555)][0]
addline("Spur: backbone -> PN5A (Mid-Plate)", orient(sp,(-127.2777,45.7735)), MC_SRC%508, MC_URL, "charted", line="north",
        note="Corridor terminus matches the centre of the VAA-PN5A box on the OOI safety flyer (<0.1 km). Sub-100 m junction clutter between loop and spur omitted.")
west=[p for p in parts(508) if near(p,-128.8949,45.8364)][0]
west=orient(west,(-127.2788,45.7755))
addline("North backbone: PN5A area -> US EEZ limit (toward PN3A)", west, MC_SRC%508, MC_URL, "charted", line="north",
        note="Marine Cadastre geometry stops at the US EEZ boundary; cable continues to Axial Base (see approximate segment).")
for tgt,label in [((-127.3321,45.7764),"west"),((-127.2417,45.8438),"north-north-east")]:
    p=[q for q in parts(508) if near(q,*tgt)][0]
    addline("Unidentified stub near PN5A (%s)"%label, orient(p,tgt), MC_SRC%508, MC_URL, "charted", line="north",
            note="Dead-end cable in the Marine Cadastre RSN corridor near PN5A; role not documented (possibly spare/abandoned end or future-expansion stub).")
# beyond EEZ: approximate
eez=west.coords[-1]
g=geod.npts(eez[0],eez[1],MJ03A[0],MJ03A[1],30)
addline("North backbone (approximate): US EEZ limit -> PN3A (Axial Base)", LineString([eez]+g+[MJ03A]),
        "Approximation: geodesic from the Marine Cadastre corridor end at the EEZ limit to the RS03AXBS-MJ03A position (OOI asset-management) used as PN3A proxy",
        "https://github.com/oceanobservatories/asset-management/blob/master/deployment/RS03AXBS_Deploy.csv", "approximate", line="north",
        note="No public geometry found beyond the EEZ. True lay likely deviates by up to several km.")
g2=geod.npts(MJ03A[0],MJ03A[1],vaa_pn3b[0],vaa_pn3b[1],20)
addline("North backbone (approximate): PN3A (Axial Base) -> PN3B (Axial Caldera)", LineString([MJ03A]+g2+[vaa_pn3b]),
        "Approximation: geodesic between PN3A proxy (MJ03A) and centre of VAA-PN3B box on OOI safety flyer", FLY, "approximate", line="north",
        note="Real cable climbs the southern/eastern flank of Axial Seamount into the caldera; route shape unknown.")

# ---------- points ----------
addpt("Pacific City cable landfall (both RCA lines)", *LAND, MC_SRC%'506/508'+" (common landward terminus)", MC_URL, "charted",
      kind="landfall", note="Beach landfall; cables run underground north from a beach manhole to the shore station.")
addpt("RCA Shore Station, Pacific City, OR (approximate)", *LAND, "Location stated by OOI/Interactive Oceans as Pacific City, OR; no published coordinates found - placed at the cable landfall",
      "https://interactiveoceans.washington.edu/technology/cabled-network/", "approximate", kind="shore_station",
      note="Building is inland/north of the landfall via conduits; exact position not published (likely within ~1 km).")
addpt("PN1A (Slope Base)", *PN1A_LEAF, MC_SRC%506+"; terminus of short stub at Slope Base corridor junction", MC_URL, "approximate", kind="primary_node",
      depth_m=2900, note="No published node coordinates. Within ~0.6 km of RS01SLBS-MJ01A (44.50988,-125.40524) from OOI asset-management.")
addpt("PN1B (Southern Hydrate Ridge)", *kce_pn1b, "OOI safety flyer PC01A-LV01B-S2HR-PN1B: centre of KCE-PN1B box (44°28.48'-29.29'N, 125°08.33'-09.47'W); corroborated by COSZO cruise plan site PN01B 44°28.89'N 125°08.90'W, ~1249 m, and by MC corridor junction (<0.4 km)",
      "https://oceanobservatories.org/wp-content/uploads/2015/09/PC01A-LV01B-S2HR-PN1B-Safety-FlyerREDUCED.pdf", "charted", kind="primary_node", depth_m=1249)
addpt("PN1C (Oregon Offshore)", *coszo_pn1c, "COSZO ship-time request (repo data/coszo, datamsri p.41) ROV site PN01C 44°21.82'N 124°57.72'W ~620 m; lies 74 m from the MC corridor centerline and inside the KCE-PN1C/LV01C polygon on the OOI safety flyer",
      "https://oceanobservatories.org/wp-content/uploads/2015/09/PN1C-PN1D-MPJ01C-Safety-FlyerREDUCED.pdf", "charted", kind="primary_node", depth_m=600)
addpt("PN1D (Oregon Shelf)", *kce_pn1d, "OOI safety flyer PN1C-PN1D-MPJ01C: centre of KCE-PN1D box (44°41.23'-41.73'N, 124°27.07'-27.77'W); corroborated by COSZO site PN01D 44°41.48'N 124°27.42'W ~113 m",
      "https://oceanobservatories.org/wp-content/uploads/2015/09/PN1C-PN1D-MPJ01C-Safety-FlyerREDUCED.pdf", "charted", kind="primary_node", depth_m=113)
addpt("PN5A (Mid-Plate)", *vaa_pn5a, "OOI safety flyer PN3B-PC03A-PN5A: centre of VAA-PN5A box; matches MC corridor spur terminus",
      "https://oceanobservatories.org/wp-content/uploads/2015/09/PN3B-PC03A-PN5A-Saftey-Flyer_v2REDUCED.pdf", "charted", kind="primary_node", depth_m=2800)
addpt("PN3A (Axial Base) - proxy", *MJ03A, "OOI asset-management RS03AXBS-MJ03A position used as proxy (PN3A itself has no published coordinates)",
      "https://github.com/oceanobservatories/asset-management/blob/master/deployment/RS03AXBS_Deploy.csv", "approximate", kind="primary_node", depth_m=2600,
      note="Expect PN3A within ~1-2 km of MJ03A.")
addpt("PN3B (Axial Caldera / ASHES) - approximate", *vaa_pn3b, "OOI safety flyer PN3B-PC03A-PN5A: centre of VAA-PN3B box (a ~2 x 2.5 nm avoidance area, not the node itself)",
      "https://oceanobservatories.org/wp-content/uploads/2015/09/PN3B-PC03A-PN5A-Saftey-Flyer_v2REDUCED.pdf", "approximate", kind="primary_node", depth_m=1500,
      note="Node lies somewhere inside the VAA box (±2 km); box covers ASHES/International District/Eastern caldera.")
addpt("Oregon Shelf MJ01C (south line terminus)", -124.305531,44.637381, "OOI asset-management CE02SHBP-MJ01C", "https://github.com/oceanobservatories/asset-management/blob/master/deployment/CE02SHBP_Deploy.csv", "surveyed", kind="junction_box")
addpt("Southern Hydrate Ridge LJ01B (summit extension terminus)", -125.147912,44.569160, "OOI asset-management RS01SUM1-LJ01B", "https://github.com/oceanobservatories/asset-management/blob/master/deployment/RS01SUM1_Deploy.csv", "surveyed", kind="junction_box")

fc={"type":"FeatureCollection",
    "name":"OOI Regional Cabled Array cable routes",
    "description":"Centerlines derived from NOAA/BOEM Marine Cadastre 'Submarine Cable Areas' RSN Backbone Cable corridors (public domain US Gov data; 'For coastal and ocean planning', not for navigation) plus OOI node positions. Segments beyond the US EEZ are approximate.",
    "features":feats}
json.dump(fc,open('rca_cable.geojson','w'),indent=1)
for f in feats:
    p=f['properties']; print(f['geometry']['type'][:4], p['accuracy'][:6], p.get('length_km',''), p['name'], f['geometry']['coordinates'] if f['geometry']['type']=='Point' else '')
