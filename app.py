"""Saudi Route Optimizer V13 — run from project directory:
    streamlit run app.py

Local, single-user educational prototype. Does NOT provide live driving or traffic.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import streamlit as st
from core import all_selected_cities, make_graph, k_trips_sensible, graph_for_leg, fmt_time
from route_map import trip_map_html
from optimization_model import solve_shortest_path_model, decision_variable_table, flow_balance_table
from academic_highlight import variable_display_rows, balance_display_rows, highlighted_dataframe

ROOT=Path(__file__).resolve().parent
FULL=ROOT/'road_distances_osrm.csv'
CANDIDATES=ROOT/'road_links_audited_v2.csv'
COORDS=ROOT/'cities_coords.csv'
RECENT=ROOT/'last_search_local.json'

st.set_page_config(page_title='Saudi Route Optimizer V13',page_icon='🧭',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
:root{--accent:#19bfa4}
.block-container {padding-top:1.3rem;max-width:1400px}
.sro-hero{background:linear-gradient(112deg,#102a3f,#136f71);padding:22px 24px;border-radius:17px;color:#fff;margin-bottom:16px}
.sro-hero h1{margin:0;color:#fff;font-size:27px}
.sro-hero p{margin:6px 0 0;color:#d9eeed;font-size:13px}
.sro-bubble{border-radius:15px;background:rgba(24,145,128,.08);border:1px solid #2c83794d;padding:14px 18px}
.sro-caption{font-size:12px;color:#8395a6}
div[data-testid="stMetric"]{background:rgba(106,132,150,.07);padding:10px 14px;border-radius:12px}
.stButton>button[kind="primary"]{background:#168b83;border-color:#168b83}
</style>''',unsafe_allow_html=True)
st.markdown('<div class="sro-hero"><h1>Saudi Route Optimizer</h1><p>تحسين المسارات السعودية • بحوث العمليات • رحلات متعددة المحطات</p></div>',unsafe_allow_html=True)

if not CANDIDATES.exists() or not FULL.exists():
    st.error('ملف المسافات أو الوصلات مفقود. استعمل نسخة الحزمة الكاملة.'); st.stop()
registered_cities=all_selected_cities(CANDIDATES)
measured_graph=make_graph(FULL)
cities=[c for c in registered_cities if c in measured_graph.nodes]
pending_cities=[c for c in registered_cities if c not in measured_graph.nodes]
if not cities: st.error('لا توجد مدن في جدول الوصلات.'); st.stop()
coords={}
with COORDS.open(encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        if r.get('lat') and r.get('lon'): coords[r['city_ar']]=(float(r['lat']),float(r['lon']))

def recent_read():
    try:
        obj=json.loads(RECENT.read_text(encoding='utf-8'))
        if isinstance(obj,dict) and obj.get('itinerary') and all(c in cities for c in obj['itinerary']):
            return obj
    except (OSError,ValueError,TypeError):pass
    return None

def recent_save(stops,metric):
    # Only city names & preferred metric are stored on the user's computer.
    RECENT.write_text(json.dumps({'itinerary':stops,'metric':metric},ensure_ascii=False,indent=2),encoding='utf-8')

st.session_state.setdefault('sro_origin','الرياض')
st.session_state.setdefault('sro_end','أبها')
st.session_state.setdefault('sro_stops',0)
st.session_state.setdefault('sro_metric','duration_min')
st.session_state.setdefault('sro_strict_order',True)

with st.sidebar:
    st.header('🔎 بحث عن رحلة')
    if pending_cities:
        with st.expander('مدن أضيفت وتنتظر قياس الطرق'):
            st.write('، '.join(pending_cities))
            st.caption('تظهر في اختيارات الرحلة بمجرد استخراج روابط الطرق المناسبة لها. لم نغيّر بيانات المدن القديمة.')
    last=recent_read()
    if last:
        with st.popover('🕓 آخر عملية بحث',use_container_width=True):
            st.markdown(' **'+' ← '.join(last['itinerary'])+'**')
            st.caption('اضغط لإعادة استخدام الرحلة السابقة')
            if st.button('استخدام آخر بحث',use_container_width=True):
                seq=last['itinerary'];st.session_state['sro_origin']=seq[0]
                st.session_state['sro_end']=seq[-1]
                st.session_state['sro_stops']=len(seq)-2
                st.session_state['sro_metric']=last.get('metric','duration_min')
                for i,item in enumerate(seq[1:-1]): st.session_state[f'sro_stop_{i}']=item
                st.rerun()
    st.selectbox('مدينة الانطلاق',cities,key='sro_origin')
    st.number_input('عدد الوجهات الوسيطة',min_value=0,max_value=5,step=1,key='sro_stops')
    mids=[]
    for i in range(int(st.session_state['sro_stops'])):
        key=f'sro_stop_{i}'
        if key not in st.session_state:st.session_state[key]='الطائف' if i else 'أبها'
        mids.append(st.selectbox(f'المحطة {i+1}',cities,key=key))
    st.selectbox('مدينة الوصول',cities,key='sro_end')
    st.radio('معيار ترتيب المسارات',('duration_min','distance_km'),
             format_func=lambda v:'الأسرع (المدة)' if v=='duration_min' else 'الأقصر (الكيلومترات)',
             key='sro_metric',horizontal=True)
    if st.session_state['sro_stops']:
        st.checkbox('احترام ترتيب المحطات (على مستوى عقد المدن)',
                    key='sro_strict_order',
                    help='يمنع عبور عقدة مدينة مطلوبة لاحقًا قبل مرحلتها. لا يكشف تلقائيًا المرور داخل المدينة عبر طريق طويل من دون عقدة وسيطة.')
    st.divider()
    with st.expander('⚙️ خيارات فنية لمراجعة البيانات'):
        include_review_links=st.toggle('تضمين 4 وصلات تحتاج مراجعة (تجريبي)',value=False,
            help='هذه الطرق ليست مغلقة؛ استبعدناها من التحليل الافتراضي حتى ننتهي من تدقيق مساراتها.')
        st.caption('الوصلات L034 وL044 وL052 وL055 غير محذوفة. تظهر فقط عند تفعيل هذا الخيار، ولا يعني استبعادها أنها طرق مغلقة.')
        if include_review_links:
            st.warning('وضع بحثي: أدرجت الوصلات الأربع غير المعتمدة.')
        candidate_available = any(
            data.get('link_id') == 'L068' for _, _, data in measured_graph.edges(data=True)
        )
        include_candidate = st.toggle('تجربة وصلة الخرج–وادي الدواسر (غير معتمدة)', value=False,
            disabled=not candidate_available,
            help='وصلة L068 تجريبية. لا تدخل الحل حتى يتوفر قياسها وتُفعّلها هنا بنفسك.')
        if not candidate_available:
            st.caption('الوصلة L068 لم تُقَس بعد: لن تظهر في نتائج البحث.')
        elif include_candidate:
            st.warning('الوصلة L068 قيد المراجعة، النتائج استكشافية وليست معتمدة.')
    st.caption('قاعدة البدائل: لا نعرض مسارًا يبتعد أكثر من 200 كم عن المسار الأول، حتى عند ترتيب النتائج حسب الوقت.')
    st.caption('ترتيب المحطات الصارم يطبّق على عقد الشبكة؛ قد يتطلب التأكد من هندسة الطريق التفصيلية لاحقًا.')
    do_search=st.button('ابحث عن أفضل المسارات',type='primary',use_container_width=True)
    st.caption('يمكنك الضغط على أي مسار في الخريطة أو في لوحة النتائج. سجل البحث محفوظ محليًا على هذا الماك فقط.')

metric=st.session_state['sro_metric']
itinerary=[st.session_state['sro_origin'],*mids,st.session_state['sro_end']]
if any(a==b for a,b in zip(itinerary,itinerary[1:])):
    st.warning('لا يصح اختيار نفس المدينة لمرحلتين متتاليتين.')
    do_search=False

excluded=(set() if include_review_links else {'L034','L044','L052','L055'})
if not include_candidate: excluded.add('L068')
g=make_graph(FULL,excluded_link_ids=excluded)
if g.number_of_edges()==0:
    st.error('الملف لا يحتوي على أوزان طرق صالحة.');st.stop()

# Each widget update recalculates the selected itinerary using the new objective, so nothing becomes stale.
if do_search:
    try:recent_save(itinerary,metric)
    except OSError:st.info('لا يمكن حفظ آخر بحث في هذا المجلد، لكن يمكنك إكمال الجلسة.')

strict_order=bool(st.session_state['sro_strict_order']) and len(itinerary)>2
search_key=(tuple(itinerary),metric,include_review_links,include_candidate,strict_order)
if do_search or 'sro_result' not in st.session_state or st.session_state.get('sro_search_key')!=search_key:
    try:
        trips=k_trips_sensible(g,itinerary,k=3,metric=metric,max_gap_km=200,
                              candidates_to_check=30,enforce_stop_order=strict_order)
    except ValueError as e:
        trips=[];st.warning(str(e))
    st.session_state['sro_result']=trips
    st.session_state['sro_search_key']=search_key
else:
    trips=st.session_state['sro_result']

st.markdown(f'**الرحلة:**  {" ← ".join(itinerary)}')
st.caption(f'الشبكة المستخدمة: {g.number_of_nodes()} نقطة · {g.number_of_edges()} قوس موجه · معيار الاختيار: {"المدة التقديرية" if metric=="duration_min" else "المسافة"}')
st.warning('⚠️ هذه نسخة تجريبية: طرق OSRM غير معتمدة جغرافيًا نهائيًا، ولا توجد بيانات ازدحام أو إغلاقات حية. الزمن تقديري، و"الأقصر" يعني الأقل مجموعًا داخل شبكة هذا المشروع فقط.')

if not trips:
    st.error('لم نجد مسارًا صالحًا وفق اختياراتك في شبكة المشروع الحالية.')
    if strict_order:
        st.info('ترتيب المحطات صارم حاليًا: قد لا تتوفر وصلة مناسبة دون المرور بمحطة لاحقة مبكرًا. '
                'إذا كانت الرحلة الخبر ← أبها ← الرياض، فإن وصلة الخرج–وادي الدواسر التجريبية L068 '
                'توفر خيارًا لا يمر بالرياض في المرحلة الأولى، ولكنها غير معتمدة جغرافيًا بعد.')
else:
    if len(trips)<3:
        st.info(f'تم عرض {len(trips)} من المسارات المناسبة فقط؛ استُبعدت البدائل التي يزيد فرق مسافتها عن 200 كم مقارنة بالمسار الأول.')
    columns=st.columns(len(trips))
    for idx, (col,t) in enumerate(zip(columns,trips)):
        with col:
            st.markdown(f'**{"⭐ " if idx==0 else ""}الخيار {idx+1}**')
            st.metric('المسافة',f'{t.km:,.1f} كم')
            st.caption(f'المدة المتوقعة: {fmt_time(t.minutes)}')
    # Safety check remains even in strict mode, including manually restored legacy mode.
    premature = []
    for leg_index, leg in enumerate(trips[0].legs):
        later_stops = set(itinerary[leg_index+2:])
        overlap = later_stops.intersection(leg.cities[1:-1])
        if overlap:
            premature.append(f'{leg.start} ← {leg.end}: ' + '، '.join(sorted(overlap)))
    if premature:
        st.warning('تنبيه ترتيب المحطات: قد يمر المسار بمحطة مقررة لاحقًا قبل موعدها: '
                   + ' | '.join(premature)
                   + '؛ يجب تحسين وصلات الشبكة أو تغيير مسار الرحلة قبل اعتماد الترتيب.')
    html=trip_map_html(trips,g,itinerary,coords,metric)
    st.components.v1.html(html,height=735,scrolling=False)
    with st.expander('تفاصيل المسارات بالمدن، والمسافة والمدة لكل مرحلة'):
        for idx,t in enumerate(trips,1):
            st.markdown(f'#### الخيار {idx}: {t.km:,.1f} كم · {fmt_time(t.minutes)}')
            for leg in t.legs:
                st.write(f'{leg.start} ← {leg.end}: {leg.km:,.1f} كم · {fmt_time(leg.minutes)}')
                st.caption('نقاط المسار: '+' ← '.join(leg.cities))

# The academic model lives INSIDE the main app. route_review.py remains a
# separate optional technical screen; it does not replace this interface.
with st.expander('📐 النموذج الرياضي — متغيرات القرار والقيود والتحقق من الحل',expanded=False):
    st.markdown('**Shortest Path as a Minimum-Cost Flow Model** — كل طريق موجه يمثل متغير قرار مستقلًا.')
    st.latex(r'\min Z=\sum_{(i,j)\in A}c_{ij}x_{ij}')
    st.latex(r'\sum_{j:(i,j)\in A}x_{ij}-\sum_{j:(j,i)\in A}x_{ji}=\begin{cases}1&i=s\\-1&i=t\\0&\text{otherwise}\end{cases}')
    st.latex(r'x_{ij}\in\{0,1\}\qquad\forall(i,j)\in A')
    st.caption('cᵢⱼ = كيلومترات عند اختيار الأقصر، أو دقائق قيادة تقديرية عند اختيار الأسرع. '
               'يستخدم حل التدفق الأقل تكلفة (Network Simplex) مع سعة 1 لكل طريق. '
               'النتائج أمثل داخل الشبكة المقاسة فقط، وليست شبكة جميع طرق المملكة.')
    st.info(f'الشبكة العامة: {g.number_of_edges()} متغير قرار (قوس موجه)، '
            f'{g.number_of_nodes()} قيد توازن تدفق. عند فرض ترتيب المحطات قد تُستبعد '
            'عقد مستقبلية من النموذج الخاص بالمرحلة. شرط الدكتور (أكثر من 20 متغيرًا) متحقق.')
    if not trips:
        st.warning('اختر رحلة لها حل في الشبكة لعرض متغيراتها والقيود المحققة.')
    else:
        stage_options=list(range(len(itinerary)-1))
        if st.session_state.get('academic_model_stage') not in stage_options:
            st.session_state['academic_model_stage']=0
        stage=st.selectbox('المرحلة التي تريد عرض نموذجها الرياضي',stage_options,
                           format_func=lambda i:f'{i+1}. {itinerary[i]} ← {itinerary[i+1]}',
                           key='academic_model_stage')
        start,end=itinerary[stage],itinerary[stage+1]
        stage_graph=graph_for_leg(g,itinerary,stage,enforce_stop_order=strict_order)
        try:
            solution=solve_shortest_path_model(stage_graph,start,end,metric=metric)
            if strict_order:
                st.caption(f'هذه المرحلة تضم {stage_graph.number_of_edges()} متغيرًا و'
                           f'{stage_graph.number_of_nodes()} قيدًا، بعد استبعاد المحطات اللاحقة من البحث.')
            left,right,third=st.columns(3)
            unit='دقيقة' if metric=='duration_min' else 'كم'
            left.metric('قيمة دالة الهدف',f'{solution.objective_value:,.2f} {unit}')
            right.metric('المتغيرات المختارة (x = 1)',len(solution.selected_arcs))
            third.metric('أكبر خطأ في توازن التدفق',solution.largest_balance_error)
            st.write('**المسار الرياضي الأمثل:** '+' ← '.join(solution.path))
            st.caption(f'المسافة: {solution.distance_km:,.2f} كم • الزمن التقديري: {fmt_time(solution.duration_min)}')
            expected=trips[0].legs[stage]
            app_objective=expected.km if metric=='distance_km' else expected.minutes
            gap=abs(solution.objective_value-app_objective)
            if gap < 0.011:
                st.success('التحقق: قيمة نموذج التدفق تطابق قيمة المسار الأول المحسوبة في التطبيق (ضمن دقة التقريب).')
            else:
                st.warning(f'يوجد اختلاف {gap:.3f} بين النموذج وأول نتيجة معروضة؛ '
                           'يلزم مراجعته قبل اعتماد الحل.')
            # Presentation-only enhancements: preserve all source x values, constraints and route logic.
            variables=variable_display_rows(decision_variable_table(stage_graph,solution),solution)
            balances=balance_display_rows(flow_balance_table(stage_graph,solution),solution)
            selected_rows=[r for r in variables if r['x']==1]
            st.markdown('**🟢 الأقواس المختارة في الحل (x = 1)، مرتبة حسب الرحلة:**')
            st.dataframe(highlighted_dataframe(selected_rows,'x',1),
                         hide_index=True,use_container_width=True)
            with st.expander('اعرض جدول جميع متغيرات القرار (x = 0 أو 1)'):
                st.caption('🟢 الصف الأخضر = طريق مختار (x = 1). تظهر الطرق المختارة أولًا حسب ترتيب الرحلة، ثم بقية الطرق (x = 0).')
                only_chosen=st.checkbox('اعرض الطرق المختارة فقط (x = 1)',key='academic_only_chosen_arcs')
                visible_variables=selected_rows if only_chosen else variables
                st.dataframe(highlighted_dataframe(visible_variables,'x',1),
                             hide_index=True,use_container_width=True)
                st.caption(f'{len(selected_rows)} طرق مختارة من أصل {len(variables)} متغير قرار. التلوين للعرض فقط ولا يغيّر الحل.')
            with st.expander('اعرض تحقق قيد التدفق لكل عقدة'):
                st.caption('🟢 المدن الخضراء هي البداية والوسط والنهاية في المسار. البقية رمادية ولا يمر بها الحل. جميع قيود التدفق تبقى محسوبة.')
                only_path=st.checkbox('اعرض المدن التي يمر بها المسار فقط',key='academic_only_path_nodes')
                visible_balances=[r for r in balances if r['على المسار']] if only_path else balances
                st.dataframe(highlighted_dataframe(visible_balances,'على المسار',True),
                             hide_index=True,use_container_width=True)
                st.caption('عند نقطة الانطلاق: الخارج − الداخل = 1. '
                           'عند الوصول = −1. في جميع المدن الأخرى = 0.')
        except (ValueError,RuntimeError) as exc:
            st.error(f'تعذر استخراج النموذج الرياضي لهذه المرحلة: {exc}')
    if len(itinerary)>2:
        if strict_order:
            st.caption('للرحلة متعددة المحطات نحل كل مرحلة بالتسلسل، ونمنع المرور '
                       'بالمحطات المطلوبة لاحقًا قبل موعدها. قد تتكرر مدن سبق زيارتها '
                       'إذا لزم ذلك بسبب شبكة الطرق.')
        else:
            st.warning('الوضع المرن لا يمنع المرور بمحطة مطلوبة لاحقًا قبل وقتها. '
                       'فعّل احترام ترتيب المحطات إذا كنت تحتاج هذا الشرط.')
    st.caption('هذه الصياغة خاصة بمسألة أقصر مسار: لا تمثل ازدحامًا حيًا أو طرقًا مغلقة حاليًا. '
               'قيم الأوزان من ملف OSRM المقاس والمعلّم بأنه غير معتمد جغرافيًا بعد.')
