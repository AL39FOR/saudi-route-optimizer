"""Manual-review UI for route geometry from existing OSRM snapshots.
Run: streamlit run route_review.py
"""
from __future__ import annotations
import streamlit as st
from pathlib import Path
from priority_audit import analysis,audit_map,PRIORITY
from audit_network import analyze
st.set_page_config(page_title='مراجعة جودة الطرق | Saudi Route Optimizer',page_icon='🔍',layout='wide')
st.title('🔍 مراجعة الطرق — V11')
st.caption('شاشة بحثية للمقارنة بين اتجاهات القيادة في الملفات المحفوظة. لا تعدّل المسافات، ولا تعتمد الطرق تلقائيًا.')
name={"L044":"النماص ↔ أبها","L061":"حريملاء ↔ ضرما","L068":"الخرج ↔ وادي الدواسر (تجريبي)"}
selected=st.selectbox('الطريق المراد مراجعته',PRIORITY,format_func=lambda v:f'{name[v]} · {v}')
a=analysis(selected)
x,y,z=st.columns(3)
x.metric('الذهاب',f'{a["forward_km"]:,.1f} كم',f'{a["forward_min"]:.0f} دقيقة',delta_color='off')
y.metric('العودة',f'{a["reverse_km"]:,.1f} كم',f'{a["reverse_min"]:.0f} دقيقة',delta_color='off')
z.metric('فرق المسافة',f'{a["direction_diff_km"]:,.1f} كم')
st.components.v1.html(audit_map(a),height=670,scrolling=False)
st.subheader('مؤشرات هندسية للفحص')
u,v,w=st.columns(3)
u.metric('أقصى تباعد بين خطّي المسار',f'{a["max_geometry_separation_km"]:.1f} كم')
v.metric('تشابه تقريبي ضمن 2 كم',f'{a["within_2km_pct"]:.0f}%')
w.metric('مقارنة القيادة بالمسافة الجوية',f'{a["forward_air_ratio"]:.2f}×')
if selected=='L044':
    st.info('مسارا الذهاب والعودة يختلفان بشكل واضح؛ هذا وحده لا يثبت وجود خطأ في بيانات الطرق. نحتاج التأكد من اتجاهات المرور والطريق المستعمل لكل جهة.')
elif selected=='L061':
    st.info('المساران في الاتجاهين متقاربان جدًا لكنهما يسلكان التفافًا طويلًا. لا نحذف الوصلة ولا نختصر مسافتها دون دليل على طريق أقصر صالح للقيادة.')
else:
    st.info('الوصلة الجديدة تعمل حسابيًا لكنها تجريبية حتى تدقيق طريقها الفعلي على مصدر مستقل.')
st.warning('جميع مسافات الملف تعود إلى طرق اختارها OSRM بالاعتماد على الزمن لكل وصلة؛ لا تعني أقصر طريق بري مطلق. الخطوط المعروضة مبسطة، ويجب مراجعتها جغرافيًا.')
with st.expander('كل الوصلات التي ظهرت عليها تنبيهات آلية'):
    results=analyze()
    alerts=[r for r in results if r[9] not in ('OK_SCREEN','NOT_MEASURED')]
    st.dataframe([{'ID':r[0],'من':r[1],'إلى':r[2],'ذهاب كم':r[3],'عودة كم':r[4],'سبب المراجعة':r[9]} for r in alerts],hide_index=True,use_container_width=True)
    st.caption('تنبيه PASS_NEAR_CITY لا يعني أن السيارة توقفت في تلك المدينة، بل فقط مرور هندسة الطريق قرب نقطة المدينة المسجلة.')
