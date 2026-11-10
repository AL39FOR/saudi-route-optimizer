"""Reproducible geographic *screening*, not official route certification.

Usage: python priority_audit.py
Reads the measured arcs only. Writes two independently usable comparison maps and
one CSV. It never modifies source CSV or route approval statuses.
"""
from __future__ import annotations
import csv,json,math
from pathlib import Path
import folium

HERE=Path(__file__).resolve().parent
PRIORITY=('L044','L061','L068')

def read(name):
    with (HERE/name).open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def haversine(a,b):
    p1, l1, p2, l2 = *map(math.radians,a), *map(math.radians,b)
    q=math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin((l2-l1)/2)**2
    return 12742*math.asin(math.sqrt(min(1,max(0,q))))

def project(pts):
    # Local equirectangular projection in kilometers (for screening only).
    mid=sum(pt[0] for pt in pts)/len(pts)
    return [(p[1]*111.195*math.cos(math.radians(mid)),p[0]*111.195) for p in pts]

def xy(pts,ref_lat):
    return [(lon*111.195*math.cos(math.radians(ref_lat)),lat*111.195) for lat,lon in pts]

def dist_point_poly(p,line):
    x,y=p;best=float('inf')
    for (ax,ay),(bx,by) in zip(line,line[1:]):
        dx=bx-ax;dy=by-ay
        if dx*dx+dy*dy < 1e-12:
            qx,qy=ax,ay
        else:
            t=min(1,max(0,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy)))
            qx,qy=ax+t*dx,ay+t*dy
        best=min(best,math.hypot(x-qx,y-qy))
    return best

def resample(line,step_km=1):
    result=[line[0]]
    for (ax,ay),(bx,by) in zip(line,line[1:]):
        span=math.hypot(bx-ax,by-ay)
        n=max(1,math.ceil(span/step_km))
        for j in range(1,n+1):
            t=j/n;result.append((ax+(bx-ax)*t,ay+(by-ay)*t))
    return result

def analysis(link_id):
    rows=read('road_distances_osrm.csv')
    pair={r['direction']:r for r in rows if r['link_id']==link_id}
    if set(pair)!={'A_TO_B','B_TO_A'}: raise ValueError(f'Missing directions: {link_id}')
    f=pair['A_TO_B'];r=pair['B_TO_A']
    f_pts=json.loads(f['geometry_json']);r_pts=json.loads(r['geometry_json'])
    if len(f_pts)<2 or len(r_pts)<2:raise ValueError('Missing route geometry')
    base_lat=sum(pt[0] for pt in f_pts+r_pts)/(len(f_pts)+len(r_pts))
    aa=xy(f_pts,base_lat);bb=xy(r_pts,base_lat)
    a_points=resample(aa);b_points=resample(bb)
    da=[dist_point_poly(pt,bb) for pt in a_points]
    db=[dist_point_poly(pt,aa) for pt in b_points]
    km=float(f['distance_km']);rev=float(r['distance_km']);air=haversine(f_pts[0],f_pts[-1])
    matches=sum(d<2 for d in da)+sum(d<2 for d in db)
    overlap=matches/(len(da)+len(db))*100
    maxsep=max(*da,*db)
    avgsep=(sum(da)+sum(db))/(len(da)+len(db))
    if maxsep>5: label='DIFFERENT_DIRECTIONAL_CORRIDORS'
    elif km/air>2.3: label='LONG_DETOUR_SHARED_CORRIDOR'
    else:label='SIMILAR_ROAD_GEOMETRY'
    return dict(link_id=link_id,from_ar=f['from_ar'],to_ar=f['to_ar'],forward_km=km,reverse_km=rev,
                forward_min=float(f['duration_min']),reverse_min=float(r['duration_min']),
                air_km=round(air,2),forward_air_ratio=round(km/air,2),
                reverse_air_ratio=round(rev/air,2),direction_diff_km=round(abs(km-rev),3),
                max_geometry_separation_km=round(maxsep,2),
                mean_geometry_separation_km=round(avgsep,2),
                within_2km_pct=round(overlap,1),
                endpoint_snap_max_m=max(float(f['snap_start_m']),float(f['snap_end_m']),float(r['snap_start_m']),float(r['snap_end_m'])),
                geom_pt_count_forward=len(f_pts),geom_pt_count_reverse=len(r_pts),
                screening_label=label,verification='MANUAL_ROAD_REVIEW_REQUIRED',
                forward_geometry=f_pts,reverse_geometry=r_pts)

def audit_map(result):
    pts=result['forward_geometry']+result['reverse_geometry']
    lat=(min(p[0] for p in pts)+max(p[0] for p in pts))/2
    lon=(min(p[1] for p in pts)+max(p[1] for p in pts))/2
    m=folium.Map(location=[lat,lon],zoom_start=9,tiles='OpenStreetMap',control_scale=True)
    folium.PolyLine(result['forward_geometry'],color='#0cae9d',weight=7,opacity=.86,
                    tooltip=f"{result['from_ar']} → {result['to_ar']}: {result['forward_km']:.1f} كم · {result['forward_min']:.0f} دقيقة").add_to(m)
    folium.PolyLine(result['reverse_geometry'],color='#dc6f35',weight=5,opacity=.84,dash_array='12 7',
                    tooltip=f"{result['to_ar']} → {result['from_ar']}: {result['reverse_km']:.1f} كم · {result['reverse_min']:.0f} دقيقة").add_to(m)
    folium.Marker(result['forward_geometry'][0],tooltip=result['from_ar'],icon=folium.Icon(color='green',icon='flag')).add_to(m)
    folium.Marker(result['forward_geometry'][-1],tooltip=result['to_ar'],icon=folium.Icon(color='blue',icon='flag')).add_to(m)
    folium.PolyLine([result['forward_geometry'][0],result['forward_geometry'][-1]],color='#9ca3af',
                    weight=2,opacity=.7,dash_array='4 10',tooltip='خط جوي توضيحي — ليس طريق قيادة').add_to(m)
    m.fit_bounds([[min(p[0] for p in pts),min(p[1] for p in pts)],
                  [max(p[0] for p in pts),max(p[1] for p in pts)]],padding=(24,24))
    from branca.element import Element
    legend="""<div style="position:fixed;z-index:999;left:15px;top:15px;background:#10293de8;color:white;border-radius:13px;padding:15px;max-width:360px;font:13px system-ui;direction:rtl;text-align:right;box-shadow:0 5px 15px #0004">
    <strong>مقارنة اتجاهي الطريق — للمراجعة فقط</strong><div style="margin-top:7px"><span style="color:#0cae9d">━━</span> الاتجاه الأول&nbsp;&nbsp; <span style="color:#dc6f35">┄┄</span> الاتجاه المعاكس</div>
    <div style="font-size:11px;opacity:.9;margin-top:5px">خطوط OSRM مبسطة، لا تعني تأكيد صلاحية أو إغلاق أي طريق.</div></div>"""
    m.get_root().html.add_child(Element(legend))
    return m.get_root().render()

def main():
    audits=[analysis(lid) for lid in PRIORITY]
    fields=[k for k in audits[0] if not k.endswith('_geometry')]
    with (HERE/'priority_route_audit_v11.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:v for k,v in a.items() if k in fields} for a in audits)
    for a in audits:
        (HERE/f"compare_{a['link_id']}_v11.html").write_text(audit_map(a),encoding='utf-8')
        print(a['link_id'],a['from_ar'],'<->',a['to_ar'],
              'dist',a['forward_km'],a['reverse_km'],
              'max-gap',a['max_geometry_separation_km'],'km',
              'near-same-percent',a['within_2km_pct'],
              'status',a['screening_label'])
    print('Original measurement data are unchanged.')
    return audits

if __name__=='__main__':main()
