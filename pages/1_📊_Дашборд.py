import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.sheets import load_expenses, load_revenue, load_salaries, load_budget
from utils.mappings import (
    STUDIO_CODES, ENTITY_NAMES, ENTITY_STUDIOS,
    ALL_EXPENSE_CATEGORIES, REVENUE_CATEGORIES,
    MONTHS_RU, ENTITY_COLORS, ACQUIRING_RATE,
)
from utils.ui import sidebar_period

st.set_page_config(page_title='Дашборд', page_icon='📊', layout='wide')
from utils.auth import check_password, show_logout_button

if not check_password():
    st.stop()
show_logout_button()


# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.kpi-card {
    border-radius: 14px; padding: 20px 16px; text-align: center;
    box-shadow: 0 3px 12px rgba(0,0,0,.09); margin-bottom: 4px;
    min-height: 110px;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
}
.kpi-label { font-size: 11px; font-weight: 700; letter-spacing: .7px;
             text-transform: uppercase; margin: 0 0 8px; opacity: .82; }
.kpi-value { font-size: 28px; font-weight: 800; margin: 0 0 4px; line-height: 1.1; }
.kpi-pct   { font-size: 13px; margin: 0; opacity: .85; font-weight: 600; }

.pnl-wrap  { background: #FAFAFA; border-radius: 14px; padding: 20px 24px;
             box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.pnl-table { width:100%; border-collapse:collapse; font-size:14px; }
.pnl-table td { padding: 5px 8px; vertical-align:middle; }
.pnl-table td:last-child { text-align:right; font-weight:600; min-width:110px; }
.pnl-table td:nth-child(2) { text-align:right; color:#6B7280; font-size:13px; min-width:48px; }
.pnl-sub  td { color:#9CA3AF; font-size:13px; }
.pnl-sub  td:first-child { padding-left:28px; }
.pnl-div  td { border-top: 1.5px solid #E5E7EB; padding-top: 8px; margin-top: 4px; }
.pnl-bold td { font-weight:700; font-size:15px; }
.pnl-result td { font-weight:800; font-size:16px; background:#ECFDF5;
                 border-radius:8px; padding:8px 10px; }
</style>
""", unsafe_allow_html=True)


# ── Хелперы ────────────────────────────────────────────────────────────────────
def fmt(val):
    if abs(val) >= 1_000_000:
        return f'{val/1_000_000:.1f} млн ₽'
    return f'{val:,.0f} ₽'.replace(',', ' ')

def fmt_short(val):
    if abs(val) >= 1_000_000:
        return f'{val/1_000_000:.1f} млн'
    return f'{val:,.0f}'.replace(',', ' ')

def pct_str(val, total):
    if not total:
        return '—'
    return f'{val / total * 100:.1f}%'

def kpi_card(label, value, sub=None, bg='#1E3A5F', fg='#FFFFFF'):
    s_html = f'<p class="kpi-pct" style="color:{fg};">{sub}</p>' if sub else ''
    return (f'<div class="kpi-card" style="background:{bg};">'
            f'<p class="kpi-label" style="color:{fg};">{label}</p>'
            f'<p class="kpi-value" style="color:{fg};">{value}</p>'
            f'{s_html}</div>')


# ── Загрузка данных ────────────────────────────────────────────────────────────
exp_df    = load_expenses()
rev_df    = load_revenue()
sal_df    = load_salaries()
budget_df = load_budget()

# Ремаппинг категорий для данных января–мая 2026
_CAT_MAP_JAN_MAY_2026 = {
     9: 41,  10: 40,  11:  9,  12: 10,  13: 11,  14: 12,
    15: 13,  16: 14,  17: 15,  18: 16,  19: 17,  20: 18,
    21: 19,  22: 20,  23: 21,  24: 22,  25: 23,  26: 24,
    27: 25,  28: 26,  29: 27,  30: 28,  31: 29,  32: 30,
    33: 31,  34: 32,  35: 33,  36: 34,  37: 35,  38: 36,
    39: 37,  40: 38,  41: 39,
}
if not exp_df.empty:
    _old = (exp_df['year'] == 2026) & (exp_df['month'] <= 5)
    _rm  = _old & exp_df['category_code'].isin(_CAT_MAP_JAN_MAY_2026)
    exp_df.loc[_rm, 'category_code'] = exp_df.loc[_rm, 'category_code'].map(_CAT_MAP_JAN_MAY_2026)

if exp_df.empty and rev_df.empty:
    st.info('Данных пока нет. Загрузи реестры и введи доходы.')
    st.stop()


# ── Сайдбар ────────────────────────────────────────────────────────────────────
year, month = sidebar_period()

with st.sidebar:
    st.header('Фильтры')
    view_mode = st.radio('Период', ['Месяц', 'С начала года (YTD)'])
    if view_mode == 'Месяц':
        months_range = [month]
    else:
        max_month = st.slider('По месяц включительно', 1, 12, value=month,
                              format=lambda x: MONTHS_RU[x])
        months_range = list(range(1, max_month + 1))

    studio_filter = st.selectbox(
        'Студия', ['Все'] + list(STUDIO_CODES.keys()),
        format_func=lambda x: 'Все студии' if x == 'Все' else STUDIO_CODES[x],
    )
    entity_filter = st.selectbox(
        'Юрлицо', ['Все'] + list(ENTITY_NAMES.keys()),
        format_func=lambda x: 'Все' if x == 'Все' else f'{x} — {ENTITY_NAMES[x]}',
    )

    pass  # sidebar end


# ── Фильтрация ─────────────────────────────────────────────────────────────────
def filter_df(df):
    if df is None or df.empty:
        return pd.DataFrame()
    mask = (df['year'] == year) & (df['month'].isin(months_range))
    if studio_filter != 'Все':
        mask &= df['studio'] == studio_filter
    if entity_filter != 'Все':
        mask &= df['entity'] == entity_filter
    return df[mask].copy()

exp_f = filter_df(exp_df)
rev_f = filter_df(rev_df)
sal_f = filter_df(sal_df)

# ── Уровни P&L ─────────────────────────────────────────────────────────────────
FULLY_EXCLUDED  = {0, 24, 25, 27}
BELOW_LINE_CATS = {19, 43, 44, 45}

if not exp_f.empty:
    exp_f_oper  = exp_f[~exp_f['category_code'].isin(FULLY_EXCLUDED | BELOW_LINE_CATS)]
    exp_f_below = exp_f[exp_f['category_code'].isin(BELOW_LINE_CATS)]
    exp_f_show  = exp_f[~exp_f['category_code'].isin(FULLY_EXCLUDED)]
else:
    exp_f_oper = exp_f_below = exp_f_show = pd.DataFrame()

# ── Эквайринг ─────────────────────────────────────────────────────────────────
if not rev_f.empty:
    acq_by_studio = rev_f.groupby('studio')['amount'].sum().mul(ACQUIRING_RATE).round(2)
    total_acquiring = acq_by_studio.sum()
else:
    acq_by_studio  = pd.Series(dtype=float)
    total_acquiring = 0.0

# ── Расчёт P&L ─────────────────────────────────────────────────────────────────
# Переменные расходы: эквайринг + прямые расходы пропорциональные выручке/посещениям
VARIABLE_CATS = {8, 9, 10, 14, 15}  # товары, гигиена, расходные, химчистка, продукты бара

total_revenue  = rev_f['amount'].sum()  if not rev_f.empty  else 0.0
total_sal      = sal_f['amount'].sum()  if not sal_f.empty  else 0.0

if not exp_f_oper.empty:
    var_exp_raw  = exp_f_oper[exp_f_oper['category_code'].isin(VARIABLE_CATS)]['amount'].sum()
    fix_exp_raw  = exp_f_oper[~exp_f_oper['category_code'].isin(VARIABLE_CATS)]['amount'].sum()
else:
    var_exp_raw = fix_exp_raw = 0.0

total_variable  = var_exp_raw + total_acquiring   # переменные: прямые + эквайринг
total_fixed     = fix_exp_raw + total_sal          # постоянные: оверхед + ФОТ
total_oper_exp  = total_variable + total_fixed     # итого операционные
total_oper_exp_raw = fix_exp_raw + var_exp_raw     # без эквайринга (для совместимости)

gross_profit = total_revenue - total_variable
gross_margin = gross_profit / total_revenue * 100 if total_revenue else 0.0
oper_profit  = gross_profit - total_fixed
oper_margin  = oper_profit / total_revenue * 100 if total_revenue else 0.0
below_total  = exp_f_below['amount'].sum() if not exp_f_below.empty else 0.0
net_profit   = oper_profit - below_total
net_margin   = net_profit / total_revenue * 100 if total_revenue else 0.0

period_label = (MONTHS_RU[months_range[0]] if len(months_range) == 1
                else f'Январь – {MONTHS_RU[months_range[-1]]}')

# ══════════════════════════════════════════════════════════════════════════════
# РАЗДЕЛ 1: KPI-карточки
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f'### {period_label} {year}')

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(kpi_card(
        '💚 ВЫРУЧКА', fmt(total_revenue),
        bg='#065F46', fg='#ECFDF5',
    ), unsafe_allow_html=True)

with c2:
    bg2 = '#EFF6FF' if gross_profit >= 0 else '#FEF2F2'
    fg2 = '#1E40AF' if gross_profit >= 0 else '#991B1B'
    st.markdown(kpi_card(
        '📊 ВАЛОВАЯ ПРИБЫЛЬ', fmt(gross_profit),
        sub=f'{gross_margin:.1f}%' if total_revenue else None,
        bg=bg2, fg=fg2,
    ), unsafe_allow_html=True)

with c3:
    bg3 = '#F0FDF4' if oper_profit >= 0 else '#FEF2F2'
    fg3 = '#166534' if oper_profit >= 0 else '#991B1B'
    st.markdown(kpi_card(
        '🏆 ОПЕРАЦ. ПРИБЫЛЬ', fmt(oper_profit),
        sub=f'{oper_margin:.1f}%' if total_revenue else None,
        bg=bg3, fg=fg3,
    ), unsafe_allow_html=True)

with c4:
    bg4 = '#ECFDF5' if net_profit >= 0 else '#FEF2F2'
    fg4 = '#065F46' if net_profit >= 0 else '#991B1B'
    st.markdown(kpi_card(
        '💰 ЧИСТАЯ ПРИБЫЛЬ', fmt(net_profit),
        sub=f'{net_margin:.1f}%' if total_revenue else None,
        bg=bg4, fg=fg4,
    ), unsafe_allow_html=True)

st.markdown('<br>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# РАЗДЕЛ 2: P&L таблица
# ══════════════════════════════════════════════════════════════════════════════
def tr(label, amount, total, cls='', color=''):
    p = pct_str(amount, total)
    neg = amount < 0
    val_fmt = ('(' + fmt(abs(amount)) + ')') if neg else fmt(amount)
    style = f'style="color:{color};"' if color else ''
    return (f'<tr class="{cls}"><td {style}>{label}</td>'
            f'<td>{p}</td><td {style}>{val_fmt}</td></tr>')

def sub_row(label, amount, total):
    p = pct_str(amount, total)
    return (f'<tr class="pnl-sub">'
            f'<td style="padding-left:28px;color:#9CA3AF;">{label}</td>'
            f'<td style="color:#9CA3AF;">{p}</td>'
            f'<td style="color:#9CA3AF;">({fmt(amount)})</td></tr>')

# Детализация налогов
tax_detail = ''
if not exp_f_below.empty:
    tmp = exp_f_below.copy()
    tmp['cat'] = tmp['category_code'].map(
        lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else '?'
    )
    for cat, grp in tmp.groupby('cat'):
        tax_detail += sub_row(cat, grp['amount'].sum(), total_revenue)

def color_val(v):
    return '#065F46' if v >= 0 else '#DC2626'

pnl_html = f"""
<div class="pnl-wrap">
<table class="pnl-table">
  <colgroup><col style="width:55%"><col style="width:15%"><col style="width:30%"></colgroup>

  {tr('💚 &nbsp;Выручка', total_revenue, total_revenue, 'pnl-bold', '#065F46')}

  {sub_row('Товары и расходники', var_exp_raw, total_revenue)}
  {sub_row(f'Эквайринг {int(ACQUIRING_RATE*100)}%', total_acquiring, total_revenue)}
  {tr('📦 &nbsp;Переменные расходы', -total_variable, total_revenue, 'pnl-div', '#DC2626')}

  {tr('📊 &nbsp;Валовая прибыль', gross_profit, total_revenue, 'pnl-bold pnl-div', color_val(gross_profit))}

  {sub_row('ФОТ', total_sal, total_revenue)}
  {sub_row('Аренда и оверхед', fix_exp_raw, total_revenue)}
  {tr('🏗 &nbsp;Постоянные расходы', -total_fixed, total_revenue, 'pnl-div', '#DC2626')}

  {tr('🏆 &nbsp;Операционная прибыль', oper_profit, total_revenue, 'pnl-bold pnl-div', color_val(oper_profit))}

  {tax_detail}
  {tr('💸 &nbsp;Налоги', -below_total, total_revenue, 'pnl-div', '#D97706') if below_total else ''}

  {tr('💰 &nbsp;Чистая прибыль', net_profit, total_revenue, 'pnl-result pnl-div', color_val(net_profit))}
</table>
</div>
"""

left_col, right_col = st.columns([3, 2])

with left_col:
    st.markdown('**P&L — отчёт о прибылях и убытках**')
    st.markdown(pnl_html, unsafe_allow_html=True)

with right_col:
    st.markdown('**Структура расходов**')
    all_exp_show_pie = pd.concat(
        [d for d in [exp_f_show, sal_f] if not d.empty], ignore_index=True
    ) if (not exp_f_show.empty or not sal_f.empty) else pd.DataFrame()

    if not all_exp_show_pie.empty or total_acquiring > 0:
        if not all_exp_show_pie.empty:
            all_exp_show_pie['cat'] = all_exp_show_pie['category_code'].map(
                lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else 'Прочее'
            )
            pie_data = all_exp_show_pie.groupby('cat')['amount'].sum().reset_index()
        else:
            pie_data = pd.DataFrame(columns=['cat', 'amount'])

        if total_acquiring > 0:
            pie_data = pd.concat([pie_data, pd.DataFrame([{
                'cat': f'Эквайринг {int(ACQUIRING_RATE*100)}%', 'amount': total_acquiring
            }])], ignore_index=True)

        pie_data = pie_data[pie_data['amount'] > 0].sort_values('amount', ascending=False)
        # Группируем мелкие статьи в "Прочее" если их больше 10
        if len(pie_data) > 10:
            top = pie_data.head(9).copy()
            other_sum = pie_data.iloc[9:]['amount'].sum()
            top = pd.concat([top, pd.DataFrame([{'cat': 'Прочее', 'amount': other_sum}])],
                            ignore_index=True)
            pie_data = top

        fig_pie = px.pie(
            pie_data, values='amount', names='cat',
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Set3,
        )
        fig_pie.update_traces(
            textposition='inside', textinfo='percent',
            hovertemplate='<b>%{label}</b><br>%{value:,.0f} ₽<br>%{percent}<extra></extra>',
        )
        fig_pie.update_layout(
            height=340, margin=dict(t=0, b=0, l=0, r=0),
            legend=dict(orientation='v', font=dict(size=11)),
            showlegend=True,
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info('Нет данных')

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# ВКЛАДКИ
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs(['📍 По студиям', '📋 По статьям', '📈 Динамика', '🗂 Сводная', '🎯 План/Факт'])

# ══ Вкладка 1: По студиям ══════════════════════════════════════════════════════
with tab1:
    all_exp_oper = pd.concat(
        [d for d in [exp_f_oper, sal_f] if not d.empty], ignore_index=True
    ) if (not exp_f_oper.empty or not sal_f.empty) else pd.DataFrame()

    if not rev_f.empty or not all_exp_oper.empty:
        rev_s = rev_f.groupby('studio')['amount'].sum() if not rev_f.empty else pd.Series(dtype=float)
        exp_s = (all_exp_oper[all_exp_oper['studio'].isin(STUDIO_CODES)]
                 .groupby('studio')['amount'].sum()
                 if not all_exp_oper.empty else pd.Series(dtype=float))
        exp_s = exp_s.add(acq_by_studio, fill_value=0)

        studios = sorted(set(rev_s.index) | set(exp_s.index),
                         key=lambda s: rev_s.get(s, 0), reverse=True)
        rows = []
        for s in studios:
            if s not in STUDIO_CODES:
                continue
            r = rev_s.get(s, 0)
            e = exp_s.get(s, 0)
            p = r - e
            rows.append({
                'Студия': STUDIO_CODES[s],
                'Выручка': r, 'Расходы': e, 'Прибыль': p,
                'Маржа': f'{p/r*100:.0f}%' if r > 0 else '—',
            })

        pnl_df = pd.DataFrame(rows)
        if not pnl_df.empty:
            # Grouped bar chart
            fig_studios = go.Figure()
            fig_studios.add_bar(
                name='Выручка', x=pnl_df['Студия'], y=pnl_df['Выручка'],
                marker_color='#10B981',
                text=[fmt_short(v) for v in pnl_df['Выручка']],
                textposition='outside', textfont_size=11,
            )
            fig_studios.add_bar(
                name='Расходы', x=pnl_df['Студия'], y=pnl_df['Расходы'],
                marker_color='#EF4444',
                text=[fmt_short(v) for v in pnl_df['Расходы']],
                textposition='outside', textfont_size=11,
            )
            fig_studios.add_bar(
                name='Прибыль', x=pnl_df['Студия'], y=pnl_df['Прибыль'],
                marker_color='#3B82F6',
                text=[fmt_short(v) for v in pnl_df['Прибыль']],
                textposition='outside', textfont_size=11,
            )
            fig_studios.update_layout(
                barmode='group', height=380,
                xaxis_tickangle=-30, yaxis_title='₽',
                legend=dict(orientation='h', yanchor='bottom', y=1.02),
                margin=dict(t=40, b=60),
            )
            st.plotly_chart(fig_studios, use_container_width=True)

            # Таблица P&L по студиям
            display_df = pnl_df.copy()
            for col in ['Выручка', 'Расходы', 'Прибыль']:
                display_df[col] = display_df[col].apply(fmt)
            st.dataframe(display_df, hide_index=True, use_container_width=True)
    else:
        st.info('Нет данных')


# ══ Вкладка 2: По статьям ══════════════════════════════════════════════════════
with tab2:
    all_exp_show = pd.concat(
        [d for d in [exp_f_show, sal_f] if not d.empty], ignore_index=True
    ) if (not exp_f_show.empty or not sal_f.empty) else pd.DataFrame()

    if not all_exp_show.empty or total_acquiring > 0:
        if not all_exp_show.empty:
            all_exp_show['cat'] = all_exp_show['category_code'].map(
                lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else 'Прочее'
            )
            cat_sum = all_exp_show.groupby('cat')['amount'].sum().reset_index()
        else:
            cat_sum = pd.DataFrame(columns=['cat', 'amount'])

        if total_acquiring > 0:
            cat_sum = pd.concat([cat_sum, pd.DataFrame([{
                'cat': f'Эквайринг (расч. {int(ACQUIRING_RATE*100)}%)',
                'amount': total_acquiring
            }])], ignore_index=True)

        cat_sum = cat_sum[cat_sum['amount'] > 0].sort_values('amount', ascending=True).tail(20)

        fig_cat = px.bar(
            cat_sum, x='amount', y='cat', orientation='h',
            text=[fmt_short(v) for v in cat_sum['amount']],
            color='amount', color_continuous_scale='Blues',
            labels={'amount': '', 'cat': ''},
        )
        fig_cat.update_traces(textposition='outside', textfont_size=11)
        fig_cat.update_layout(
            height=max(400, len(cat_sum) * 30),
            coloraxis_showscale=False,
            margin=dict(l=10, r=80, t=20, b=20),
            xaxis_title='',
        )
        st.plotly_chart(fig_cat, use_container_width=True)

        # ── Дрилл-даун по статье ──────────────────────────────────────────────
        st.divider()
        st.markdown('**🔍 Детализация по статье**')
        cats_available = sorted(cat_sum['cat'].tolist(), reverse=True)
        selected_cat = st.selectbox(
            'Выбери статью для детализации', ['— не выбрано —'] + cats_available,
            key=f'drill_cat_{year}_{month}',
        )
        if selected_cat != '— не выбрано —' and not all_exp_show.empty:
            detail = all_exp_show[all_exp_show['cat'] == selected_cat].copy()
            if not detail.empty:
                detail['studio_name'] = detail['studio'].map(
                    lambda s: STUDIO_CODES.get(s, s) if s else 'Общие'
                )
                detail_display = detail[['date', 'studio_name', 'amount', 'description']].copy()
                detail_display = detail_display.sort_values('amount', ascending=False)
                detail_display.columns = ['Дата', 'Студия', 'Сумма, ₽', 'Описание платежа']
                detail_display['Сумма, ₽'] = detail_display['Сумма, ₽'].apply(
                    lambda x: f'{x:,.0f}'.replace(',', ' ')
                )

                total_cat = detail['amount'].sum()
                count_cat = len(detail)
                st.caption(f'**{selected_cat}** — {count_cat} платежей на сумму **{fmt(total_cat)}**')
                st.dataframe(detail_display, hide_index=True, use_container_width=True)
            else:
                st.info('Данных нет (статья может быть эквайрингом — авторасчёт).')
    else:
        st.info('Нет данных о расходах')


# ══ Вкладка 3: Динамика ════════════════════════════════════════════════════════
with tab3:
    def monthly_series(df, label, exclude_cats=None):
        if df is None or df.empty:
            return pd.DataFrame(columns=['month', label])
        mask = df['year'] == year
        if studio_filter != 'Все':
            mask &= df['studio'] == studio_filter
        if entity_filter != 'Все':
            mask &= df['entity'] == entity_filter
        sub = df[mask]
        if exclude_cats:
            sub = sub[~sub['category_code'].isin(exclude_cats)]
        s = sub.groupby('month')['amount'].sum().reset_index()
        s.columns = ['month', label]
        return s

    rev_m   = monthly_series(rev_df, 'Доходы')
    exp_m   = monthly_series(exp_df, 'Операц. расходы', exclude_cats=FULLY_EXCLUDED | BELOW_LINE_CATS)
    sal_m   = monthly_series(sal_df, 'ЗП')
    below_m = monthly_series(exp_df, 'Налоги и фин.',
                              exclude_cats={c for c in range(100) if c not in BELOW_LINE_CATS})

    if not rev_df.empty:
        rev_mask = rev_df['year'] == year
        if studio_filter != 'Все': rev_mask &= rev_df['studio'] == studio_filter
        if entity_filter != 'Все': rev_mask &= rev_df['entity'] == entity_filter
        acq_m = (rev_df[rev_mask].groupby('month')['amount'].sum()
                 .mul(ACQUIRING_RATE).round(2).reset_index())
        acq_m.columns = ['month', 'Эквайринг']
    else:
        acq_m = pd.DataFrame(columns=['month', 'Эквайринг'])

    base = pd.DataFrame({'month': range(1, 13)})
    for df_m in [rev_m, exp_m, sal_m, acq_m, below_m]:
        base = base.merge(df_m, on='month', how='left')
    base = base.fillna(0)
    base['Всего расходы'] = (base.get('Операц. расходы', 0)
                             + base.get('ЗП', 0)
                             + base.get('Эквайринг', 0))
    base['Опер. прибыль'] = base['Доходы'] - base['Всего расходы']
    base['Чистая прибыль'] = base['Опер. прибыль'] - base.get('Налоги и фин.', 0)
    base['Месяц'] = base['month'].map(MONTHS_RU)

    # Линейный график помесячно
    fig_trend = go.Figure()
    for name, color, dash in [
        ('Доходы',        '#10B981', 'solid'),
        ('Всего расходы', '#EF4444', 'solid'),
        ('Опер. прибыль', '#3B82F6', 'dot'),
        ('Чистая прибыль','#8B5CF6', 'dash'),
    ]:
        fig_trend.add_scatter(
            x=base['Месяц'], y=base[name], name=name,
            line=dict(color=color, width=2.5, dash=dash),
            mode='lines+markers',
            marker=dict(size=6),
            hovertemplate=f'<b>{name}</b>: %{{y:,.0f}} ₽<extra></extra>',
        )
    fig_trend.update_layout(
        height=400, xaxis_title='', yaxis_title='₽',
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        margin=dict(t=40),
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    # YTD накопительно (только если выбран YTD режим или всегда)
    base['Доходы YTD']   = base['Доходы'].cumsum()
    base['Расходы YTD']  = base['Всего расходы'].cumsum()
    base['Прибыль YTD']  = base['Чистая прибыль'].cumsum()

    fig_ytd = go.Figure()
    fig_ytd.add_scatter(x=base['Месяц'], y=base['Доходы YTD'],   name='Доходы YTD',
                        fill='tozeroy', fillcolor='rgba(16,185,129,.12)',
                        line=dict(color='#10B981', width=2))
    fig_ytd.add_scatter(x=base['Месяц'], y=base['Расходы YTD'],  name='Расходы YTD',
                        line=dict(color='#EF4444', width=2))
    fig_ytd.add_scatter(x=base['Месяц'], y=base['Прибыль YTD'],  name='Чистая прибыль YTD',
                        line=dict(color='#8B5CF6', width=2, dash='dash'))
    fig_ytd.update_layout(
        height=300, title='Накопительно с начала года',
        xaxis_title='', yaxis_title='₽',
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        margin=dict(t=50),
    )
    st.plotly_chart(fig_ytd, use_container_width=True)


# ══ Вкладка 5: План / Факт ════════════════════════════════════════════════════
with tab5:
    if budget_df.empty:
        st.info('📋 План не введён. Перейди на страницу **🎯 Бюджет** и заполни плановые показатели.')
        st.stop()

    # Получаем план за выбранный период
    def get_plan(line):
        if budget_df.empty:
            return 0.0
        mask = (
            (budget_df['year']  == year) &
            (budget_df['month'].isin(months_range)) &
            (budget_df['line']  == line)
        )
        return float(budget_df[mask]['amount'].sum())

    plan_rev    = get_plan('revenue')
    plan_sal    = get_plan('salary')
    plan_exp    = get_plan('expenses')
    plan_below  = get_plan('below_line')
    plan_mgmt   = get_plan('mgmt')
    plan_total_exp = plan_sal + plan_exp + plan_below
    plan_profit = plan_rev - plan_total_exp

    # Факт (уже рассчитан выше)
    fact_rev    = total_revenue
    fact_sal    = total_sal
    fact_exp    = total_oper_exp_raw
    fact_below  = below_total
    fact_profit = net_profit

    def var(fact, plan, invert=False):
        """Отклонение: + хорошо, - плохо. invert=True для расходов."""
        if plan == 0:
            return None, None
        delta = fact - plan
        if invert:
            delta = -delta  # перерасход = отрицательное отклонение
        pct = delta / plan * 100
        return delta, pct

    def status(pct, invert=False):
        if pct is None:
            return '—'
        if pct >= -3:
            return '✅'
        if pct >= -10:
            return '🟡'
        return '🔴'

    # ── Сводная таблица план/факт ──────────────────────────────────────────────
    st.markdown(f'### План vs Факт — {period_label} {year}')

    rows_pnl = []
    items = [
        ('💚 Выручка',          fact_rev,    plan_rev,    False),
        ('👥 ФОТ',              fact_sal,    plan_sal,    True),
        ('🔴 Операц. расходы',  fact_exp,    plan_exp,    True),
        ('💸 Налоги',           fact_below,  plan_below,  True),
        ('💰 Чистая прибыль',   fact_profit, plan_profit, False),
    ]
    for label, fact, plan, invert in items:
        delta, pct = var(fact, plan, invert)
        rows_pnl.append({
            'Показатель': label,
            'План':       fmt(plan) if plan else '—',
            'Факт':       fmt(fact),
            'Откл. ₽':   ('+' if (delta or 0) >= 0 else '') + fmt(delta) if delta is not None else '—',
            'Откл. %':   ('+' if (pct or 0) >= 0 else '') + f'{pct:.1f}%' if pct is not None else '—',
            'Статус':     status(pct, invert) if pct is not None else '—',
        })

    df_pnl = pd.DataFrame(rows_pnl)

    def highlight_status(row):
        s = row['Статус']
        if s == '🔴':
            return ['background-color: #FEE2E2'] * len(row)
        if s == '🟡':
            return ['background-color: #FEF9C3'] * len(row)
        if s == '✅':
            return ['background-color: #DCFCE7'] * len(row)
        return [''] * len(row)

    styled_pnl = df_pnl.style.apply(highlight_status, axis=1)
    st.dataframe(styled_pnl, hide_index=True, use_container_width=True)

    # ── Умные рекомендации ─────────────────────────────────────────────────────
    st.divider()
    st.markdown('### 🤖 Автоанализ — на что обратить внимание')

    alerts = []

    # Выручка
    if plan_rev > 0:
        _, pct_rev = var(fact_rev, plan_rev, invert=False)
        if pct_rev is not None and pct_rev < -10:
            alerts.append(('🔴', f'Выручка ниже плана на **{abs(pct_rev):.1f}%** '
                           f'({fmt(plan_rev - fact_rev)} недобор). '
                           'Проверить заполняемость и причины оттока клиентов.'))
        elif pct_rev is not None and pct_rev < -3:
            alerts.append(('🟡', f'Выручка незначительно ниже плана на **{abs(pct_rev):.1f}%**. '
                           'Следить за динамикой.'))

    # ФОТ
    if plan_sal > 0:
        delta_sal, pct_sal = var(fact_sal, plan_sal, invert=True)
        if pct_sal is not None and pct_sal < -10:
            alerts.append(('🔴', f'Перерасход ФОТ на **{abs(pct_sal):.1f}%** '
                           f'(+{fmt(fact_sal - plan_sal)} сверх плана). '
                           'Проверить штатное расписание и сверхурочные.'))
        elif pct_sal is not None and pct_sal < -3:
            alerts.append(('🟡', f'ФОТ превышает план на **{abs(pct_sal):.1f}%**. '
                           'Контролировать.'))

    # Операц. расходы
    if plan_exp > 0:
        _, pct_exp = var(fact_exp, plan_exp, invert=True)
        if pct_exp is not None and pct_exp < -10:
            alerts.append(('🔴', f'Операционные расходы выше плана на **{abs(pct_exp):.1f}%** '
                           f'(+{fmt(fact_exp - plan_exp)}). '
                           'Изучить детализацию по статьям во вкладке «По статьям».'))
        elif pct_exp is not None and pct_exp < -3:
            alerts.append(('🟡', f'Операционные расходы незначительно выше плана (+**{abs(pct_exp):.1f}%**).'))

    # Налоги/финансовые
    if plan_below > 0:
        _, pct_bel = var(fact_below, plan_below, invert=True)
        if pct_bel is not None and pct_bel < -15:
            alerts.append(('🔴', f'Налоги и финансовые расходы выше плана на **{abs(pct_bel):.1f}%**. '
                           'Уточнить у бухгалтера.'))

    # Прибыль
    if plan_profit > 0:
        _, pct_pr = var(fact_profit, plan_profit, invert=False)
        if pct_pr is not None and pct_pr >= 5:
            alerts.append(('✅', f'Прибыль превышает план на **{pct_pr:.1f}%** (+{fmt(fact_profit - plan_profit)}). '
                           'Хороший результат!'))
        elif pct_pr is not None and pct_pr < -15:
            alerts.append(('🔴', f'Прибыль ниже плана на **{abs(pct_pr):.1f}%** '
                           f'({fmt(plan_profit - fact_profit)} недополучено). '
                           'Требует срочного разбора.'))

    # Маржа
    if fact_rev > 0 and plan_rev > 0:
        fact_m = fact_profit / fact_rev * 100
        plan_m = plan_profit / plan_rev * 100
        if plan_m > 0 and (fact_m - plan_m) < -5:
            alerts.append(('🟡', f'Маржинальность **{fact_m:.1f}%** vs плановая **{plan_m:.1f}%** '
                           f'— снижение на {plan_m - fact_m:.1f} п.п. '
                           'Растут расходы или падает выручка.'))

    if not alerts:
        alerts.append(('✅', 'Все показатели в пределах плановых значений. Продолжай в том же духе!'))

    for icon, text in alerts:
        if icon == '🔴':
            st.error(f'{icon} {text}')
        elif icon == '🟡':
            st.warning(f'{icon} {text}')
        else:
            st.success(f'{icon} {text}')

    # ── Помесячная динамика план vs факт ──────────────────────────────────────
    if not budget_df.empty:
        st.divider()
        st.markdown('**Помесячно: выручка и прибыль — план vs факт**')

        months_data = []
        for m in range(1, 13):
            # Факт
            def get_fact_month(df, m_val):
                if df is None or df.empty:
                    return 0.0
                mask = (df['year'] == year) & (df['month'] == m_val)
                if studio_filter != 'Все':
                    mask &= df['studio'] == studio_filter
                if entity_filter != 'Все':
                    mask &= df['entity'] == entity_filter
                return float(df[mask]['amount'].sum())

            f_rev  = get_fact_month(rev_df, m)
            f_sal  = get_fact_month(sal_df, m)
            f_exp_raw = 0.0
            if not exp_df.empty:
                mask_e = (
                    (exp_df['year'] == year) & (exp_df['month'] == m) &
                    ~exp_df['category_code'].isin(FULLY_EXCLUDED | BELOW_LINE_CATS)
                )
                if studio_filter != 'Все': mask_e &= exp_df['studio'] == studio_filter
                if entity_filter != 'Все': mask_e &= exp_df['entity'] == entity_filter
                f_exp_raw = float(exp_df[mask_e]['amount'].sum())
            f_acq  = f_rev * ACQUIRING_RATE
            f_bel  = 0.0
            if not exp_df.empty:
                mask_b = (
                    (exp_df['year'] == year) & (exp_df['month'] == m) &
                    exp_df['category_code'].isin(BELOW_LINE_CATS)
                )
                if studio_filter != 'Все': mask_b &= exp_df['studio'] == studio_filter
                if entity_filter != 'Все': mask_b &= exp_df['entity'] == entity_filter
                f_bel = float(exp_df[mask_b]['amount'].sum())
            f_profit = f_rev - f_sal - f_exp_raw - f_acq - f_bel

            # План
            def get_plan_month(line, m_val):
                if budget_df.empty:
                    return 0.0
                mask = (budget_df['year'] == year) & (budget_df['month'] == m_val) & (budget_df['line'] == line)
                return float(budget_df[mask]['amount'].sum())

            p_rev    = get_plan_month('revenue', m)
            p_sal    = get_plan_month('salary', m)
            p_exp    = get_plan_month('expenses', m)
            p_below  = get_plan_month('below_line', m)
            p_mgmt   = get_plan_month('mgmt', m)
            p_profit = p_rev - p_sal - p_exp - p_below - p_mgmt

            months_data.append({
                'Месяц': MONTHS_RU[m],
                'Выручка факт': f_rev, 'Выручка план': p_rev,
                'Прибыль факт': f_profit, 'Прибыль план': p_profit,
            })

        md = pd.DataFrame(months_data)
        md_has_data = md[['Выручка факт', 'Выручка план']].sum().sum() > 0

        if md_has_data:
            fig_pf = go.Figure()
            fig_pf.add_bar(name='Выручка план', x=md['Месяц'], y=md['Выручка план'],
                           marker_color='rgba(16,185,129,.25)', marker_line_color='#10B981',
                           marker_line_width=1.5)
            fig_pf.add_scatter(name='Выручка факт', x=md['Месяц'], y=md['Выручка факт'],
                               mode='lines+markers', line=dict(color='#10B981', width=3),
                               marker=dict(size=8))
            fig_pf.add_bar(name='Прибыль план', x=md['Месяц'], y=md['Прибыль план'],
                           marker_color='rgba(59,130,246,.2)', marker_line_color='#3B82F6',
                           marker_line_width=1.5)
            fig_pf.add_scatter(name='Прибыль факт', x=md['Месяц'], y=md['Прибыль план'],
                               mode='lines+markers', line=dict(color='#3B82F6', width=2, dash='dot'),
                               marker=dict(size=6))
            fig_pf.update_layout(
                barmode='group', height=380,
                hovermode='x unified', xaxis_title='',
                legend=dict(orientation='h', yanchor='bottom', y=1.02),
            )
            st.plotly_chart(fig_pf, use_container_width=True)


# ══ Вкладка 4: Сводная ════════════════════════════════════════════════════════
with tab4:
    col_exp, col_rev = st.columns(2)

    with col_exp:
        st.markdown('**Расходы: статья × студия**')
        all_piv = pd.concat(
            [d for d in [exp_f_show, sal_f] if not d.empty], ignore_index=True
        ) if (not exp_f_show.empty or not sal_f.empty) else pd.DataFrame()

        if not all_piv.empty or total_acquiring > 0:
            if not all_piv.empty:
                all_piv['cat'] = all_piv['category_code'].map(
                    lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else 'Прочее'
                )
                all_piv['studio_name'] = all_piv['studio'].map(
                    lambda s: STUDIO_CODES.get(s, 'Общие')
                )
                pivot = all_piv.pivot_table(
                    index='cat', columns='studio_name',
                    values='amount', aggfunc='sum', fill_value=0,
                )
            else:
                pivot = pd.DataFrame()

            if total_acquiring > 0:
                acq_lbl = f'Эквайринг {int(ACQUIRING_RATE*100)}%'
                acq_row = {STUDIO_CODES.get(s, s): round(v, 0)
                           for s, v in acq_by_studio.items() if s in STUDIO_CODES}
                adf = pd.DataFrame([acq_row], index=[acq_lbl])
                if pivot.empty:
                    pivot = adf
                else:
                    for col in adf.columns:
                        if col not in pivot.columns:
                            pivot[col] = 0
                    pivot = pd.concat([pivot, adf.reindex(columns=pivot.columns, fill_value=0)])

            if not pivot.empty:
                pivot['ИТОГО'] = pivot.sum(axis=1)
                pivot = pivot.sort_values('ИТОГО', ascending=False)
                fmt_fn = lambda x: f'{x:,.0f}'.replace(',', ' ')
                try:
                    styled = pivot.style.format(fmt_fn).background_gradient(
                        cmap='Reds', subset=[c for c in pivot.columns if c != 'ИТОГО'])
                    st.dataframe(styled, use_container_width=True, height=500)
                except Exception:
                    try:
                        st.dataframe(pivot.map(fmt_fn), use_container_width=True, height=500)
                    except AttributeError:
                        st.dataframe(pivot.applymap(fmt_fn), use_container_width=True, height=500)
        else:
            st.info('Нет данных')

    with col_rev:
        st.markdown('**Доходы: категория × студия**')
        if not rev_f.empty:
            rev_piv = rev_f.copy()
            rev_piv['cat'] = rev_piv['category_code'].map(
                lambda x: REVENUE_CATEGORIES.get(int(x), f'Кат. {x}') if pd.notna(x) else 'Прочее'
            )
            rev_piv['studio_name'] = rev_piv['studio'].map(lambda s: STUDIO_CODES.get(s, s))
            pivot2 = rev_piv.pivot_table(
                index='cat', columns='studio_name',
                values='amount', aggfunc='sum', fill_value=0,
            )
            pivot2['ИТОГО'] = pivot2.sum(axis=1)
            fmt_fn2 = lambda x: f'{x:,.0f}'.replace(',', ' ')
            try:
                styled2 = pivot2.style.format(fmt_fn2).background_gradient(cmap='Greens')
                st.dataframe(styled2, use_container_width=True, height=500)
            except Exception:
                try:
                    st.dataframe(pivot2.map(fmt_fn2), use_container_width=True, height=500)
                except AttributeError:
                    st.dataframe(pivot2.applymap(fmt_fn2), use_container_width=True, height=500)
        else:
            st.info('Нет данных')
