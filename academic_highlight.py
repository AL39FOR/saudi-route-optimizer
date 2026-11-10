"""Presentation-only academic table helpers for Saudi Route Optimizer V12.1.

No solver weights, x values or constraints are modified.
"""
from __future__ import annotations
import pandas as pd


def variable_display_rows(raw_rows, solution):
    """Keep every original decision variable, but list chosen arcs in route order."""
    order={arc:index for index,arc in enumerate(solution.selected_arcs)}
    rows=[]
    for i, raw in enumerate(raw_rows):
        r=dict(raw)
        arc=(r['من'],r['إلى'])
        r['الحالة']='✓ ضمن المسار' if r['x']==1 else '—'
        rows.append((0 if r['x']==1 else 1,order.get(arc,i),i,r))
    rows.sort(key=lambda item:item[:3])
    return [r for _,_,_,r in rows]


def balance_display_rows(raw_rows, solution):
    """Show cities in the ordered path first, while retaining every flow constraint."""
    position={name:i for i,name in enumerate(solution.path)}
    rows=[]
    for i,raw in enumerate(raw_rows):
        r=dict(raw)
        city=r['العقدة']
        on_path=city in position
        r['على المسار']=on_path
        if city==solution.origin:
            role='البداية'
        elif city==solution.destination:
            role='النهاية'
        elif on_path:
            role='مدينة عبور'
        else:
            role='خارج المسار'
        r['الدور']=role
        rows.append((0 if on_path else 1,position.get(city,i),i,r))
    rows.sort(key=lambda item:item[:3])
    return [r for _,_,_,r in rows]


def highlighted_dataframe(rows,flag_column,flag_value):
    """Use pandas Styler supported by Streamlit to color entire selected rows."""
    df=pd.DataFrame(rows)
    if df.empty: return df
    def style_row(row):
        if row[flag_column]==flag_value:
            css='background-color: #d6f5e9; color: #064936; font-weight: 600'
        else:
            css=''
        return [css]*len(row)
    return df.style.apply(style_row,axis=1)
