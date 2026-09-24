# Derive centerlines from Marine Cadastre 200-ft cable corridor polygons (Voronoi medial axis + spur pruning).
import json, time
import numpy as np, networkx as nx, shapely
from shapely.geometry import shape, mapping, LineString
from shapely.ops import transform, linemerge
from pyproj import Transformer
PROJ="+proj=aea +lat_1=43 +lat_2=47 +lat_0=45 +lon_0=-127 +datum=NAD83 +units=m"
fwd=Transformer.from_crs("EPSG:4269",PROJ,always_xy=True).transform
inv=Transformer.from_crs(PROJ,"EPSG:4326",always_xy=True).transform
d=json.load(open('mc_rsn_backbone_polygons.geojson'))
out={}
for f in d['features']:
    oid=f['properties']['OBJECTID']
    if oid not in (506,508): continue
    poly=transform(fwd, shape(f['geometry'])).buffer(0)
    pts=shapely.get_coordinates(shapely.segmentize(poly.boundary, 8))
    vor=shapely.voronoi_polygons(shapely.MultiPoint(pts), only_edges=True)
    segs=[]
    for e in shapely.get_parts(vor):
        c=shapely.get_coordinates(e)
        for i in range(len(c)-1): segs.append(LineString([c[i],c[i+1]]))
    segs=np.array(segs,dtype=object)
    shapely.prepare(poly)
    segs=segs[shapely.contains(poly, segs)]
    G=nx.Graph()
    key=lambda p:(round(p[0],3),round(p[1],3))
    for s in segs:
        a,b=[key(p) for p in s.coords]
        if a!=b: G.add_edge(a,b,w=s.length)
    # iterative spur pruning: remove leaf chains shorter than L
    L=150.0
    changed=True
    while changed:
        changed=False
        leaves=[n for n in G.nodes if G.degree(n)==1]
        for lf in leaves:
            if lf not in G or G.degree(lf)!=1: continue
            chain=[lf]; length=0; cur=lf; prev=None
            while True:
                nbrs=[n for n in G.neighbors(cur) if n!=prev]
                if len(nbrs)!=1: break
                nxt=nbrs[0]; length+=G[cur][nxt]['w']; prev,cur=cur,nxt; chain.append(cur)
                if G.degree(cur)!=2 or length>L: break
            if length<=L and G.degree(cur)>=3:
                G.remove_nodes_from(chain[:-1]); changed=True
    G.remove_nodes_from([n for n in list(G.nodes) if G.degree(n)==0])
    comps=list(nx.connected_components(G))
    lines=[LineString([u,v]) for u,v in G.edges]
    merged=linemerge(lines)
    parts=list(shapely.get_parts(merged))
    leaves=[n for n in G.nodes if G.degree(n)==1]; junc=[n for n in G.nodes if G.degree(n)>=3]
    print(oid,'components',len(comps),'parts',len(parts),'total km',round(sum(p.length for p in parts)/1000,1))
    print('  leaves',[tuple(round(c,5) for c in inv(*n)) for n in leaves])
    print('  junctions',[tuple(round(c,5) for c in inv(*n)) for n in junc])
    print('  part lens km',sorted([round(p.length/1000,2) for p in parts],reverse=True))
    out[oid]=[mapping(transform(inv,p.simplify(3))) for p in parts]
json.dump(out,open('skeleton_raw.json','w'))
