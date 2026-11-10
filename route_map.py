"""Folium/Leaflet result view with clickable, dimmed alternatives and journey stages.

No live traffic, GPS or road closure information is inferred.
"""
from __future__ import annotations
import json
from html import escape
from typing import Any
import folium
from branca.element import Element


def trip_map_html(trips, graph, waypoints, coordinates, metric='duration_min') -> str:
    """Create an interactive standalone HTML Leaflet map from computed routes."""
    fmap = folium.Map(location=[23.3, 44.9], zoom_start=6,
                      tiles='OpenStreetMap', control_scale=True, prefer_canvas=True,
                      zoom_control=True)
    boundaries = []
    route_layers = []
    journey_data = []
    for ti, trip in enumerate(trips):
        layer_list = []
        js_legs = []
        for li, leg in enumerate(trip.legs):
            seg_list = []
            for a,b in zip(leg.cities, leg.cities[1:]):
                data = graph[a][b]
                geo = data.get('geom', [])
                if not isinstance(geo, list) or len(geo) < 2:
                    continue
                boundaries.extend(geo)
                poly = folium.PolyLine(
                    geo, color='#9aa4af', weight=4, opacity=.25,
                    tooltip=escape(f'طريق {ti+1}: {a} ← {b} · {data["distance_km"]:,.1f} كم'),
                )
                poly.add_to(fmap)
                seg_list.append(poly.get_name())
            layer_list.append(seg_list)
            js_legs.append(dict(start=leg.start, end=leg.end,
                                km=round(leg.km,1), minutes=round(leg.minutes,1),
                                via=list(leg.cities)))
        route_layers.append(layer_list)
        journey_data.append(dict(km=round(trip.km,1), minutes=round(trip.minutes,1),
                                 legs=js_legs))
    for idx, city in enumerate(waypoints):
        c=coordinates.get(city)
        if not c: continue
        xy=[c[0],c[1]]
        boundaries.append(xy)
        folium.CircleMarker(xy,radius=8 if idx in (0,len(waypoints)-1) else 6,
            fill=True, fill_color=('#13b8a4' if idx==0 else '#f49b72' if idx==len(waypoints)-1 else '#52718c'),
            fill_opacity=1,color='#ffffff',weight=2,tooltip=f'{idx+1}. {city}').add_to(fmap)
    if boundaries:
        fmap.fit_bounds(boundaries,padding=(42,42))
    panel = '''
    <style>
      .sro-panel{font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif;position:fixed;z-index:9999;
      left:16px;top:16px;width:315px;max-width:calc(100% - 32px);max-height:calc(100% - 34px);overflow-y:auto;
      direction:rtl;text-align:right;background:rgba(13,31,45,.96);color:#fff;border:1px solid #2e4a5f;
      border-radius:18px;box-shadow:0 17px 36px #071b2c7a;padding:15px;box-sizing:border-box}
      .sro-head{font-weight:800;font-size:16px;letter-spacing:.1px}
      .sro-sub{color:#afc3cf;font-size:11px;margin-top:4px;line-height:1.7}
      .sro-route{display:flex;align-items:center;gap:10px;width:100%;text-align:right;direction:rtl;
      background:#1a3448;color:#d4e2e9;border:1px solid #344e61;border-radius:11px;padding:10px;
      margin-top:8px;cursor:pointer;font-family:inherit}
      .sro-route.active{background:#124f53;border-color:#26dab5;color:#fff;box-shadow:0 0 0 1px #26dab53b}
      .sro-route .rt-index{width:25px;height:25px;flex-shrink:0;background:#375369;border-radius:8px;
      display:flex;align-items:center;justify-content:center;font-weight:700}
      .sro-route.active .rt-index{background:#31d3b2;color:#073d3c}
      .sro-route .rt-main{flex:1;font-size:12px;font-weight:700}
      .sro-route .rt-sub{color:#b1c5cf;font-size:11px;font-weight:400;margin-top:3px}
      .sro-summary{border:1px solid #2c4b58;background:#173445;border-radius:12px;padding:12px;margin-top:12px}
      .sro-mini{font-size:11px;color:#b7ced5;margin-bottom:7px}
      .sro-stats{display:flex;gap:10px;justify-content:space-between;font-size:13px;font-weight:800}
      .sro-stage{font-size:11px;border-right:3px solid #6b8593;margin-top:8px;padding:6px 9px;
      color:#94adb9;background:#1a3447;border-radius:5px}
      .sro-stage.on{border-color:#26dab5;color:#fff;background:#175051}
      .sro-stage.done{border-color:#64748b;color:#a8b2b8}
      .sro-stage small{display:block;color:#bacbd3;margin-top:3px}
      .sro-next{background:#26bd9c;color:#073a3d;border:0;border-radius:9px;padding:9px 14px;
      margin-top:10px;width:100%;font-weight:800;cursor:pointer;font-family:inherit}
      .sro-next:disabled{background:#49616f;color:#a8c0cc;cursor:default}
      .sro-foot{font-size:10px;color:#bacbd3;line-height:1.65;margin-top:10px}
      @media(max-width:680px){.sro-panel{top:8px;left:8px;width:265px;max-height:65%;padding:11px}.sro-head{font-size:13px}}
    </style>
    <div class="sro-panel" id="sro-panel">
      <div class="sro-head">Saudi Route Optimizer</div>
      <div class="sro-sub" id="sro-od"></div>
      <div class="sro-sub">اضغط على أي طريق في الخريطة أو اختره من القائمة</div>
      <div id="sro-routes"></div>
      <div class="sro-summary">
         <div class="sro-mini" id="sro-choice"></div>
         <div class="sro-stats" id="sro-totals"></div>
         <div id="sro-stages"></div>
         <button type="button" class="sro-next" id="sro-next">وصلت إلى المحطة التالية</button>
      </div>
      <div class="sro-foot">⚠️ نتائج بحثية من شبكة محدودة غير معتمدة نهائيًا؛ ليست ملاحة مباشرة أو تتبع GPS.</div>
    </div>
    '''
    fmap.get_root().html.add_child(Element(panel))
    layer_expr = '['+','.join('['+','.join('['+','.join(row)+']' for row in legs)+']' for legs in route_layers)+']'
    routes_json=json.dumps(journey_data,ensure_ascii=False)
    od_json=json.dumps(' ← '.join(waypoints),ensure_ascii=False)
    metric_json=json.dumps('الأسرع' if metric=='duration_min' else 'الأقصر',ensure_ascii=False)
    script = r'''
      window.addEventListener('load',function(){
        const routeLayers=__LAYERS__;
        const routes=__ROUTES__;
        const objective=__OBJECTIVE__;
        document.getElementById('sro-od').textContent=__OD__;
        let active=0, currentLeg=0;
        function fmtTime(minutes){let n=Math.round(minutes);return `${Math.floor(n/60)} س ${n%60} د`;}
        function pick(n){active=n;currentLeg=0;render();}
        function render(){
          routeLayers.forEach((legs,ri)=>legs.forEach((paths,li)=>paths.forEach(poly=>{
            const on=(ri===active);const isNow=(li===currentLeg);
            const isDone=(li<currentLeg);
            poly.setStyle({color: !on?'#8697a4':isDone?'#526575':isNow?'#29deb8':'#79a7a3',
              opacity:!on ? 0.22 : isDone ? 0.58 : isNow ? 1 : 0.38,
              weight:!on?3:isNow?8:5,dashArray:!on?'6 8':null});
          })));
          // Drawing the focused route last makes clicking the choice feel natural.
          routeLayers[active].forEach(leg=>leg.forEach(poly=>poly.bringToFront()));
          document.getElementById('sro-routes').innerHTML=routes.map((r,i)=>
            `<button type="button" class="sro-route ${i===active?'active':''}" data-route="${i}">
               <span class="rt-index">${i+1}</span>
               <span class="rt-main">المسار ${i+1} ${i===0?'· '+objective:''}
                 <span class="rt-sub">${r.km.toLocaleString()} كم · ${fmtTime(r.minutes)}</span></span>
               ${i===active?'✓':''}</button>`).join('');
          document.querySelectorAll('.sro-route').forEach(el=>el.onclick=()=>pick(Number(el.dataset.route)));
          const trip=routes[active];
          document.getElementById('sro-choice').textContent=`المسار المحدد ${active+1} · ${objective} (حسب ترتيب البحث)`;
          document.getElementById('sro-totals').innerHTML=`<span>${trip.km.toLocaleString()} كم</span><span>${fmtTime(trip.minutes)}</span>`;
          document.getElementById('sro-stages').innerHTML=trip.legs.map((leg,i)=>
             `<div class="sro-stage ${i===currentLeg?'on':i<currentLeg?'done':''}">
               ${i+1}. ${leg.start} ← ${leg.end} <small>${leg.km.toLocaleString()} كم · ${fmtTime(leg.minutes)}
               ${i===currentLeg?' · المرحلة الحالية':i<currentLeg?' · مكتملة':' · قادمة'}</small></div>`).join('');
          let btn=document.getElementById('sro-next');
          btn.disabled=currentLeg>=trip.legs.length;
          btn.textContent=btn.disabled?'اكتملت جميع المراحل':'وصلت إلى المحطة التالية';
        }
        routeLayers.forEach((legs,ri)=>legs.forEach(paths=>paths.forEach(poly=>poly.on('click',()=>pick(ri)))));
        document.getElementById('sro-next').onclick=()=>{if(currentLeg<routes[active].legs.length){currentLeg++;render();}};
        render();
      });
    '''.replace('__LAYERS__',layer_expr).replace('__ROUTES__',routes_json).replace('__OD__',od_json).replace('__OBJECTIVE__',metric_json)
    fmap.get_root().script.add_child(Element(script))
    return fmap.get_root().render()
